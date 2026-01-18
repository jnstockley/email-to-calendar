import asyncio
import datetime
from datetime import timedelta

import sys

from dotenv import load_dotenv

from util.healthcheck import healthcheck
from util.logging import logger

from pydantic_ai.models import Model
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel

from src.events.caldav import add_to_caldav
from src.mail import mail
from src.db import engine
from src.model.ai import OpenAICredential, OllamaCredential, DockerCredential
from src.model.email import EMail, EMailType
from src.model.event import Event
from src.util import ai
from src.util.ai import (
    build_model,
    Provider,
    build_agent,
    AgentDependencies,
)
from src.util.env import get_settings, Settings
from src.util.notifications import send_success_notification, send_failure_notification


def create_model(settings: Settings) -> Model:
    if settings.AI_PROVIDER == Provider.DOCKER:
        credential = DockerCredential(
            host=settings.HOST,
            port=settings.PORT,
            secure=settings.SECURE,
        )
    elif settings.AI_PROVIDER == Provider.OLLAMA:
        credential = OllamaCredential(
            host=settings.HOST,
            port=settings.PORT,
            secure=settings.SECURE,
        )
    elif settings.AI_PROVIDER == Provider.OPENAI:
        credential = OpenAICredential(
            api_key=settings.OPEN_AI_API_KEY,
        )
    else:
        logger.error("Unsupported AI provider: %s", settings.AI_PROVIDER)
        raise ValueError(f"Unsupported AI provider: {settings.AI_PROVIDER}")

    return build_model(
        settings.AI_PROVIDER,
        settings.AI_MODEL,
        credential,
    )


async def generate_events_from_email(
    email: EMail, settings: Settings, model: Model
) -> list[Event]:
    logger.info("Generating events from email id %d", email.id)
    if email.email_type == EMailType.HTML:
        logger.debug("Converting HTML email to Markdown for email id %d", email.id)
        email.body = ai.html_to_md(email.body)

    agent = build_agent(model, email, settings.AI_MAX_RETRIES)

    deps = AgentDependencies(email=email)

    results = await agent.run(email.body, deps=deps)
    events: list[Event] = results.output.events

    # update the type for `start` and `end` to be datetime objects
    for event in events:
        if isinstance(event.start, str):
            event.start = datetime.datetime.fromisoformat(event.start)
        if isinstance(event.end, str):
            event.end = datetime.datetime.fromisoformat(event.end)

    return events


async def schedule_run(task_coro, interval_seconds: int):
    while True:
        logger.info("Checking for new emails to process...")
        start = asyncio.get_event_loop().time()
        try:
            await task_coro()
        except Exception:
            logger.exception("Unhandled exception in scheduled run")
        elapsed = asyncio.get_event_loop().time() - start
        sleep_for = max(0, int(interval_seconds - elapsed))
        logger.info("Sleeping for %.2f seconds before next run", sleep_for)
        await asyncio.sleep(sleep_for)


async def main(settings: Settings):
    logger.info("Starting email retrieval process")

    # Create tables if they don't exist
    SQLModel.metadata.create_all(engine)

    client = mail.authenticate(settings)
    try:
        most_recent_email: EMail = EMail.get_most_recent()

        if most_recent_email:
            logger.info(
                "Searching for emails since: %s",
                most_recent_email.delivery_date + timedelta(seconds=1),
            )

            emails = mail.get_emails_by_filter(
                client,
                settings,
                since=most_recent_email.delivery_date + timedelta(seconds=1),
            )
        else:
            emails = mail.get_emails_by_filter(client, settings)
    except Exception as e:
        logger.error("An error occurred while retrieving emails", e)
        raise e
    finally:
        client.logout()

    if not settings.BACKFILL:
        emails = emails[-1:] if emails else []

    logger.info("Retrieved %d emails", len(emails))

    model = create_model(settings)

    processed_email_ids = {email.id for email in EMail.get_all()}
    emails = [email for email in emails if email.id not in processed_email_ids]

    if emails:
        for email in emails:
            logger.info("Starting to process email with id %d", email.id)
            start_time = datetime.datetime.now()
            try:
                email.save()
                if not email.body:
                    logger.warning("Email id %d has no body, skipping", email.id)
                    continue
                events: list[Event] = await generate_events_from_email(
                    email, settings, model
                )
                event_objs: list[Event] = []
                for event in events:
                    logger.info(
                        "Saving event '%s' from email id %d", event.summary, email.id
                    )
                    event.email_id = email.id

                    try:
                        event = event.save()
                        event_objs.append(event)
                    except IntegrityError:
                        logger.warning(
                            "Event '%s' from email id %d already exists in the database, skipping",
                            event.summary,
                            email.id,
                        )
                logger.debug(
                    "Generated the following events from email id %d: %s",
                    email.id,
                    event_objs,
                )
                add_to_caldav(
                    settings.CALDAV_URL,
                    settings.CALDAV_USERNAME,
                    settings.CALDAV_PASSWORD,
                    settings.CALDAV_CALENDAR,
                    event_objs,
                )
                send_success_notification(settings.APPRISE_URL, event_objs)

            except Exception as e:
                error_message = f"Error generating events from email id {email.id}"
                logger.error(error_message, e)
                send_failure_notification(settings.APPRISE_URL, error_message)
            finally:
                end_time = datetime.datetime.now()
                duration = (end_time - start_time).total_seconds()
                logger.info(
                    "Processing of email id %d completed in %.2f seconds",
                    email.id,
                    duration,
                )
    else:
        logger.info("No new emails to process.")


if __name__ == "__main__":
    load_dotenv()
    if len(sys.argv) > 1 and sys.argv[1] == "healthcheck":
        healthcheck()
    else:
        settings = get_settings()
        try:
            asyncio.run(
                schedule_run(
                    lambda: main(settings),
                    interval_seconds=settings.INTERVAL_MINUTES * 60,
                )
            )
        except KeyboardInterrupt:
            logger.info("Program interrupted by user, shutting down.")
