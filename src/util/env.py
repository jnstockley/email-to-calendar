from pathlib import Path
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
    IMAP_HOST: str = Field(default=None, description="IMAP server host")
    IMAP_PORT: int = Field(993, ge=1, le=65535, description="IMAP server port")
    IMAP_USERNAME: str = Field(default=None, description="IMAP username")
    IMAP_PASSWORD: str = Field(default=None, description="IMAP password")
    IMAP_MAILBOX: str = Field("INBOX", description="IMAP mailbox to check")
    IMAP_SSL: bool = Field(True, description="Whether to use SSL for IMAP connection")

    FILTER_FROM_EMAIL: Optional[EmailStr] = Field(
        None, description="Email address to filter messages from (optional)"
    )
    FILTER_SUBJECT: Optional[str] = Field(None, description="Subject filter (optional)")
    BACKFILL: bool = Field(False, description="Whether to backfill all emails")
    INTERVAL_MINUTES: int = Field(
        15, ge=1, description="Interval in minutes to check for new emails"
    )

    CALDAV_URL: AnyUrl = Field(default=None, description="CalDAV server URL")
    CALDAV_USERNAME: str = Field(default=None, description="CalDAV username")
    CALDAV_PASSWORD: str = Field(default=None, description="CalDAV password")
    CALDAV_CALENDAR: str = Field(default=None, description="CalDAV calendar name")

    AI_PROVIDER: AIProvider = Field(
        default=None, description="AI provider to use (ollama, openai, none)"
    )

    OLLAMA_SECURE: bool = Field(
        False, description="Whether to use HTTPS for Ollama connection"
    )
    OLLAMA_HOST: str = Field("localhost", description="Ollama base URL")
    OLLAMA_PORT: int = Field(11434, ge=1, le=65535, description="Ollama port")

    OPEN_AI_API_KEY: Optional[str] = Field(
        None, description="OpenAI API key (required if AI_PROVIDER is openai)"
    )

    AI_MODEL: str = Field(default=None, description="Model to use for parsing")
    AI_MAX_RETRIES: int = Field(3, ge=0, description="Maximum retries for AI parsing")

    AI_SYSTEM_PROMPT: Optional[str] = Field(
        None, description="Custom system prompt for the AI model (optional)"
    )
    AI_SYSTEM_PROMPT_FILE: Optional[str] = Field(
        None, description="Custom system prompt for the AI model (optional)"
    )

    DB_FILE: str = Field(f"{Path.cwd()}/data/emails.db", description="SQLite database file path")

    APPRISE_URL: Optional[AnyUrl] = Field(
        None, description="Apprise notification service URL (optional)"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


def get_settings() -> Settings:
    try:
        settings = Settings()
        if settings.AI_PROVIDER == AIProvider.OLLAMA and not settings.AI_MODEL:
            settings.AI_MODEL = "gpt-oss:20b"
            assert settings.OLLAMA_HOST is not None
            assert settings.OLLAMA_PORT is not None
        elif settings.AI_PROVIDER == AIProvider.OPENAI and not settings.AI_MODEL:
            settings.AI_MODEL = "gpt-5-mini"
            assert settings.OPEN_AI_API_KEY is not None

        if settings.AI_SYSTEM_PROMPT_FILE:
            try:
                with open(settings.AI_SYSTEM_PROMPT_FILE, "r") as f:
                    settings.AI_SYSTEM_PROMPT = f.read()
            except Exception as e:
                raise ValueError(f"Error reading system prompt file: {e}")
        return settings
    except ValidationError as exc:
        # Fail fast with a clear error so startup doesn't proceed with bad config
        raise SystemExit(f"Environment validation error:\n{exc}")
