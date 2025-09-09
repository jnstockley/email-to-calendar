import asyncio
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

from src import logger
from src.model.email import EMail

DEFAULT_SYSTEM_PROMPT = """You are a personal assistant who receives emails and needs to parse through the contents of the email to create calendar events.
You will parse the email and the event(s) from top to bottom. Every line, that is not blank, is a month, or a year, should contain at least one event.
You must return the a list of events, even if they are no events or just one event.
These are STRICT rule that you MUST follow when parsing the events:
- The start of the email with either contain a year, which all following events should take place in, or if no year is provided you will use this year: {current_year}
- The next line will contain a month, which all following events should take place in, until a new month is provided
- The following line(s) will contain the event(s) for that month, until a new month or year is provided
- When generating the even summary, you can alter it, but only to remove any date ot time information, or any information that relates to when the event is happening, like `week ok` or similar
- Date information can either be a single day of the month, or a range of days
- Time information can either be just an hour, an hour and minute, with/without `:` or `.` separator, with/without am/pm, or a range of times
- Time information can be any of theses formats: `12:50`, `6:30`, `9am` `820`, `130`, `8`, `10-12`, `10:30-12:30`, `9am-11am`, `9-11`, `9-11am`, `9am-11` or anything similar
- Time information can be present anywhere in the event line
- If there is no time information, assume the event lasts the entire day, i.e., the start time is 00:00 and the end time is 23:59
- Events can be cancelled, if the event contains `cancelled` or anything similar, set the cancelled flag to true, otherwise set it to false
- If an event spans multiple days, and only contains a single time, assume the event is all-day
- Make sure the event summary does not contain any date or time information or day of the week information

You are only to return the structured output, do not return any other text, and ensure the output is valid JSON that matches the schema provided.
"""

@dataclass
class AgentDependencies:
    email: EMail
    max_result_retries: int = 3

class Event(BaseModel):
    summary: str = Field(description="The name of the event, not including any date or time information")
    start_date: datetime = Field(description="The start date and time of the event, if no time is provided assume the event lasts the entire day")
    end_date: datetime = Field(description="The end date and time of the event, if no time is provided assume the event lasts the entire day")
    cancelled: bool = Field(description="Whether the event is cancelled or not")

    def __str__(self):
        return f"{self.summary} {self.start_date} -> {self.end_date} {self.cancelled}"

class Events(BaseModel):
    events: list[Event] = Field(description="A list of events parsed from the email")

async def parse_email(email: EMail, model: str = "gpt-oss:20b", ollama_url: str = "http://localhost", ollama_port: int = 11434, max_retries: int = 3):
    logger.info(f"Creating events from email id {email.id}, using model: {model} at ollama host: {ollama_url}:{ollama_port}")
    ollama = OpenAIChatModel(
        model_name=model,
        provider=OllamaProvider(base_url=f'{ollama_url}:{ollama_port}/v1'),
    )

    deps = AgentDependencies(email=email)

    agent = Agent(
        ollama,
        deps_type=AgentDependencies,
        output_type=Events,
        system_prompt=DEFAULT_SYSTEM_PROMPT.replace("{current_year}", str(email.delivery_date.year)),
        retries=max_retries
    )

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
    logger.info(f"Took {elapsed:.3f} seconds to generate {len(events.events)} events from email id: {email.id}")
    return events.events
