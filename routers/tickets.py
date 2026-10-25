import datetime, shutil, csv, io
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import get_db
from models import DBTicket, DBComment, DBEquipment
from security import get_current_user
from ws_manager import manager

router = APIRouter(prefix="/api/tickets", tags=["Tickets"])

@router.get("/")
def get_tickets(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    eq_map = {e.id: e for e in db.query(DBEquipment).all()}
    return [{
        "id": t.id, "title": t.title, "description": t.description, "category": t.category, "status": t.status, "priority": t.priority, "author": t.author, "assignee": t.assignee, "createdAt": t.createdAt, "slaDeadline": t.slaDeadline, "imagePath": t.imagePath, "rating": t.rating, "support_level": t.support_level, "parent_id": t.parent_id,
        "equipment": {"name": eq_map[t.equipment_id].name, "ip_address": eq_map[t.equipment_id].ip_address, "anydesk_id": eq_map[t.equipment_id].anydesk_id} if t.equipment_id in eq_map else None,
        "comments": [{"id": c.id, "author": c.author, "text": c.text, "filePath": c.filePath, "createdAt": c.createdAt, "isRead": c.isRead, "isInternal": getattr(c, 'isInternal', False)} for c in t.comments]
    } for t in db.query(DBTicket).order_by(DBTicket.id.desc()).all()]

@router.post("/")
async def create_ticket(category: str=Form("Оборуд."), title: str=Form(...), description: str=Form(...), priority: str=Form(...), author: str=Form(...), equipment_id: str=Form(""), image: Optional[UploadFile]=File(None), db: Session=Depends(get_db), current_user=Depends(get_current_user)):
    image_path = None
    if image and hasattr(image, "filename") and image.filename:
        with open(f"uploads/{image.filename}", "wb+") as f: shutil.copyfileobj(image.file, f)
        image_path = f"/uploads/{image.filename}"
    db.add(DBTicket(category=category, title=title, description=description, priority=priority, author=current_user.login, status="Ожидает согласования" if category in ["ПО и Доступы", "Прочее"] else "Новая", createdAt=datetime.datetime.now().strftime("%d.%m.%Y %H:%M"), slaDeadline={"Высокий": "2 часа", "Средний": "8 часов", "Низкий": "24 часа"}.get(priority, "8 часов"), imagePath=image_path, equipment_id=int(equipment_id) if equipment_id else None))
    db.commit(); await manager.broadcast("update"); return {"status": "ok"}

@router.post("/{id}/comments")
async def add_comment(id: int, author: str=Form(...), text: str=Form(...), isInternal: str=Form("false"), file: Optional[UploadFile]=File(None), db: Session=Depends(get_db), current_user=Depends(get_current_user)):
    file_path = None
    if file and hasattr(file, "filename") and file.filename:
        with open(f"uploads/{file.filename}", "wb+") as f: shutil.copyfileobj(file.file, f)
        file_path = f"/uploads/{file.filename}"
    now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M"); is_int = (isInternal.lower() == 'true')
    db.add(DBComment(ticket_id=id, author=current_user.login, text=text, filePath=file_path, createdAt=now, isInternal=is_int))
    t = db.query(DBTicket).filter(DBTicket.id == id).first()
    if t:
        if t.parent_id and current_user.login != "Система": db.add(DBComment(ticket_id=t.parent_id, author=current_user.login, text=f"📨 [Из связанной заявки #{id}]\n{text}", filePath=file_path, createdAt=now, isInternal=True))
        elif not t.parent_id and current_user.login != "Система" and not is_int:
            for child in db.query(DBTicket).filter(DBTicket.parent_id == id).all(): db.add(DBComment(ticket_id=child.id, author=current_user.login, text=text, filePath=file_path, createdAt=now))
    db.commit(); await manager.broadcast("update"); return {"status": "ok"}

@router.post("/{id}/status")
async def update_ticket_status(id: int, status: str, admin: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    if current_user.roleKey == 'user': raise HTTPException(status_code=403)
    ticket = db.query(DBTicket).filter(DBTicket.id == id).first()
    if ticket:
        if ticket.status == 'Ожидает согласования' and current_user.roleKey != 'admin': raise HTTPException(status_code=403)
        ticket.status = status
        db.add(DBComment(ticket_id=id, author="Система", text=f"Пользователь {current_user.login} перевел заявку в статус «{status}»", createdAt=datetime.datetime.now().strftime("%d.%m.%Y %H:%M"), isRead=True))
        if status in ["Решена", "Закрыта"]:
            for child in db.query(DBTicket).filter(DBTicket.parent_id == id).all():
                if child.status != status:
                    child.status = status
                    db.add(DBComment(ticket_id=child.id, author="Система", text=f"Статус автоматически изменен на «{status}» (Мастер-инцидент #{id})", createdAt=datetime.datetime.now().strftime("%d.%m.%Y %H:%M"), isRead=True))
        db.commit(); await manager.broadcast("update")
    return {"status": "ok"}

@router.post("/{id}/assign")
async def assign_ticket(id: int, assignee: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    if current_user.roleKey == 'user': raise HTTPException(status_code=403)
    ticket = db.query(DBTicket).filter(DBTicket.id == id).first()
    if ticket:
        ticket.assignee = current_user.login; ticket.status = "В работе"
        db.add(DBComment(ticket_id=id, author="Система", text=f"Инженер {current_user.login} взял заявку в работу", createdAt=datetime.datetime.now().strftime("%d.%m.%Y %H:%M"), isRead=True))
        db.commit(); await manager.broadcast("update")
    return {"status": "ok"}

@router.delete("/{id}")
async def delete_ticket(id: int, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    if current_user.roleKey != 'admin': raise HTTPException(status_code=403)
    ticket = db.query(DBTicket).filter(DBTicket.id == id).first()
    if ticket:
        db.delete(ticket)
        db.commit()
        await manager.broadcast("update")
    return {"status": "ok"}