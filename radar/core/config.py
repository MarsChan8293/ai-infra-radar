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


class GitHubAIReadmeFilterSettings(BaseModel):
    model_config = _FORBID
    enabled: bool = False
    default_prompt: str | None = None

    @model_validator(mode="after")
    def _require_prompt_when_enabled(self) -> "GitHubAIReadmeFilterSettings":
        if self.enabled and (
            self.default_prompt is None or not self.default_prompt.strip()
        ):
            raise ValueError("default_prompt is required when ai_readme_filter is enabled")
        return self


class GitHubReadmeFilterSettings(BaseModel):
    model_config = _FORBID
    enabled: bool = False
    require_any: list[str] = []

    @model_validator(mode="after")
    def _require_keywords_when_enabled(self) -> "GitHubReadmeFilterSettings":
        if self.enabled and not self.require_any:
            raise ValueError("require_any must contain at least one entry when readme_filter is enabled")
        return self


class GitHubSettings(BaseModel):
    model_config = _FORBID
    enabled: bool
    token: str | None = None
    queries: list[str] = []
    burst_threshold: float = 0.6
    readme_filter: GitHubReadmeFilterSettings = GitHubReadmeFilterSettings()
    ai_readme_filter: GitHubAIReadmeFilterSettings = GitHubAIReadmeFilterSettings()

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


class GitCodeSettings(BaseModel):
    model_config = _FORBID
    enabled: bool
    token: str | None = None
    organizations: list[str] = []

    @model_validator(mode="after")
    def _require_token_and_orgs_when_enabled(self) -> "GitCodeSettings":
        if self.enabled and not self.token:
            raise ValueError("token is required when gitcode is enabled")
        if self.enabled and not self.organizations:
            raise ValueError("organizations must contain at least one entry when gitcode is enabled")
        return self


class SourceSettings(BaseModel):
    model_config = _FORBID
    github: GitHubSettings
    official_pages: OfficialPagesSettings
    huggingface: HuggingFaceSettings
    modelscope: ModelScopeSettings = ModelScopeSettings(enabled=False)
    modelers: ModelersSettings = ModelersSettings(enabled=False)
    gitcode: GitCodeSettings = GitCodeSettings(enabled=False)


class SummarizationSettings(BaseModel):
    model_config = _FORBID
    enabled: bool = False
    base_url: HttpUrl | None = None
    api_key: str | None = None
    model: str | None = None
    timeout_seconds: int = 20
    max_input_chars: int = 4000

    @model_validator(mode="after")
    def _require_provider_fields_when_enabled(self) -> "SummarizationSettings":
        if not self.enabled:
            return self
        if self.base_url is None:
            raise ValueError("base_url is required when summarization is enabled")
        if not self.api_key:
            raise ValueError("api_key is required when summarization is enabled")
        if not self.model:
            raise ValueError("model is required when summarization is enabled")
        return self


class Settings(BaseModel):
    model_config = _FORBID
    app: AppSettings
    storage: StorageSettings
    channels: ChannelSettings
    sources: SourceSettings
    summarization: SummarizationSettings = SummarizationSettings()


def load_settings(path: Path) -> Settings:
    data = yaml.safe_load(path.read_text())
    if data is None:
        data = {}
    return Settings.model_validate(data)
