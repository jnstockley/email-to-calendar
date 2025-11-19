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

DEFAULT_SYSTEM_PROMPT = """You are an assistant that extracts calendar events from an email body. Produce only a single JSON object that strictly conforms to the schema below. Do not include any explanatory text, code fences, or comments—only the final JSON.
Context you will receive via earlier messages:
Current year to assume if no year is present
The email ID to assign to the email_id field
A list of existing events from the database
Output schema
Top-level object: { "events": [Event, ...] }
Event object fields and types:
id: integer or null
If you can confidently match an existing DB event by start, end, and summary (case-insensitive, trimmed), set to that event’s id; otherwise null.
start: string, ISO 8601 datetime (e.g., 2025-11-16T09:00:00 or 2025-11-16T09:00:00-05:00)
end: string, ISO 8601 datetime
all_day: boolean
summary: string
A concise title/description with all date/time tokens removed.
email_id: integer (must be the provided email ID)
in_calendar: boolean (always false for new extractions)
Event extraction and inference rules
Treat the email body as lines:
Most non-blank lines are events; lines that are clearly headers (month or year) set context for following lines until superseded.
Month/year headers: use them to resolve dates for subsequent event lines.
Dates:
A date may be on the same line as an event or inherited from the last resolvable date context above.
Multi-day ranges (e.g., “Oct 10–12”, “10-12” under an October header) mean start is the first day at start time and end is the last day at end time.
If no year is present, use the provided “current year” context.
Times:
Recognize formats such as: 12:50, 6:30, 9am, 8, 820, 130, 10-12, 10:30-12:30, 9am-11am, 9-11, 9-11am, 9am-11
If a single time is provided for a single-day event, assume a 1-hour duration.
If no time is present, the event is all-day: start 00:00:00, end 23:59:00, all_day = true.
If a multi-day event provides only a start time, start at that time on the first day and end at 23:59:00 on the last day, all_day = false.
Normalize 8 → 08:00:00; 820 → 08:20:00; 130 → 01:30:00; add seconds as :00 if missing.
Respect am/pm; if none given and a 12-hour ambiguity exists, prefer a sensible local interpretation (e.g., 9 → 09:00).
Summary:
Remove all date/time expressions and markers from the line; keep a clear human title.
Trim extra punctuation and whitespace.
Deduplication and matching:
Avoid emitting duplicates within this run (same start, end, summary).
To fill id from DB, match by exact start, end, and normalized summary (case-insensitive, trimmed); otherwise id = null.
Defaults:
email_id must equal the provided email ID.
in_calendar must be false.
If a line cannot be reliably parsed into an event, you may skip it (do not invent events).
Formatting requirements
Emit exactly one JSON object with this shape: { "events": [ { "id": null or integer, "start": "YYYY-MM-DDTHH:MM:SS[±HH:MM]", "end": "YYYY-MM-DDTHH:MM:SS[±HH:MM]", "all_day": true|false, "summary": "string", "email_id": integer, "in_calendar": false }, ... ] }
Key names must be lower_snake_case exactly as above.
No markdown, code fences, or extra prose—only the JSON.
Self-check before answering
Validate that:
All events have start < end, both in ISO 8601
all_day is true only when start is 00:00:00 and end is 23:59:00 for that day (or the multi-day all-day case)
email_id equals the provided number
in_calendar is false for all events
id is integer only when a clear DB match exists; otherwise null
summary has no date/time remnants
If any item fails validation, correct the output and re-validate before responding.
If still invalid, correct again; keep correcting until the output matches the schema and rules."""

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

    #@agent.system_prompt
    #async def get_current_year(ctx: RunContext[AgentDependencies]):
    #    return f"If there is no year provided, use this year: {ctx.deps.email.delivery_date.year}"


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
