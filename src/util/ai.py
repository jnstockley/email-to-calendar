from dataclasses import dataclass

from bs4 import BeautifulSoup
import markdownify
from pydantic import BaseModel, Field

from pydantic_ai import Agent, ModelSettings, RunContext
from pydantic_ai.models import Model
from pydantic_ai.providers.openai import OpenAIProvider
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from util.logging import logger

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

from src.db import engine
from src.model.ai import Provider, Credential
from src.model.email import EMail
from src.model.event import Event


@dataclass
class AgentDependencies:
    email: EMail
    db = Session(engine)


class Events(BaseModel):
    events: list[Event] = Field(description="A list of events parsed from the email")


def html_to_md(html: str) -> str:
    """
    Convert HTML content to Markdown format.
    :param html: The HTML content to convert.
    :return: The converted Markdown content.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = str(soup)
    md = markdownify.markdownify(text, heading_style="ATX")
    return md


def get_system_prompt(email: EMail) -> str:
    persona = """Act as a high level personal assistant for a C level executive who's main responsibility is managing 
    their calendar and scheduling meetings from emails they receive."""

    context = """You are going to parse emails, that are in markdown format, and extract calendar events from them.
    The `email_id` is {email_id}, use this for ALL events you extract from this email.
    If there is a FOUR DIGIT year, before any month i.e, 2023, use that year for all dates, otherwise use the current year is {current_year}.
    There can be a heading that is a short of long month name i.e., 'Oct' or 'October' on a new line
    Subsequent lines can can contain a date number or a range of dates, i.e, 22-23 or 24
    After the date or date range, there CAN be an OPTIONAL time, i.e., 11 am or 2:50, or 12, these must be converted into ISO-8601 strings.
    After OPTIONAL time, there will be a summary of the event, this must be formatted in `Sentence case`.
    After an event, there CAN be an 0 or more lines that are the same as the above line. If there is no DATE this should take the date of the last event, otherwise it has a new date.
    There can then be 0 or more new lines, before the next month heading, and the same rules apply.
    If the months loops, i.e, the previous month was before or December and the new month is January or later, increment the year by 1.
    Here is an example of the format:
        INPUT:
            **October**  
            22-23 Mum/Dad Gwen Chicago  
            24 Katie Drs
            
            **November**
            
            9 2pm Mark Dudley  
            
            19-27 Jack/Cam Thanksgiving
            
            25 11 am Nurse Phone Call Mark Gastro
            
            26 Family+Nana Tallgrass 6pm
            
            *2024*
            **January**  
            3 2:50 Dentist Cam CANCELLED - on wait list
        OUTPUT:
        [{
            "start": "2023-10-22",
            "end": "2023-10-23",
            "all_day": true,
            "summary": Mum/Dad Gwen Chicago
        },
        {
            "start": "2023-10-24",
            "end": "2023-10-24",
            "all_day": true,
            "summary": "Katie Drs"
        },
        {
            "start": "2023-11-09T14:00:00",
            "end": "2023-11-09T15:00:00",
            "all_day": false,
            "summary": "Mark Dudley"
        },
        {
            "start": "2023-11-19",
            "end": "2023-11-27",
            "all_day": true,
            "summary": "Jack/Cam Thanksgiving"
        },
        {
            "start": "2023-11-25T11:00:00",
            "end": "2023-11-25T12:00:00",
            "all_day": false,
            "summary": "Nurse Phone Call Mark Gastro"
        },
        {
            "start": "2023-11-26T18:00:00",
            "end": "2023-11-26T19:00:00",
            "all_day": false,
            "summary": "Family+Nana Tallgrass"
        },
        {
            "start": "2024-01-03T14:50:00",
            "end": "2024-01-03T15:50:00",
            "all_day": false,
            "summary": "Dentist Cam CANCELLED - on wait list"
        }]]
    """.replace("{email_id}", str(email.id)).replace(
        "{current_year}", str(email.delivery_date.year)
    )

    tools = """You have the following tools available to you:
   
    # get_current_email_delivery_date
        - Description: Get the delivery date of the email being processed
        - Input: None
        - Output: A string representing the email delivery date in ISO-8601 format (YYYY-MM-DDTHH:MM:SS)
        
    # get_delivery_date_by_event
        - Description: Get the delivery date of an email by its event's email ID
        - Input: The event to find the delivery date for
        - Output: A string representing the email delivery date in ISO-8601 format (YYYY-MM-DDTHH:MM:SS) or null if the email ID does not exist"""

    '''# save_event
        - Description: Save the event to the database
        - Input: The event object to save
        - Output: A boolean indicating whether the save was successful, true if successful, false otherwise
        - Note: This tool MUST be called for each event you return to ensure it is saved in the database. If the tool returns false, the event already exists and was not saved, following the matching rules to update the event.
        
    # get_events
        - Description: Get all existing events from the database
        - Input: None
        - Output: A list of existing event objects or null if no events exist
        - Note: This tool MUST be called after each `save_event` call to get the most up-to-date list of events in the database, and to avoid duplicate events.
    """'''

    matching = """An event is considered a duplicate if the summary has a similar meaning and the `start` and `end` fields are around the same time.
        Example: Jack dentist and dentist appointment for Jack are considered similar.
        Example: An event on 2023-10-22 and another on 2023-10-23, both with the summary of `Jack dentist` are considered around the same time.
        Example: An event on 2023-10-22T10:00:00 and another on 2024-10-22T11:00:00, both with the summary of `Jack dentist` are NOT considered around the same time.
    If you find a similar event, make sure the `event.id` has the same value as the existing event in the database.
    Use the `get_delivery_date_by_event` tool to get the delivery date of the existing using the existing event's id. This tool MUST be run for each existing event found.
    Use the `get_current_email_delivery_date` tool to get the delivery date of the current. This tool MUST be run once if any existing events are found.
    Whichever delivery date is the most recent, use that event's `summary`, `start`, `end`, and `email_id` when returning the event.
    If there is no existing event found, set the `id` to `None`."""

    assumptions = """These are the following assumptions you are allowed to make when parsing the email:
    - If an event spans multiple days, it is an all-day event."""

    failure_message = """If there are no events found within the context or the email, respond with an empty array: [].
    If you cannot parse an event line fully or are not 100% sure of the result, skip that line and do not include it in the output, it is better to miss an event than to include an incorrect one.
    If an event has an invalid `"start"`, `"end"`, skip that event and do not include it in the output."""

    output = """You must respond with a JSON array of objects, each object representing a calendar event with the following fields:
    - "start": The star" date of the event in ISO-8601 format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).
    - "end": The end date of the event in ISO-8601 format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).
    - "all_day": A boolean indicating whether the event is an all-day event (true) or has a specific time (false).
    - "summary": A brief summary or title of the event in Sentence case."""

    return f"{persona}\n\n{context}\n\n{tools}\n\n{matching}\n\n{assumptions}\n\n{failure_message}\n\n{output}"


def get_cleanup_system_prompt() -> str:
    persona = """Act as a high level personal assistant for a C level executive who's main responsibility is managing 
        their calendar and ensuring there are no duplicate events."""

    task = """You will be provided A JSON representation of events within their calendar. You must identity any 
    duplicate events, determine the correct event to keep, based on when the event was created, and return a JSON array of the event(s) to delete."""

    failure_message = """If there are no duplicate events found within the context, respond with an empty array: [].
    If you cannot determine which event to delete, skip that event and do not include it in the output, it is better to miss an event than to delete the wrong one."""

    output = """You must respond with a JSON array of objects, each object representing a calendar event with the following fields:
        - "start": The star" date of the event in ISO-8601 format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).
        - "end": The end date of the event in ISO-8601 format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).
        - "all_day": A boolean indicating whether the event is an all-day event (true) or has a specific time (false).
        - "summary": A brief summary or title of the event in Sentence case."""

    return f"{persona}\n\n{task}\n\n{failure_message}\n\n{output}"


def build_model(provider: Provider, model_name: str, credential: Credential) -> Model:
    """
    Build and return an AI model based on the specified provider, model name, and credentials.
    :param provider: The AI provider to use (OLLAMA, OPENAI, DOCKER).
    :param model_name: The name of the model to use.
    :param credential: The credentials required for the specified provider.
    :return: An instance of the specified AI model.
    :raises ValueError: If the specified provider is unsupported.
    """
    settings = ModelSettings(
        temperature=0.2,
    )
    if provider == Provider.OLLAMA:
        logger.debug("Building Ollama model")
        base_url = f"{'https://' if credential.secure else 'http://'}{credential.host}:{credential.port}/v1"
        logger.debug("Ollama base URL: %s", base_url)
        return OpenAIChatModel(
            model_name=model_name,
            provider=OllamaProvider(base_url=base_url),
            settings=settings,
        )
    elif provider == Provider.OPENAI:
        logger.debug("Building OpenAI model")
        return OpenAIChatModel(
            model_name=model_name,
            provider=OpenAIProvider(api_key=credential.api_key),
            settings=settings,
        )
    elif provider == Provider.DOCKER:
        logger.debug("Building Docker model")
        base_url = f"{'https://' if credential.secure else 'http://'}{credential.host}:{credential.port}/engines/v1"
        logger.debug("Docker base URL: %s", base_url)
        return OpenAIChatModel(
            model_name=model_name,
            provider=OllamaProvider(base_url=base_url),
            settings=settings,
        )
    else:
        raise ValueError(f"Unsupported provider: {provider}")


def build_agent(model: Model, email: EMail, max_retries: int = 3) -> Agent:
    """
    Build and return an AI agent using the specified model.
    :param model: The AI model to use for the agent.
    :return: An instance of the AI agent.
    """
    logger.debug("Building AI agent")
    agent = Agent(
        model,
        deps_type=AgentDependencies,
        output_type=Events,
        system_prompt=[
            get_system_prompt(email),
            f"The output must be in the following JSON schema: {Event.model_json_schema()}",
        ],
        retries=max_retries,
    )

    @agent.system_prompt()
    async def get_current_events(ctx: RunContext[AgentDependencies]):
        logger.info("Calling get_current_events system prompt")
        events = Event.get_all()
        if events:
            logger.debug("Current events in database: %s", events)
            return (
                f"These events are already in the database. If a new event has a similar summary, use the "
                f"`get_email_delivery_date` tool to determine which event is the most recent, and use the newer event "
                f"`summary`, `start`, `end`, `id`, and `email_id` when returning the event.\nCurrent events: {events}"
            )
        logger.debug("No current events in database")
        return "There are no events currently in the database, so all parsed events are new."

    @agent.tool()
    async def get_events(ctx: RunContext[AgentDependencies]) -> list[Event] | None:
        logger.info("Calling get_events tool")
        events = Event.get_all()
        if events:
            logger.debug("Found events: %s", events)
            return events
        logger.debug("No events found")
        return None

    @agent.tool()
    async def get_delivery_date_by_event(
        ctx: RunContext[AgentDependencies], event_id: int
    ) -> str | None:
        logger.info(f"Calling get_delivery_date_by_event tool for event: {event_id}")
        event = Event.get_by_id(event_id)
        if not event:
            logger.debug("No event found with id: %d", event_id)
            return None
        email = EMail.get_by_id(event.email_id)
        if email:
            logger.debug("Found email: %s", email)
            return email.delivery_date.isoformat()
        logger.debug("No email found with id: %d", event.email_id)
        return None

    @agent.tool()
    async def get_current_email_delivery_date(
        ctx: RunContext[AgentDependencies],
    ) -> str:
        logger.info("Calling get_current_email_delivery_date tool")
        email: EMail = ctx.deps.email
        logger.debug("Current email delivery date: %s", email.delivery_date)
        return email.delivery_date.isoformat()

    @agent.tool()
    async def save_event(ctx: RunContext[AgentDependencies], event: Event) -> bool:
        logger.info(f"Calling save_event tool for event: {event}")
        try:
            if event.id == 0:
                event.id = None
            event.save()
            return True
        except IntegrityError as e:
            logger.error(f"IntegrityError while saving event: {e}")
            if (
                ctx.deps.email.id != event.email_id
                and ctx.deps.email.delivery_date
                > EMail.get_by_id(event.email_id).delivery_date
            ):
                existing_event = Event.find_unique_event(
                    event.start, event.end, event.summary
                )
                if existing_event:
                    event.id = existing_event.id
                    event.save()
                    return True
            return False

    """@agent.tool()
    async def merge_event(ctx: RunContext[AgentDependencies], event: Event) -> Event:
        logger.info(f"Calling merge_event tool for event: {event}")
        return event"""

    return agent
