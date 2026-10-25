import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class DBUserPermission(Base):
    __tablename__ = "user_permissions"
    id = Column(Integer, primary_key=True, index=True)
    login = Column(String, unique=True, index=True)
    hashed_password = Column(String, default="")
    fullName = Column(String, default="")
    dept = Column(String, default="")
    roleKey = Column(String, default="user")
    isBlocked = Column(Boolean, default=False)
    avatarPath = Column(String, nullable=True)
    isOnSite = Column(Boolean, default=False)
    isOnline = Column(Boolean, default=False)
    updatedAt = Column(DateTime, default=datetime.datetime.now)

class DBEquipment(Base):
    __tablename__ = "equipment"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String) 
    type = Column(String) 
    inv_number = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    anydesk_id = Column(String, nullable=True)
    assigned_to = Column(String, nullable=True)

class DBTicket(Base):
    __tablename__ = "tickets"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(Text)
    category = Column(String, default="Оборудование")
    status = Column(String, default="Новая")
    priority = Column(String, default="Средний")
    author = Column(String)
    assignee = Column(String, nullable=True)
    createdAt = Column(String)
    slaDeadline = Column(String, nullable=True)
    imagePath = Column(String, nullable=True)
    rating = Column(Integer, nullable=True)
    feedback = Column(Text, nullable=True)
    support_level = Column(String, default="L1")
    parent_id = Column(Integer, nullable=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id"), nullable=True)
    
    comments = relationship("DBComment", back_populates="ticket", cascade="all, delete-orphan")

class DBComment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"))
    author = Column(String)
    text = Column(Text)
    filePath = Column(String, nullable=True)
    createdAt = Column(String)
    isRead = Column(Boolean, default=False)
    isInternal = Column(Boolean, default=False)

    ticket = relationship("DBTicket", back_populates="comments")

class DBFaq(Base):
    __tablename__ = "faq"
    id = Column(Integer, primary_key=True, index=True)
    question = Column(String)
    answer = Column(Text)

class DBScheduledTask(Base):
    __tablename__ = "scheduled_tasks"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(Text)
    frequency = Column(String)
    assignee = Column(String, nullable=True)
    next_run = Column(DateTime)

class DBTopology(Base):
    __tablename__ = "topology"
    id = Column(Integer, primary_key=True)
    data = Column(Text, default='{"nodes":[], "edges":[]}')