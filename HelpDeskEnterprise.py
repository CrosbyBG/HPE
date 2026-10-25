import sys, os, time, shutil, datetime, asyncio, webbrowser, io, csv, json
from contextlib import asynccontextmanager
from typing import Optional

class DummyStream:
    def write(self, *args, **kwargs): pass
    def flush(self, *args, **kwargs): pass
    def isatty(self): return False

if sys.stdout is None: sys.stdout = DummyStream()
if sys.stderr is None: sys.stderr = DummyStream()

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect, Body
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import engine, SessionLocal, get_db, Base
from models import DBUserPermission, DBEquipment, DBTicket, DBComment, DBFaq, DBScheduledTask, DBTopology
from security import get_current_user, require_admin, get_password_hash
from ws_manager import manager

Base.metadata.create_all(bind=engine)

with engine.begin() as conn:
    queries = [
        "ALTER TABLE comments ADD COLUMN filePath VARCHAR", "ALTER TABLE tickets ADD COLUMN imagePath VARCHAR",
        "ALTER TABLE comments ADD COLUMN isRead BOOLEAN DEFAULT 0", "ALTER TABLE comments ADD COLUMN isInternal BOOLEAN DEFAULT 0",
        "ALTER TABLE user_permissions ADD COLUMN avatarPath VARCHAR", "ALTER TABLE user_permissions ADD COLUMN isOnSite BOOLEAN DEFAULT 0",
        "ALTER TABLE user_permissions ADD COLUMN isOnline BOOLEAN DEFAULT 0", "ALTER TABLE tickets ADD COLUMN rating INTEGER",
        "ALTER TABLE tickets ADD COLUMN feedback TEXT", "ALTER TABLE tickets ADD COLUMN support_level VARCHAR DEFAULT 'L1'",
        "ALTER TABLE tickets ADD COLUMN parent_id INTEGER", "ALTER TABLE tickets ADD COLUMN equipment_id INTEGER REFERENCES equipment(id)",
        "ALTER TABLE user_permissions ADD COLUMN hashed_password VARCHAR DEFAULT ''",
        "UPDATE user_permissions SET isOnline = 0"
    ]
    for q in queries:
        try: conn.execute(text(q))
        except: pass

async def scheduled_tasks_loop():
    while True:
        await asyncio.sleep(30)
        db = SessionLocal()
        try:
            now = datetime.datetime.now()
            tasks = db.query(DBScheduledTask).filter(DBScheduledTask.next_run <= now).all()
            if tasks:
                for t in tasks:
                    new_ticket = DBTicket(title=f"[РЕГЛАМЕНТ] {t.title}", description=t.description, category="Прочее", priority="Средний", author="Система", assignee=t.assignee if t.assignee else "Не назначен", status="В работе" if t.assignee and t.assignee != "Не назначен" else "Новая", createdAt=now.strftime("%d.%m.%Y %H:%M"), slaDeadline="24 часа", support_level="L1")
                    db.add(new_ticket)
                    while t.next_run <= now:
                        t.next_run += datetime.timedelta(days=1 if t.frequency == 'DAILY' else (7 if t.frequency == 'WEEKLY' else 30))
                db.commit(); await manager.broadcast("update")
        except Exception: pass
        finally: db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(scheduled_tasks_loop())
    yield

