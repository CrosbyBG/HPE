import json, datetime
from fastapi import APIRouter, Depends, Form, Body
from sqlalchemy.orm import Session
from database import get_db
from models import DBFaq, DBScheduledTask, DBTopology, DBTicket
from security import get_current_user, require_admin

router = APIRouter(tags=["System"])

@router.get("/api/topology")
def get_topology(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    topo = db.query(DBTopology).first()
    return json.loads(topo.data) if topo and topo.data else {"nodes": [], "edges": []}

@router.post("/api/topology")
async def save_topology(data: dict = Body(...), db: Session = Depends(get_db), current_user = Depends(require_admin)):
    topo = db.query(DBTopology).first()
    if not topo: db.add(DBTopology(id=1, data=json.dumps(data)))
    else: topo.data = json.dumps(data)
    db.commit(); return {"status": "ok"}

@router.get("/api/faq")
def get_faq(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    return db.query(DBFaq).all()

@router.post("/api/faq")
def add_faq(question: str = Form(...), answer: str = Form(...), db: Session = Depends(get_db), current_user = Depends(require_admin)):
    db.add(DBFaq(question=question, answer=answer)); db.commit(); return {"status": "ok"}

@router.delete("/api/faq/{id}")
def delete_faq(id: int, db: Session = Depends(get_db), current_user = Depends(require_admin)):
    faq = db.query(DBFaq).filter(DBFaq.id == id).first()
    if faq: db.delete(faq); db.commit()
    return {"status": "ok"}

@router.get("/api/tasks")
def get_tasks(db: Session = Depends(get_db), current_user = Depends(require_admin)):
    return [{"id": t.id, "title": t.title, "description": t.description, "frequency": t.frequency, "assignee": t.assignee, "next_run": t.next_run.strftime("%d.%m.%Y %H:%M")} for t in db.query(DBScheduledTask).all()]

@router.post("/api/tasks")
def add_task(title: str=Form(...), description: str=Form(...), frequency: str=Form(...), assignee: str=Form(""), start_date: str=Form(...), db: Session=Depends(get_db), current_user=Depends(require_admin)):
    next_run = datetime.datetime.fromisoformat(start_date) if "T" in start_date else datetime.datetime.strptime(start_date, "%Y-%m-%dT%H:%M")
    db.add(DBScheduledTask(title=title, description=description, frequency=frequency, assignee=assignee, next_run=next_run)); db.commit()
    return {"status": "ok"}

@router.delete("/api/tasks/{id}")
def delete_task(id: int, db: Session = Depends(get_db), current_user = Depends(require_admin)):
    t = db.query(DBScheduledTask).filter(DBScheduledTask.id == id).first()
    if t: db.delete(t); db.commit()
    return {"status": "ok"}

@router.get("/api/stats")
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