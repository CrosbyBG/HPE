import datetime
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from database import get_db
from models import DBUserPermission

SECRET_KEY = "SUPER_SECRET_ENTERPRISE_KEY_CHANGE_ME"
ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

def verify_password(plain_password, hashed_password):
    if not hashed_password: return True
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        login: str = payload.get("sub")
        if login is None: raise HTTPException(status_code=401)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Невалидный токен")
        
    user = db.query(DBUserPermission).filter(DBUserPermission.login == login).first()
    if user is None or user.isBlocked:
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    return user

def require_admin(user: DBUserPermission = Depends(get_current_user)):
    if user.roleKey != "admin": raise HTTPException(status_code=403, detail="Требуются права Администратора")
    return user