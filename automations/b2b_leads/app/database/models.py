from sqlalchemy import Column, String, Text, DateTime, Float, JSON, Integer
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()


def gen_uuid():
    return str(uuid.uuid4())


class Lead(Base):
    __tablename__ = "leads"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    email = Column(String, nullable=True)
    message = Column(Text, nullable=False)
    source = Column(String, default="website")
    status = Column(String, default="new")
    priority = Column(String, default="medium")
    analysis = Column(JSON, nullable=True)
    price = Column(JSON, nullable=True)
    crm_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=gen_uuid)
    lead_id = Column(String, nullable=False)
    direction = Column(String)  # inbound / outbound
    channel = Column(String)
    text = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class Event(Base):
    __tablename__ = "events"

    id = Column(String, primary_key=True, default=gen_uuid)
    lead_id = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Manager(Base):
    __tablename__ = "managers"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    handles_priority = Column(String, default="medium")
    is_active = Column(String, default="true")


class Analytics(Base):
    __tablename__ = "analytics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String, nullable=False)
    source = Column(String, nullable=False)
    priority = Column(String, nullable=False)
    count = Column(Integer, default=0)
    converted = Column(Integer, default=0)
