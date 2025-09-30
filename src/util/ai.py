import asyncio
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openai import OpenAIProvider
from sqlmodel import select

from src import logger
from src.db import Session, engine
from src.model.email import EMail
from src.model.event import Event
from src.util.env import AIProvider, get_settings

DEFAULT_SYSTEM_PROMPT = """You are a personal assistant who receives emails and needs to parse through the contents of the email to create calendar events.
These are the rules you MUST follow:
- Every line that is not blank, a month, or a year should contain at least one event, but can contain multiple events
- Lines that aren't blank or an event(s) will either be a month or a year, use these to determine the date of the event(s) directly below it, until a new month or year is provided
- Event lines can contain a date, or a range of dates. If there is no date, assume the event date is the same as the event directly above it.
- Event lines can contain a time, or a range of times. If there is no time, assume the event lasts the entire day
- The date of the event is a number, usually at the start of the line, but can be anywhere in the line
- The date of the event can be a single day or multiple days
- The time of the event time can be anywhere in the line
- The time of the event can be in any of these formats: `12:50`, `6:30`, `9am` `820`, `130`, `8`, `10-12`, `10:30-12:30`, `9am-11am`, `9-11`, `9-11am`, `9am-11` or anything similar
- If there is no time, assume the event lasts the entire day, i.e., the start time is 00:00 and the end time is 23:59
- If there is no time or the event has a start time of `12:00am` or `00:00` and an end time of `11:59pm` or `23:59`, assume the event lasts the entire day, and set the `all_day` flag to true
- If the event spans multiple days, and only contains a start time assume the event starts at that time on the first day and ends at 23:59 on the last day
- If the event is a single day, and only contains a start time, assume the event starts at that time and ends one hour later
- The start and end date and time of the event should be in ISO 8601 format, e.g., `2023-10-15T14:30:00` or `2023-10-15T00:00:00` if the event lasts the entire day
- The summary of the event is the entire line
- The summary of the event should not contain any date and time information
- If the summary contains `cancelled` or anything similar, set the cancelled flag to true, otherwise set it to false
- Check, using the summary, if the event is present in the database assign the id attribute to the id of the event in the database, otherwise set it to null"""


@dataclass
class AgentDependencies:
    email: EMail
    max_result_retries: int = get_settings().AI_MAX_RETRIES
    db = Session(engine)


class Events(BaseModel):
    events: list[Event] = Field(description="A list of events parsed from the email")


async def parse_email(
    email: EMail,
    provider: AIProvider,
    model: str = "gpt-oss:20b",
    ollama_host: str = "localhost",
    ollama_port: int = 11434,
    ollama_secure: bool = False,
    open_ai_api_key: str = None,
    max_retries: int = 3,
    system_prompt: str = None,
) -> list[Event]:
    if provider == AIProvider.OLLAMA:
        logger.info(
            f"Creating events from email id {email.id}, using model: {model} at ollama host: {'https://' if ollama_secure else 'http://'}{ollama_host}:{ollama_port}"
        )
        ai_model = OpenAIChatModel(
            model_name=model,
            provider=OllamaProvider(
                base_url=f"{'https://' if ollama_secure else 'http://'}{ollama_host}:{ollama_port}/v1"
            ),
        )
    elif provider == AIProvider.OPENAI:
        logger.info(
            f"Creating events from email id {email.id}, using OpenAI model: {model}"
        )
        ai_model = OpenAIChatModel(
            model_name=model, provider=OpenAIProvider(api_key=open_ai_api_key)
        )
    else:
        raise ValueError(f"Unsupported AI provider: {provider}")

    deps = AgentDependencies(email=email)

    system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

    agent = Agent(
        ai_model,
        deps_type=AgentDependencies,
        output_type=Events,
        system_prompt=system_prompt,
        retries=max_retries,
    )

    @agent.system_prompt
    async def get_current_year(ctx: RunContext[AgentDependencies]):
        return f"If there is no year provided, use this year: {ctx.deps.email.delivery_date.year}"

    @agent.system_prompt
    async def get_email_id(ctx: RunContext[AgentDependencies]):
        return f"The email ID is {ctx.deps.email.id}. Use this ID for the email_id attribute of the event(s)."

    @agent.system_prompt
    async def get_events(ctx: RunContext[AgentDependencies]):
        logger.info("Checking existing events in the database...")
        events = ctx.deps.db.exec(select(Event)).all()
        logger.debug("Found %d existing events in the database", len(events))
        if not events:
            return "There are no current events in the database, assume all events are new."
        return f"The currents events in the database are: {events}"

    logger.info("Generating events...")
    start_time = datetime.now()

    task = asyncio.create_task(agent.run(email.body, deps=deps))
    while not task.done():
        logger.debug("Waiting for AI to finish generating events...")
        await asyncio.sleep(10)

    result = await task
    events: Events = result.output

    end_time = datetime.now()
    elapsed = (end_time - start_time).total_seconds()
    logger.info(
        f"Took {elapsed:.3f} seconds to generate {len(events.events)} events from email id: {email.id}"
    )
    return events.events
