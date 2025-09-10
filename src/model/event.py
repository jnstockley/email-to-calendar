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
    id: int = Field(primary_key=True)
    start: datetime = Field(nullable=False)
    end: datetime = Field(nullable=False)
    summary: str = Field(nullable=False)
    email_id: int = Field(foreign_key="email.id", nullable=True)
    in_calendar: bool = Field(nullable=False, default=False)

    def __repr__(self):
        return f"<Event(id={self.id}, start={self.start}, end={self.end}, summary={self.summary})>"

    def __str__(self):
        return f"Event(id={self.id}, start={self.start}, end={self.end}, summary={self.summary})"

    def save(self):
        session = Session(engine)
        try:
            # First check for exact duplicates (same start, end, and summary)
            existing_exact = session.exec(
                select(Event).where(
                    Event.start == self.start,
                    Event.end == self.end,
                    Event.summary == self.summary,
                )
            ).first()
            if existing_exact:
                # Preserve email linkage if existing record has it but new instance doesn't
                if self.email_id is None and existing_exact.email_id is not None:
                    self.email_id = existing_exact.email_id
                self.id = (
                    existing_exact.id
                )  # Update the ID to match the existing record
                session.merge(self)
                session.commit()
                return

            # Check for events with the same summary but different start/end times
            if self.email_id is not None:
                from src.model.email import (
                    EMail,
                )  # Import here to avoid circular import

                # Get all events with the same summary
                existing_events_with_same_summary = session.exec(
                    select(Event).where(
                        Event.summary == self.summary,
                    )
                ).all()

                if existing_events_with_same_summary:
                    # Get the current email's delivery date
                    current_email = (
                        session.exec(select(Event).where(Event.id==self.id)).first()
                    )
                    if current_email:
                        current_delivery_date = current_email.delivery_date

                        # Check if any existing events are from older emails
                        events_to_remove = []
                        for existing_event in existing_events_with_same_summary:
                            existing_email = (
                                session.exec(select(EMail).where(EMail.id == existing_event.email_id)).first())
                            if (
                                existing_email
                                and existing_email.delivery_date < current_delivery_date
                            ):
                                events_to_remove.append(existing_event)

                        # Remove older events with the same summary
                        for event_to_remove in events_to_remove:
                            session.delete(event_to_remove)

                        # Also check if there are newer events with the same summary
                        has_newer_event = False
                        for existing_event in existing_events_with_same_summary:
                            if existing_event not in events_to_remove:
                                existing_email = (
                                    session.exec(select(EMail).where(EMail.id==existing_event.email_id)).first())
                                if (
                                    existing_email
                                    and existing_email.delivery_date
                                    > current_delivery_date
                                ):
                                    has_newer_event = True
                                    break

                        # Only save the current event if there are no newer events with the same summary
                        if not has_newer_event:
                            session.merge(self)
                            session.commit()
                        # If there is a newer event, don't save the current event
                    else:
                        # If we can't get the email, proceed with normal save
                        session.merge(self)
                        session.commit()
                else:
                    # No existing events with same summary, proceed with normal save
                    session.merge(self)
                    session.commit()
            else:
                # No email_id, proceed with normal save
                session.merge(self)
                session.commit()
        finally:
            session.close()

    def get(self):
        session = Session(engine)
        try:
            return session.exec(select(Event).where(Event.id==self.id)).first()
        finally:
            session.close()

    def delete(self):
        session = Session(engine)
        try:
            session.delete(Event.where(Event.id==self.id))
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
            return (
                session.exec(select(Event).where(Event.start == date or Event.end == date)).all())
        finally:
            session.close()