app = FastAPI(title="HelpDeskManager", lifespan=lifespan)
os.makedirs("uploads", exist_ok=True); os.makedirs("static", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/static", StaticFiles(directory="static"), name="static")

from routers import equipment, users
app.include_router(equipment.router)
app.include_router(users.router)

def seed_default_data():
    db = SessionLocal()
    if db.query(DBUserPermission).count() == 0:
        db.add_all([
            DBUserPermission(login="admin", fullName="Главный Администратор", dept="ИТ", roleKey="admin", hashed_password=get_password_hash("12345")),
            DBUserPermission(login="engineer", fullName="Старший Инженер", dept="Техподдержка", roleKey="engineer", hashed_password=get_password_hash("12345")),
            DBUserPermission(login="user", fullName="Иван Пользователь", dept="Бухгалтерия", roleKey="user", hashed_password=get_password_hash("12345")),
        ])
        db.add(DBFaq(question="Сброс пароля", answer="Обратитесь в отдел кадров."))
        db.add(DBTopology(id=1, data='{"nodes":[], "edges":[]}'))
        db.commit()
    db.close()
seed_default_data()

@app.get("/", response_class=FileResponse)
def get_index(): return "static/index.html"

@app.get("/api/topology")
def get_topology(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    topo = db.query(DBTopology).first()
    return json.loads(topo.data) if topo and topo.data else {"nodes": [], "edges": []}

@app.post("/api/topology")
async def save_topology(data: dict = Body(...), db: Session = Depends(get_db), current_user = Depends(require_admin)):
    topo = db.query(DBTopology).first()
    if not topo: db.add(DBTopology(id=1, data=json.dumps(data)))
    else: topo.data = json.dumps(data)
    db.commit(); return {"status": "ok"}

@app.get("/api/faq")
def get_faq(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    return db.query(DBFaq).all()

@app.post("/api/faq")
def add_faq(question: str = Form(...), answer: str = Form(...), db: Session = Depends(get_db), current_user = Depends(require_admin)):
    db.add(DBFaq(question=question, answer=answer)); db.commit(); return {"status": "ok"}

@app.delete("/api/faq/{id}")
def delete_faq(id: int, db: Session = Depends(get_db), current_user = Depends(require_admin)):
    faq = db.query(DBFaq).filter(DBFaq.id == id).first()
    if faq: db.delete(faq); db.commit()
    return {"status": "ok"}

@app.get("/api/tasks")
def get_tasks(db: Session = Depends(get_db), current_user = Depends(require_admin)):
    return [{"id": t.id, "title": t.title, "description": t.description, "frequency": t.frequency, "assignee": t.assignee, "next_run": t.next_run.strftime("%d.%m.%Y %H:%M")} for t in db.query(DBScheduledTask).all()]

@app.post("/api/tasks")
def add_task(title: str=Form(...), description: str=Form(...), frequency: str=Form(...), assignee: str=Form(""), start_date: str=Form(...), db: Session=Depends(get_db), current_user=Depends(require_admin)):
    next_run = datetime.datetime.fromisoformat(start_date) if "T" in start_date else datetime.datetime.strptime(start_date, "%Y-%m-%dT%H:%M")
    db.add(DBScheduledTask(title=title, description=description, frequency=frequency, assignee=assignee, next_run=next_run)); db.commit()
    return {"status": "ok"}

@app.delete("/api/tasks/{id}")
def delete_task(id: int, db: Session = Depends(get_db), current_user = Depends(require_admin)):
    t = db.query(DBScheduledTask).filter(DBScheduledTask.id == id).first()
    if t: db.delete(t); db.commit()
    return {"status": "ok"}

@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db), current_user = Depends(require_admin)):
    tickets = db.query(DBTicket).all()
    statuses = {"Новая": 0, "В работе": 0, "Решена": 0, "Закрыта": 0}; dates = {}; active = csat_sum = csat_count = 0
    for t in tickets:
        if t.status in statuses: statuses[t.status] += 1
        if t.status in ["Новая", "В работе"]: active += 1
        if t.rating: csat_sum += t.rating; csat_count += 1
        d = t.createdAt.split(' ')[0]
        dates[d] = dates.get(d, 0) + 1
    return {"total": len(tickets), "active": active, "avg_csat": round(csat_sum / csat_count, 1) if csat_count > 0 else 0.0, "statuses": statuses, "dates": dict(sorted(dates.items())[-7:])}

@app.get("/api/tickets")
def get_tickets(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    eq_map = {e.id: e for e in db.query(DBEquipment).all()}
    return [{
        "id": t.id, "title": t.title, "description": t.description, "category": t.category, "status": t.status, "priority": t.priority, "author": t.author, "assignee": t.assignee, "createdAt": t.createdAt, "slaDeadline": t.slaDeadline, "imagePath": t.imagePath, "rating": t.rating, "support_level": t.support_level, "parent_id": t.parent_id,
        "equipment": {"name": eq_map[t.equipment_id].name, "ip_address": eq_map[t.equipment_id].ip_address, "anydesk_id": eq_map[t.equipment_id].anydesk_id} if t.equipment_id in eq_map else None,
        "comments": [{"id": c.id, "author": c.author, "text": c.text, "filePath": c.filePath, "createdAt": c.createdAt, "isRead": c.isRead, "isInternal": getattr(c, 'isInternal', False)} for c in t.comments]
    } for t in db.query(DBTicket).order_by(DBTicket.id.desc()).all()]

@app.post("/api/tickets")
async def create_ticket(category: str=Form("Оборуд."), title: str=Form(...), description: str=Form(...), priority: str=Form(...), author: str=Form(...), equipment_id: str=Form(""), image: Optional[UploadFile]=File(None), db: Session=Depends(get_db), current_user=Depends(get_current_user)):
    image_path = None
    if image and hasattr(image, "filename") and image.filename:
        with open(f"uploads/{image.filename}", "wb+") as f: shutil.copyfileobj(image.file, f)
        image_path = f"/uploads/{image.filename}"
    db.add(DBTicket(category=category, title=title, description=description, priority=priority, author=current_user.login, status="Ожидает согласования" if category in ["ПО и Доступы", "Прочее"] else "Новая", createdAt=datetime.datetime.now().strftime("%d.%m.%Y %H:%M"), slaDeadline={"Высокий": "2 часа", "Средний": "8 часов", "Низкий": "24 часа"}.get(priority, "8 часов"), imagePath=image_path, equipment_id=int(equipment_id) if equipment_id else None))
    db.commit(); await manager.broadcast("update"); return {"status": "ok"}

@app.post("/api/tickets/{id}/comments")
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

@app.post("/api/tickets/{id}/status")
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

@app.post("/api/tickets/merge")
async def merge_tickets(req: dict = Body(...), db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    if current_user.roleKey == 'user': raise HTTPException(status_code=403)
    now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    master = DBTicket(title=f"Массовый инцидент (Связано заявок: {len(req.get('ticket_ids', []))})", description="Глобальный инцидент. Связанные заявки будут закрыты автоматически.", category="Сеть и Интернет", priority="Высокий", author=current_user.login, assignee=current_user.login, status="В работе", createdAt=now, slaDeadline="2 часа", support_level="L2")
    db.add(master); db.commit(); db.refresh(master)
    for t_id in req.get('ticket_ids', []):
        child = db.query(DBTicket).filter(DBTicket.id == int(t_id)).first()
        if child and not child.parent_id:
            child.parent_id = master.id; child.status = "В работе"
            db.add(DBComment(ticket_id=child.id, author="Система", text=f"Заявка привязана к Мастер-инциденту #{master.id}.", createdAt=now, isRead=True))
    db.commit(); await manager.broadcast("update"); return {"status": "ok"}

@app.post("/api/tickets/{id}/assign")
async def assign_ticket(id: int, assignee: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    if current_user.roleKey == 'user': raise HTTPException(status_code=403)
    ticket = db.query(DBTicket).filter(DBTicket.id == id).first()
    if ticket:
        ticket.assignee = current_user.login; ticket.status = "В работе"
        db.add(DBComment(ticket_id=id, author="Система", text=f"Инженер {current_user.login} взял заявку в работу", createdAt=datetime.datetime.now().strftime("%d.%m.%Y %H:%M"), isRead=True))
        db.commit(); await manager.broadcast("update")
    return {"status": "ok"}

@app.get("/api/export/excel")
def export_excel(db: Session = Depends(get_db)):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Тема', 'Категория', 'Статус', 'Приоритет', 'Автор', 'Исполнитель', 'Дата создания', 'Оценка CSAT'])
    for t in db.query(DBTicket).all():
        writer.writerow([t.id, t.title, t.category, t.status, t.priority, t.author, t.assignee or 'Не назначен', t.createdAt, f"{t.rating}/5" if t.rating else 'Нет'])
    output.seek(0)
    return StreamingResponse(io.BytesIO(output.getvalue().encode('utf-8-sig')), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=helpdesk_report.csv"})

@app.delete("/api/tickets/{id}")
async def delete_ticket(id: int, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    if current_user.roleKey != 'admin': raise HTTPException(status_code=403)
    ticket = db.query(DBTicket).filter(DBTicket.id == id).first()
    if ticket:
        db.delete(ticket)
        db.commit()
        await manager.broadcast("update")
    return {"status": "ok"}

@app.websocket("/ws/{login}")
async def websocket_endpoint(websocket: WebSocket, login: str):
    await manager.connect(websocket, login)
    try:
        while True: await websocket.receive_text()
    except: manager.disconnect(websocket, login)

if __name__ == "__main__":
    import uvicorn
    import threading
    PORT = 8050
    threading.Thread(target=lambda: (time.sleep(1.5), webbrowser.open(f"http://127.0.0.1:{PORT}")), daemon=True).start()
    uvicorn.run("HelpDeskEnterprise:app", host="0.0.0.0", port=PORT, reload=True, log_config=None)