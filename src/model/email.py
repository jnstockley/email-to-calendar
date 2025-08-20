from datetime import datetime
import enum

import tzlocal
from sqlalchemy import Column, Integer, String, DateTime, Enum
from sqlalchemy.orm import relationship

from src.db import Base, SessionLocal


class EMailType(enum.Enum):
    PLAIN = "plain"
    HTML = "html"


class EMail(Base):
    __tablename__ = "emails"
    id = Column(Integer, primary_key=True, autoincrement=True)
    subject = Column(String, nullable=False)
    from_address = Column(String, nullable=False)
    delivery_date = Column(DateTime, nullable=False)
    body = Column(String, nullable=False)
    retrieved_date = Column(
        DateTime, nullable=False, default=lambda: datetime.now(tzlocal.get_localzone())
    )
    email_type = Column(Enum(EMailType), nullable=False)

    events = relationship("Event", back_populates="email", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<EMail(id={self.id}, subject={self.subject}, from_address={self.from_address}, delivery_date={self.delivery_date})>"

    def __str__(self):
        return f"EMail(id={self.id}, subject={self.subject}, from_address={self.from_address}, delivery_date={self.delivery_date})"

    def save(self):
        session = SessionLocal()
        try:
            self.retrieved_date = datetime.now(tzlocal.get_localzone())
            session.merge(self)
            session.commit()
        finally:
            session.close()

    def get(self):
        session = SessionLocal()
        try:
            return session.query(EMail).filter(EMail.id == self.id).first()
        finally:
            session.close()

    def delete(self):
        session = SessionLocal()
        try:
            session.query(EMail).filter(EMail.id == self.id).delete()
            session.commit()
        finally:
            session.close()

    @staticmethod
    def get_by_id(email_id: int):
        session = SessionLocal()
        try:
            return session.query(EMail).filter(EMail.id == email_id).first()
        finally:
            session.close()

    @staticmethod
    def get_all():
        session = SessionLocal()
        try:
            return session.query(EMail).all()
        finally:
            session.close()

    @staticmethod
    def get_by_delivery_date(delivery_date: datetime):
        session = SessionLocal()
        try:
            return (
                session.query(EMail).filter(EMail.delivery_date == delivery_date).all()
            )
        finally:
            session.close()

    @staticmethod
    def get_most_recent():
        session = SessionLocal()
        try:
            return session.query(EMail).order_by(EMail.delivery_date.desc()).first()
        finally:
            session.close()
