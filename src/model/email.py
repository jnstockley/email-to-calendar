from datetime import datetime
import enum

import tzlocal
from sqlmodel import SQLModel, Field, select

from src.db import Session, engine
from src.model.event import Event


class EMailType(enum.Enum):
    PLAIN = "plain"
    HTML = "html"


class EMail(SQLModel, table=True):
    id: int = Field(primary_key=True)
    subject: str = Field(nullable=False)
    from_address: str = Field(nullable=False)
    delivery_date: datetime = Field(nullable=False)
    body: str = Field(nullable=False)
    retrieved_date: datetime = Field(
        nullable=False, default=lambda: datetime.now(tzlocal.get_localzone())
    )
    email_type: EMailType = Field(nullable=False)

    def __repr__(self):
        return f"<EMail(id={self.id}, subject={self.subject}, from_address={self.from_address}, delivery_date={self.delivery_date})>"

    def __str__(self):
        return f"EMail(id={self.id}, subject={self.subject}, from_address={self.from_address}, delivery_date={self.delivery_date})"

    def save(self):
        session = Session(engine)
        try:
            self.retrieved_date = datetime.now(tzlocal.get_localzone())
            session.merge(self)
            session.commit()
        finally:
            session.close()

    def get(self):
        session = Session(engine)
        try:
            return session.exec(select(EMail).where(EMail.id == self.id)).first()
        finally:
            session.close()

    def delete(self):
        session = Session(engine)
        try:
            session.delete(EMail.where(EMail.id == self.id))
            session.commit()
        finally:
            session.close()

    @staticmethod
    def get_by_id(email_id: int):
        session = Session(engine)
        try:
            return session.exec(select(EMail).where(EMail.id == email_id)).first()
        finally:
            session.close()

    @staticmethod
    def get_all():
        session = Session(engine)
        try:
            return session.exec(select(EMail)).all()
        finally:
            session.close()

    @staticmethod
    def get_by_delivery_date(delivery_date: datetime):
        session = Session(engine)
        try:
            return session.exec(
                select(EMail).where(EMail.delivery_date == delivery_date)
            ).all()
        finally:
            session.close()

    @staticmethod
    def get_most_recent():
        session = Session(engine)
        try:
            return session.exec(
                select(EMail).order_by(EMail.delivery_date.desc())
            ).first()
        finally:
            session.close()

    @staticmethod
    def get_most_recent_without_events():
        session = Session(engine)
        try:
            email: EMail = session.exec(
                select(EMail).order_by(EMail.delivery_date.desc())
            ).first()
            # Check if this email has any associated events
            if email:
                event = session.exec(
                    select(Event).where(Event.email_id == email.id)
                ).first()
                if event:
                    return None  # The most recent email has associated events
            return email
        finally:
            session.close()

    @staticmethod
    def get_without_events():
        session = Session(engine)
        try:
            # Use NOT EXISTS to find emails with no events referencing them
            result = session.exec(
                select(EMail).where(
                    ~select(Event).where(Event.email_id == EMail.id).exists()
                )
            ).all()
            return result
        finally:
            session.close()
