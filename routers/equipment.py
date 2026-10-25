from fastapi import APIRouter, Depends, Form
from sqlalchemy.orm import Session
from database import get_db
from models import DBEquipment
from security import require_admin

router = APIRouter(prefix="/api/equipment", tags=["Equipment"])

@router.get("/")
def get_equipment(db: Session = Depends(get_db), current_user = Depends(require_admin)):
    return db.query(DBEquipment).all()

@router.post("/")
def add_equipment(
    name: str = Form(...), type: str = Form(...), inv_number: str = Form(""), 
    ip_address: str = Form(""), anydesk_id: str = Form(""), assigned_to: str = Form(""), 
    db: Session = Depends(get_db), current_user = Depends(require_admin)
):
    eq = DBEquipment(
        name=name, type=type, inv_number=inv_number, 
        ip_address=ip_address, anydesk_id=anydesk_id, 
        assigned_to=assigned_to if assigned_to else None
    )
    db.add(eq)
    db.commit()
    return {"status": "ok"}

@router.delete("/{id}")
def delete_equipment(id: int, db: Session = Depends(get_db), current_user = Depends(require_admin)):
    eq = db.query(DBEquipment).filter(DBEquipment.id == id).first()
    if eq:
        db.delete(eq)
        db.commit()
    return {"status": "ok"}