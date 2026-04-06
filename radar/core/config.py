from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl


_FORBID = ConfigDict(extra="forbid")


class AppSettings(BaseModel):
    model_config = _FORBID
    timezone: str


class StorageSettings(BaseModel):
    model_config = _FORBID
    path: str


class WebhookChannelSettings(BaseModel):
    model_config = _FORBID
    enabled: bool
    url: HttpUrl | None = None


class EmailChannelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    enabled: bool
    smtp_host: str | None = None
    smtp_port: int = 587
    username: str | None = None
    password: str | None = None
    from_address: str | None = Field(default=None, alias="from")
    to: list[str] = []


class ChannelSettings(BaseModel):
    model_config = _FORBID
    webhook: WebhookChannelSettings
    email: EmailChannelSettings


class GitHubSettings(BaseModel):
    model_config = _FORBID
    enabled: bool
    token: str | None = None
    queries: list[str] = []
    burst_threshold: float = 0.6


class OfficialPageEntry(BaseModel):
    model_config = _FORBID
    url: HttpUrl
    whitelist_keywords: list[str] = []


class OfficialPagesSettings(BaseModel):
    model_config = _FORBID
    enabled: bool
    pages: list[OfficialPageEntry] = []


class SourceSettings(BaseModel):
    model_config = _FORBID
    github: GitHubSettings
    official_pages: OfficialPagesSettings


class Settings(BaseModel):
    model_config = _FORBID
    app: AppSettings
    storage: StorageSettings
    channels: ChannelSettings
    sources: SourceSettings


def load_settings(path: Path) -> Settings:
    return Settings.model_validate(yaml.safe_load(path.read_text()))
