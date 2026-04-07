from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


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

    @model_validator(mode="after")
    def _require_url_when_enabled(self) -> "WebhookChannelSettings":
        if self.enabled and self.url is None:
            raise ValueError("url is required when webhook is enabled")
        return self


class EmailChannelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    enabled: bool
    smtp_host: str | None = None
    smtp_port: int = 587
    username: str | None = None
    password: str | None = None
    from_address: str | None = Field(default=None, alias="from")
    to: list[str] = []

    @model_validator(mode="after")
    def _require_smtp_host_when_enabled(self) -> "EmailChannelSettings":
        if self.enabled and self.smtp_host is None:
            raise ValueError("smtp_host is required when email is enabled")
        return self


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

    @model_validator(mode="after")
    def _require_queries_when_enabled(self) -> "GitHubSettings":
        if self.enabled and not self.queries:
            raise ValueError("queries must contain at least one entry when github is enabled")
        return self


class OfficialPageEntry(BaseModel):
    model_config = _FORBID
    url: HttpUrl
    whitelist_keywords: list[str] = []


class OfficialPagesSettings(BaseModel):
    model_config = _FORBID
    enabled: bool
    pages: list[OfficialPageEntry] = []

    @model_validator(mode="after")
    def _require_pages_when_enabled(self) -> "OfficialPagesSettings":
        if self.enabled and not self.pages:
            raise ValueError("pages must contain at least one entry when official_pages is enabled")
        return self


class HuggingFaceSettings(BaseModel):
    model_config = _FORBID
    enabled: bool
    organizations: list[str] = []

    @model_validator(mode="after")
    def _require_orgs_when_enabled(self) -> "HuggingFaceSettings":
        if self.enabled and not self.organizations:
            raise ValueError("organizations must contain at least one entry when huggingface is enabled")
        return self


class ModelScopeSettings(BaseModel):
    model_config = _FORBID
    enabled: bool
    organizations: list[str] = []

    @model_validator(mode="after")
    def _require_orgs_when_enabled(self) -> "ModelScopeSettings":
        if self.enabled and not self.organizations:
            raise ValueError("organizations must contain at least one entry when modelscope is enabled")
        return self


class ModelersSettings(BaseModel):
    model_config = _FORBID
    enabled: bool
    organizations: list[str] = []

    @model_validator(mode="after")
    def _require_orgs_when_enabled(self) -> "ModelersSettings":
        if self.enabled and not self.organizations:
            raise ValueError("organizations must contain at least one entry when modelers is enabled")
        return self


class SourceSettings(BaseModel):
    model_config = _FORBID
    github: GitHubSettings
    official_pages: OfficialPagesSettings
    huggingface: HuggingFaceSettings
    modelscope: ModelScopeSettings = ModelScopeSettings(enabled=False)
    modelers: ModelersSettings = ModelersSettings(enabled=False)


class Settings(BaseModel):
    model_config = _FORBID
    app: AppSettings
    storage: StorageSettings
    channels: ChannelSettings
    sources: SourceSettings


def load_settings(path: Path) -> Settings:
    return Settings.model_validate(yaml.safe_load(path.read_text()))
