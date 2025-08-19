import os
from sqlalchemy import inspect

from src import db_file, logger
from src.mail import mail
from src.db import Base, engine, SessionLocal
from src.model.email import EMail


def main():
    logger.info("Starting email retrieval process")

    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)

    host = os.environ["IMAP_HOST"]
    port = int(os.environ["IMAP_PORT"])
    username = os.environ["IMAP_USERNAME"]
    password = os.environ["IMAP_PASSWORD"]

    from_email = os.environ["FILTER_FROM_EMAIL"]
    subject = os.environ["FILTER_SUBJECT"]
    # backfill: bool = os.environ.get("FILTER_BACKFILL", "false").lower() == "true"

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

    client = mail.authenticate(host, port, username, password)

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
    except Exception as e:
        logger.error("An error occurred while retrieving emails: %s", e)
        raise e
    finally:
        client.logout()


if __name__ == "__main__":
    main()
