from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    UniqueConstraint,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from src.db import Base, SessionLocal


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("start", "end", "summary", name="uq_event_start_end_summary"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    start = Column(DateTime, nullable=False)
    end = Column(DateTime, nullable=False)
    summary = Column(String, nullable=False)
    email_id = Column(Integer, ForeignKey("emails.id"), nullable=True, index=True)
    in_calendar = Column(Boolean, nullable=False, default=False)

    email = relationship("EMail", back_populates="events")

    def __repr__(self):
        return f"<Event(id={self.id}, start={self.start}, end={self.end}, summary={self.summary})>"

    def __str__(self):
        return f"Event(id={self.id}, start={self.start}, end={self.end}, summary={self.summary})"

    def save(self):
        session = SessionLocal()
        try:
            existing = (
                session.query(Event)
                .filter_by(start=self.start, end=self.end, summary=self.summary)
                .one_or_none()
            )
            if existing:
                # Preserve email linkage if existing record has it but new instance doesn't
                if self.email_id is None and existing.email_id is not None:
                    self.email_id = existing.email_id
                self.id = existing.id  # Update the ID to match the existing record
            session.merge(self)
            session.commit()
        finally:
            session.close()

    def get(self):
        session = SessionLocal()
        try:
            return session.query(Event).filter(Event.id == self.id).first()
        finally:
            session.close()

    def delete(self):
        session = SessionLocal()
        try:
            session.query(Event).filter(Event.id == self.id).delete()
            session.commit()
        finally:
            session.close()

    def save_to_caldav(self):
        session = SessionLocal()
        try:
            self.in_calendar = True
            session.merge(self)
            session.commit()
        finally:
            session.close()

    @staticmethod
    def get_by_id(event_id: int):
        session = SessionLocal()
        try:
            return session.query(Event).filter(Event.id == event_id).first()
        finally:
            session.close()

    @staticmethod
    def get_all():
        session = SessionLocal()
        try:
            return session.query(Event).all()
        finally:
            session.close()

    @staticmethod
    def get_by_date(date: datetime):
        session = SessionLocal()
        try:
            return (
                session.query(Event)
                .filter(Event.start == date or Event.end == date)
                .all()
            )
        finally:
            session.close()
