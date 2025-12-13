import asyncio
import datetime
from datetime import timedelta

from pydantic_ai.models import Model
from sqlmodel import SQLModel

from src import logger
from src.events.caldav import add_to_caldav
from src.mail import mail
from src.db import engine
from src.model.ai import OpenAICredential, OllamaCredential, DockerCredential
from src.model.email import EMail
from src.model.event import Event
from src.util import ai
from src.util.ai import build_model, Provider, build_agent, AgentDependencies
from src.util.env import get_settings, Settings
from src.util.notifications import send_success_notification, send_failure_notification


def create_model(settings: Settings) -> Model:
    if settings.AI_PROVIDER == Provider.DOCKER:
        credential = DockerCredential(
            host=settings.DOCKER_HOST,
            port=settings.DOCKER_PORT,
            secure=settings.DOCKER_SECURE,
        )
    elif settings.AI_PROVIDER == Provider.OLLAMA:
        credential = OllamaCredential(
            host=settings.OLLAMA_HOST,
            port=settings.OLLAMA_PORT,
            secure=settings.OLLAMA_SECURE,
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
    if email.email_type == "html":
        logger.debug("Converting HTML email to Markdown for email id %d", email.id)
        email.body = ai.html_to_md(email.body)

    agent = build_agent(model, email, settings.AI_MAX_RETRIES)

    deps = AgentDependencies(email=email)

    results = await agent.run(email.body, deps=deps)
    return results.output.events


async def schedule_run(task_coro, interval_seconds: int):
    while True:
        start = asyncio.get_event_loop().time()
        try:
            await task_coro()
        except Exception:
            logger.exception("Unhandled exception in scheduled run")
        elapsed = asyncio.get_event_loop().time() - start
        sleep_for = max(0, int(interval_seconds - elapsed))
        await asyncio.sleep(sleep_for)


async def main():
    logger.info("Starting email retrieval process")
    settings = get_settings()

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

    for email in emails:
        logger.info("Starting to process email with id %d", email.id)
        start_time = datetime.datetime.now()
        try:
            if not email.body:
                logger.warning("Email id %d has no body, skipping", email.id)
                continue
            events: list[Event] = await generate_events_from_email(
                email, settings, model
            )
            logger.debug(
                "Generated the following events from email id %d: %s", email.id, events
            )
            email.save()
            add_to_caldav(
                settings.CALDAV_URL,
                settings.CALDAV_USERNAME,
                settings.CALDAV_PASSWORD,
                settings.CALDAV_CALENDAR_NAME,
                events,
            )
            send_success_notification(settings.APPRISE_URL, events)
        except Exception as e:
            error_message = f"Error generating events from email id {email.id}\n{e}"
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


if __name__ == "__main__":
    asyncio.run(schedule_run(main, interval_seconds=300))
