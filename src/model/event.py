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
            # First check for exact duplicates (same start, end, and summary)
            existing_exact = (
                session.query(Event)
                .filter_by(start=self.start, end=self.end, summary=self.summary)
                .one_or_none()
            )
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
                existing_events_with_same_summary = (
                    session.query(Event)
                    .filter_by(summary=self.summary)
                    .filter(Event.email_id.isnot(None))
                    .all()
                )

                if existing_events_with_same_summary:
                    # Get the current email's delivery date
                    current_email = (
                        session.query(EMail).filter_by(id=self.email_id).first()
                    )
                    if current_email:
                        current_delivery_date = current_email.delivery_date

                        # Check if any existing events are from older emails
                        events_to_remove = []
                        for existing_event in existing_events_with_same_summary:
                            existing_email = (
                                session.query(EMail)
                                .filter_by(id=existing_event.email_id)
                                .first()
                            )
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
                                    session.query(EMail)
                                    .filter_by(id=existing_event.email_id)
                                    .first()
                                )
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
