from enum import Enum

from pydantic import BaseModel


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
