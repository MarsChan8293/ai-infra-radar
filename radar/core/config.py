from pathlib import Path

import yaml
from pydantic import BaseModel, Field, HttpUrl


class AppSettings(BaseModel):
    timezone: str


class StorageSettings(BaseModel):
    path: str


class WebhookChannelSettings(BaseModel):
    enabled: bool
    url: HttpUrl | None = None


class EmailChannelSettings(BaseModel):
    enabled: bool
    smtp_host: str | None = None
    smtp_port: int = 587
    username: str | None = None
    password: str | None = None
    from_address: str | None = Field(default=None, alias="from")
    to: list[str] = []

    model_config = {"populate_by_name": True}


class ChannelSettings(BaseModel):
    webhook: WebhookChannelSettings
    email: EmailChannelSettings


class GitHubSettings(BaseModel):
    enabled: bool
    token: str | None = None
    queries: list[str] = []
    burst_threshold: float = 0.6


class OfficialPagesSettings(BaseModel):
    enabled: bool
    pages: list[dict] = []


class SourceSettings(BaseModel):
    github: GitHubSettings
    official_pages: OfficialPagesSettings


class Settings(BaseModel):
    app: AppSettings
    storage: StorageSettings
    channels: ChannelSettings
    sources: SourceSettings


def load_settings(path: Path) -> Settings:
    return Settings.model_validate(yaml.safe_load(path.read_text()))
