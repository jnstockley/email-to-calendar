import asyncio
import datetime
import os
import time

from sqlalchemy import inspect
from sqlmodel import SQLModel

from src import db_file, logger
from src.events.caldav import add_to_caldav
from src.mail import mail
from src.db import Session, engine
from src.model.email import EMail
from src.model.event import Event
from src.util.ai import parse_email
from src.util.env import get_settings, Settings
from src.util.notifications import send_success_notification


async def populate_events(settings: Settings):
    backfill = settings.BACKFILL
    provider = settings.AI_PROVIDER
    model = settings.AI_MODEL
    ollama_host = settings.OLLAMA_HOST
    ollama_port = settings.OLLAMA_PORT
    ollama_secure = settings.OLLAMA_SECURE
    open_ai_api_key = settings.OPEN_AI_API_KEY
    max_retries = settings.AI_MAX_RETRIES
    system_prompt = settings.AI_SYSTEM_PROMPT

    if backfill:
        logger.info("Backfilling events from all emails without events")
        for email in EMail.get_without_events():
            events = await parse_email(
                email,
                provider,
                model,
                ollama_host,
                ollama_port,
                ollama_secure,
                open_ai_api_key,
                max_retries,
                system_prompt,
            )
            for event in events:
                logger.debug(f"Backfilling event: {event}")
                try:
                    event.save()
                except Exception as e:
                    logger.error(f"Error saving event {event}: {e}", exc_info=True)
                    for e in events:
                        e.delete()
        logger.info("Backfilled events from all emails")
    else:
        most_recent_email = EMail.get_most_recent_without_events()
        if most_recent_email:
            logger.info("Parsing most recent email with id %s", most_recent_email.id)
            events = await parse_email(
                most_recent_email,
                provider,
                model,
                ollama_host,
                ollama_port,
                ollama_secure,
                open_ai_api_key,
                max_retries,
                system_prompt,
            )
            for event in events:
                logger.debug(f"Saving event: {event}")
                try:
                    event.save()
                except Exception as e:
                    logger.error(f"Error saving event {event}: {e}", exc_info=True)
                    for e in events:
                        e.delete()
            logger.info(
                "Parsed and saved events from most recent email with date %s",
                most_recent_email.delivery_date,
            )
        else:
            logger.info("No new emails without events to parse")

    events = Event.get_not_in_calendar()

    caldav_url = settings.CALDAV_URL
    caldav_username = settings.CALDAV_USERNAME
    caldav_password = settings.CALDAV_PASSWORD
    calendar_name = settings.CALDAV_CALENDAR

    if events:
        logger.info("Adding %d new events to CalDAV calendar", len(events))
        add_to_caldav(
            caldav_url, caldav_username, caldav_password, calendar_name, events
        )
        if settings.APPRISE_URL:
            send_success_notification(settings.APPRISE_URL, events)


def main():
    logger.info("Starting email retrieval process")
    settings = get_settings()

    # Create tables if they don't exist
    SQLModel.metadata.create_all(engine)

    imap_host = settings.IMAP_HOST
    imap_port = settings.IMAP_PORT
    imap_username = settings.IMAP_USERNAME
    imap_password = settings.IMAP_PASSWORD
    mailbox = settings.IMAP_MAILBOX
    ssl = settings.IMAP_SSL

    from_email = settings.FILTER_FROM_EMAIL
    subject = settings.FILTER_SUBJECT

    db_path = os.path.join(os.path.dirname(__file__), db_file)
    db_exists = os.path.exists(db_path)
    inspector = inspect(engine)
    table_exists = inspector.has_table("email")
    has_record = False
    if db_exists and table_exists:
        logger.info("Database and table exist, checking for records")
        session = Session(engine)
        try:
            has_record = len(EMail.get_all()) > 0
        finally:
            session.close()

    client = mail.authenticate(imap_host, imap_port, imap_username, imap_password, ssl)

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
                mailbox=mailbox,
            )
        else:
            logger.info("No existing records found, retrieving all emails")
            emails = mail.get_emails_by_filter(
                client, from_email=from_email, subject=subject
            )

        logger.info("Retrieved %d emails", len(emails))

        for email in emails:
            email.save()

        while True:
            logger.info("Starting event population process...")
            start_time = datetime.datetime.now()
            try:
                asyncio.run(populate_events(settings))
            except Exception as e:
                logger.error("Error populating events: %s", e, e)
            finally:
                end_time = datetime.datetime.now()
                duration = (end_time - start_time).total_seconds()
                logger.info(
                    "Event population process completed in %.2f seconds", duration
                )
                sleep_duration = settings.INTERVAL_MINUTES * 60
                remaining_time = max(0, sleep_duration - int(duration))
                logger.info("Sleeping for %d seconds", remaining_time)
                time.sleep(remaining_time)

    except Exception as e:
        logger.error("An error occurred while retrieving emails: %s", e)
        raise e
    finally:
        client.logout()


if __name__ == "__main__":
    main()
