import time
import shutil
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from ldap3 import Server, Connection, ALL, NTLM, SUBTREE

from database import get_db
from models import DBUserPermission
from security import get_current_user, require_admin, create_access_token
from ws_manager import manager, ONLINE_USERS

router = APIRouter(tags=["Users"])

# --- НАСТРОЙКИ ACTIVE DIRECTORY ---
AD_SERVER = "ldap://dc.yourcompany.local"
AD_DOMAIN = "YOURDOMAIN"
AD_SEARCH_BASE = "dc=yourcompany,dc=local"

def authenticate_ad(username, password):
    user_principal = f"{AD_DOMAIN}\\{username}"
    server = Server(AD_SERVER, get_info=ALL)
    
    try:
        conn = Connection(server, user=user_principal, password=password, authentication=NTLM, auto_bind=True)
        conn.search(
            search_base=AD_SEARCH_BASE,
            search_filter=f'(sAMAccountName={username})',
            search_scope=SUBTREE,
            attributes=['displayName', 'department']
        )
        
        ad_user = {}
        if conn.entries:
            entry = conn.entries[0]
            ad_user['fullName'] = entry.displayName.value if entry.displayName else username
            ad_user['dept'] = entry.department.value if entry.department else "Не указан"
            
        conn.unbind()
        return True, ad_user
    except Exception as e:
        return False, None

@router.post("/api/login")
def login(login: str, password: str = "", db: Session = Depends(get_db)):
    if not password:
        raise HTTPException(status_code=400, detail="Пароль обязателен")

    # 1. ОБХОД AD ДЛЯ ДЕМО-АККАУНТОВ И ЛОКАЛЬНОГО АДМИНА
    demo_accounts = {
        "admin": "LocalAdminPass!",
        "engineer": "12345",
        "user": "12345"
    }
    
    if login in demo_accounts and password == demo_accounts[login]:
        user = db.query(DBUserPermission).filter(DBUserPermission.login == login).first()
        if not user:
            roles = {"admin": "admin", "engineer": "engineer", "user": "user"}
            names = {"admin": "Главный Админ", "engineer": "Старший Инженер", "user": "Тестовый Пользователь"}
            user = DBUserPermission(login=login, fullName=names[login], dept="Демо Отдел", roleKey=roles[login], isBlocked=False)
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            user.isBlocked = False
            db.commit()
            
        token = create_access_token({"sub": user.login, "role": user.roleKey})
        return {"token": token, "login": user.login, "fullName": user.fullName, "roleKey": user.roleKey, "dept": user.dept}

    # 2. ПРОВЕРКА ЧЕРЕЗ ACTIVE DIRECTORY
    is_auth, ad_data = authenticate_ad(login, password)
    if not is_auth:
        raise HTTPException(status_code=401, detail="Неверный логин или пароль (AD)")

    user = db.query(DBUserPermission).filter(DBUserPermission.login == login).first()
    if not user:
        user = DBUserPermission(
            login=login, 
            fullName=ad_data.get('fullName', login), 
            dept=ad_data.get('dept', "Общий отдел"), 
            roleKey="user", 
            isBlocked=False
        )
        db.add(user)
    else:
        if user.isBlocked:
            raise HTTPException(status_code=403, detail="Доступ заблокирован в HelpDesk")
        if ad_data:
            user.fullName = ad_data.get('fullName', user.fullName)
            user.dept = ad_data.get('dept', user.dept)

    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": user.login, "role": user.roleKey})
    return {"token": token, "login": user.login, "fullName": user.fullName, "roleKey": user.roleKey, "dept": user.dept}

@router.get("/api/users_map")
def get_users_map(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    users = db.query(DBUserPermission).all()
    return {u.login: {"fullName": u.fullName, "avatarPath": u.avatarPath, "dept": u.dept, "isOnSite": u.isOnSite, "isOnline": (u.login in ONLINE_USERS), "roleKey": u.roleKey} for u in users}

@router.post("/api/users/{login}/onsite")
async def toggle_onsite(login: str, status: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    if current_user.login != login and current_user.roleKey != "admin": raise HTTPException(status_code=403)
    user = db.query(DBUserPermission).filter(DBUserPermission.login == login).first()
    if user: user.isOnSite = (status.lower() == 'true'); db.commit(); await manager.broadcast("update_users")
    return {"status": "ok"}

@router.get("/api/users")
def get_users(db: Session = Depends(get_db), current_user = Depends(require_admin)):
    return db.query(DBUserPermission).all()

@router.post("/api/users/{login}/role")
async def update_user_role(login: str, roleKey: str, db: Session = Depends(get_db), current_user = Depends(require_admin)):
    user = db.query(DBUserPermission).filter(DBUserPermission.login == login).first()
    if user: user.roleKey = roleKey; db.commit(); await manager.broadcast("update_users")
    return {"status": "ok"}

@router.post("/api/users/{login}/block")
async def block_user(login: str, isBlocked: bool, db: Session = Depends(get_db), current_user = Depends(require_admin)):
    user = db.query(DBUserPermission).filter(DBUserPermission.login == login).first()
    if user: user.isBlocked = isBlocked; db.commit(); await manager.broadcast("update_users")
    return {"status": "ok"}

@router.post("/api/users/{login}/profile")
async def update_profile(login: str, fullName: str = Form(...), dept: str = Form(...), avatar: Optional[UploadFile] = File(None), db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    if current_user.login != login and current_user.roleKey != "admin": raise HTTPException(status_code=403)
    user = db.query(DBUserPermission).filter(DBUserPermission.login == login).first()
    if user:
        user.fullName = fullName; user.dept = dept
        if avatar and hasattr(avatar, "filename") and avatar.filename:
            path = f"uploads/avatar_{login}_{int(time.time())}_{avatar.filename}"
            with open(path, "wb+") as f: shutil.copyfileobj(avatar.file, f)
            user.avatarPath = f"/{path}"
        db.commit(); await manager.broadcast("update_users")
        return {"login": user.login, "fullName": user.fullName, "dept": user.dept, "roleKey": user.roleKey, "avatarPath": user.avatarPath}
    raise HTTPException(status_code=404)