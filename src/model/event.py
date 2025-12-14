from datetime import datetime

from sqlalchemy import (
    UniqueConstraint,
)
from sqlmodel import SQLModel, Field, select

from src.db import Session, engine


class Event(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("start", "end", "summary", name="uq_event_start_end_summary"),
    )
    id: int | None = Field(
        primary_key=True,
        default=None,
        description="The unique identifier for the event, use the `get_event_id` tool to get determine this value.",
    )
    start: datetime = Field(
        nullable=False,
        description="The start date and time of the event, must be a Python datetime object, cannot be None",
    )
    end: datetime = Field(
        nullable=False,
        description="The end date and time of the event, must be a Python datetime object, cannot be None",
    )
    all_day: bool = Field(
        nullable=False,
        default=False,
        description="Whether the event lasts all day or not",
    )
    summary: str = Field(
        nullable=False, description="A brief summary or title of the event"
    )
    email_id: int = Field(
        foreign_key="email.id",
        nullable=True,
        description="The ID of the email from which this event was created, use the `get_email_id` tool to get determine this value.",
    )
    in_calendar: bool = Field(
        nullable=False,
        default=False,
        description="Indicates whether the event has been saved to the calendar",
    )
    caldav_id: str | None = Field(
        nullable=True, description="The CalDAV identifier for the event, if applicable"
    )

    def __repr__(self):
        return f"<Event(id={self.id}, start={self.start}, end={self.end}, summary={self.summary})>"

    def __str__(self):
        return f"Event(id={self.id}, start={self.start}, end={self.end}, summary={self.summary})"

    def save(self):
        session = Session(engine)
        try:
            if isinstance(self.start, str):
                self.start = datetime.fromisoformat(self.start)
            if isinstance(self.end, str):
                self.end = datetime.fromisoformat(self.end)
            self.summary = self.summary.lower()
            if self.id:
                self.caldav_id = Event.get_by_id(self.id).caldav_id
            event = session.merge(self)
            session.commit()
            session.flush()
            session.refresh(event)
            return event
        finally:
            session.close()

    def get(self):
        session = Session(engine)
        try:
            return session.exec(select(Event).where(Event.id == self.id)).first()
        finally:
            session.close()

    def delete(self):
        session = Session(engine)
        try:
            session.delete(Event.where(Event.id == self.id))
            session.commit()
        finally:
            session.close()

    def save_to_caldav(self):
        session = Session(engine)
        try:
            self.in_calendar = True
            session.merge(self)
            session.commit()
        finally:
            session.close()

    @staticmethod
    def get_by_id(event_id: int):
        session = Session(engine)
        try:
            return session.exec(select(Event).where(Event.id == event_id)).first()
        finally:
            session.close()

    @staticmethod
    def get_all():
        session = Session(engine)
        try:
            return session.exec(select(Event)).all()
        finally:
            session.close()

    @staticmethod
    def get_by_date(date: datetime):
        session = Session(engine)
        try:
            return session.exec(
                select(Event).where(Event.start == date or Event.end == date)
            ).all()
        finally:
            session.close()

    @staticmethod
    def get_not_in_calendar():
        session = Session(engine)
        try:
            return session.exec(select(Event).where(not Event.in_calendar)).all()
        finally:
            session.close()

    @staticmethod
    def get_max_id():
        session = Session(engine)
        try:
            max_id = session.exec(select(Event.id).order_by(Event.id.desc())).first()
            return max_id if max_id is not None else 1
        finally:
            session.close()

    @staticmethod
    def find_unique_event(start: datetime, end: datetime, summary: str):
        session = Session(engine)
        try:
            return session.exec(
                select(Event).where(
                    Event.start == start,
                    Event.end == end,
                    Event.summary == summary.lower(),
                )
            ).first()
        finally:
            session.close()
