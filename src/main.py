import os
from typing import List

from sqlalchemy import inspect

from src import db_file, logger
from src.util import text
from src.mail import mail
from src.db import Base, engine, SessionLocal
from src.model.email import EMail
from src.util.text import ParsedEvent


def main():
    logger.info("Starting email retrieval process")

    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)

    imap_host = os.environ["IMAP_HOST"]
    imap_port = int(os.environ["IMAP_PORT"])
    imap_username = os.environ["IMAP_USERNAME"]
    imap_password = os.environ["IMAP_PASSWORD"]

    from_email = os.environ["FILTER_FROM_EMAIL"]
    subject = os.environ["FILTER_SUBJECT"]
    backfill: bool = os.environ.get("BACKFILL", "false").lower() == "true"

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
            for email in EMail.get_all():
                events: list[Event] = event.parse_from_email(email)
                for event_obj in events:
                    event_obj.save()
            logger.info("Backfilled events from all emails")
        else:
            most_recent_email = EMail.get_most_recent()
            events: list[Event] = event.parse_from_email(most_recent_email)
            for event_obj in events:
                event_obj.save()
            logger.info(
                "Parsed and saved events from most recent email with date %s",
                most_recent_email.delivery_date,
            )
        events = Event.get_all()

        caldav_url = os.environ["CALDAV_URL"]
        caldav_username = os.environ["CALDAV_USERNAME"]
        caldav_password = os.environ["CALDAV_PASSWORD"]
        calendar_name = os.environ["CALDAV_CALENDAR"]

        add_to_caldav(
            caldav_url, caldav_username, caldav_password, calendar_name, events
        )

    except Exception as e:
        logger.error("An error occurred while retrieving emails: %s", e)
        raise e
    finally:
        client.logout()

    emails = EMail.get_all()
    for email in emails:
        content: List[ParsedEvent] = text.parse_email_events(email)
        print("--------------------------------------------------------")
        for event in content:
            print(event)
        print("--------------------------------------------------------")
        #events = event.parse_schedule_text(content, email.delivery_date, email.id)
        #for event_obj in events:
        #    print(event_obj)
        input("Press Enter to continue...")


if __name__ == "__main__":
    main()
