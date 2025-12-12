from dataclasses import dataclass
from enum import Enum

from bs4 import BeautifulSoup
import markdownify

from pydantic_ai import Agent, ModelSettings
from pydantic_ai.models import Model
from pydantic_ai.providers.openai import OpenAIProvider
from sqlalchemy.event import Events
from sqlalchemy.orm import Session

from src import logger


from pydantic import BaseModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

from src.db import engine
from src.model.email import EMail


class Credential(BaseModel):
    pass

class OllamaCredential(Credential):
    host: str
    port: int
    secure: bool = False

class DockerCredential(Credential):
    host: str = "model-runner.docker.internal"
    port: int = 80
    secure: bool = False

class OpenAICredential(Credential):
    api_key: str

class Provider(Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    DOCKER = "docker"

@dataclass
class AgentDependencies:
    email: EMail
    db = Session(engine)

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
    """.replace("{email_id}", str(email.id)).replace("{current_year}", str(email.delivery_date.year))

    failure_message = """If there are no events found within the context or the email, respond with an empty array: [].
    If you cannot parse an event line fully or are not 100% sure of the result, skip that line and do not include it in the output, it is better to miss an event than to include an incorrect one.
    If an event has an invalid `"start"`, `"end"`, skip that event and do not include it in the output."""

    output = f"""You must respond with a JSON array of objects, each object representing a calendar event with the following fields:
    - "start": The star" date of the event in ISO-8601 format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).
    - "end": The end date of the event in ISO-8601 format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).
    - "all_day": A boolean indicating whether the event is an all-day event (true) or has a specific time (false).
    - "summary": A brief summary or title of the event in Sentence case."""

    return f"{persona}\n\n{context}\n\n{failure_message}\n\n{output}"


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
        #max_tokens=131_072
    )
    if provider == Provider.OLLAMA:
        logger.debug("Building Ollama model")
        base_url = f"{'https://' if credential.secure else 'http://'}{credential.host}:{credential.port}/v1"
        logger.debug("Ollama base URL: %s", base_url)
        return OpenAIChatModel(
            model_name=model_name,
            provider=OllamaProvider(base_url=base_url),
            settings=settings
        )
    elif provider == Provider.OPENAI:
        logger.debug("Building OpenAI model")
        return OpenAIChatModel(
            model_name=model_name,
            provider=OpenAIProvider(api_key=credential.api_key),
            settings=settings
        )
    elif provider == Provider.DOCKER:
        logger.debug("Building Docker model")
        base_url = f"{'https://' if credential.secure else 'http://'}{credential.host}:{credential.port}/engines/v1"
        logger.debug("Docker base URL: %s", base_url)
        return OpenAIChatModel(
            model_name=model_name,
            provider=OllamaProvider(base_url=base_url),
            settings=settings
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
            f"The output must be in the following JSON schema: {Events.model_json_schema()}"
        ],
        retries=max_retries,
    )

    return agent
