from typing import Optional
from enum import Enum

from pydantic import (
    Field,
    ValidationError,
    AnyUrl,
    EmailStr,
)
from pydantic_settings import BaseSettings


class AIProvider(str, Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"


class Settings(BaseSettings):
    IMAP_HOST: str = Field(..., description="IMAP server host")
    # use int with Field constraints instead of conint to satisfy linters
    IMAP_PORT: int = Field(993, ge=1, le=65535, description="IMAP server port")
    IMAP_USERNAME: str = Field(..., description="IMAP username")
    IMAP_PASSWORD: str = Field(..., description="IMAP password")

    FILTER_FROM_EMAIL: Optional[EmailStr] = Field(
        None, description="Email address to filter messages from (optional)"
    )
    FILTER_SUBJECT: Optional[str] = Field(None, description="Subject filter (optional)")
    BACKFILL: bool = Field(False, description="Whether to backfill all emails")

    CALDAV_URL: AnyUrl = Field(..., description="CalDAV server URL")
    CALDAV_USERNAME: str = Field(..., description="CalDAV username")
    CALDAV_PASSWORD: str = Field(..., description="CalDAV password")
    CALDAV_CALENDAR: str = Field(..., description="CalDAV calendar name")

    AI_PROVIDER: AIProvider = Field(..., description="AI provider to use (ollama, openai, none)"
    )
    OLLAMA_URL: str = Field("http://localhost", description="Ollama base URL")
    OLLAMA_PORT: int = Field(11434, ge=1, le=65535, description="Ollama port")
    OLLAMA_MODEL: str = Field("gpt-oss:20b", description="Model to use for parsing")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        # Fail fast with a clear error so startup doesn't proceed with bad config
        raise SystemExit(f"Environment validation error:\n{exc}")
