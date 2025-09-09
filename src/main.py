import asyncio
import os

from sqlalchemy import inspect

from src import db_file, logger
from src.events.caldav import add_to_caldav
from src.mail import mail
from src.db import Base, engine, SessionLocal
from src.model.email import EMail
from src.model.event import Event
from src.util.ai import parse_email
from src.util.env import get_settings


async def main():
    logger.info("Starting email retrieval process")
    settings = get_settings()

    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)

    imap_host = settings.IMAP_HOST
    imap_port = settings.IMAP_PORT
    imap_username = settings.IMAP_USERNAME
    imap_password = settings.IMAP_PASSWORD

    from_email = settings.FILTER_FROM_EMAIL
    subject = settings.FILTER_SUBJECT
    backfill = settings.BACKFILL

    db_path = os.path.join(os.path.dirname(__file__), db_file)
    db_exists = os.path.exists(db_path)
    inspector = inspect(engine)
    table_exists = inspector.has_table("emails")
    has_record = False
    if db_exists and table_exists:
        logger.info("Database and table exist, checking for records")
        session = SessionLocal()
        try:
            has_record = len(EMail.get_all()) > 0
        finally:
            session.close()

    client = mail.authenticate(imap_host, imap_port, imap_username, imap_password)

    try:
        if has_record:
            logger.info(
                "Database has existing records, retrieving emails since the most recent record"
            )
            most_recent_email: EMail = EMail.get_most_recent()
            logger.info(
                "Searching for emails since: %s", most_recent_email.delivery_date
            )
            emails = mail.get_emails_by_filter(
                client,
                from_email=from_email,
                subject=subject,
                since=most_recent_email.delivery_date,
            )
        else:
            logger.info("No existing records found, retrieving all emails")
            emails = mail.get_emails_by_filter(
                client, from_email=from_email, subject=subject
            )

        logger.info("Retrieved %d emails", len(emails))

        for email in emails:
            email.save()

        if backfill:
            events = []
            for email in EMail.get_all():
                events.append(await parse_email(email))
            logger.info("Backfilled events from all emails")
        else:
            most_recent_email = EMail.get_most_recent()
            logger.info("Parsing most recent email with id %s", most_recent_email.id)
            for event in await parse_email(most_recent_email):
                print(event)
            logger.info(
                "Parsed and saved events from most recent email with date %s",
                most_recent_email.delivery_date,
            )
        events = Event.get_all()

        caldav_url = settings.CALDAV_URL
        caldav_username = settings.CALDAV_USERNAME
        caldav_password = settings.IMAP_PASSWORD
        calendar_name = settings.CALDAV_CALENDAR

        add_to_caldav(
            caldav_url, caldav_username, caldav_password, calendar_name, events
        )

    except Exception as e:
        logger.error("An error occurred while retrieving emails: %s", e)
        raise e
    finally:
        client.logout()


if __name__ == "__main__":
    asyncio.run(main())
