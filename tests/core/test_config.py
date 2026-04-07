from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from radar.cli import cli
from radar.core.config import load_settings

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_load_settings_reads_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "radar.yaml"
    config_path.write_text(
        """
app:
  timezone: Asia/Singapore
storage:
  path: ./data/radar.db
channels:
  webhook:
    enabled: true
    url: https://example.com/webhook
  email:
    enabled: true
    smtp_host: smtp.example.com
    smtp_port: 587
    username: radar@example.com
    password: secret
    from: radar@example.com
    to:
      - team@example.com
sources:
  github:
    enabled: true
    token: ghp_example
    queries:
      - sglang
    burst_threshold: 0.6
  official_pages:
    enabled: true
    pages:
      - url: https://api-docs.deepseek.com/
        whitelist_keywords:
          - release
          - update
  huggingface:
    enabled: false
""".strip()
    )

    settings = load_settings(config_path)

    assert settings.app.timezone == "Asia/Singapore"
    assert settings.storage.path == "./data/radar.db"
    assert settings.channels.webhook.enabled is True

    page = settings.sources.official_pages.pages[0]
    assert str(page.url) == "https://api-docs.deepseek.com/"
    assert page.whitelist_keywords == ["release", "update"]


def test_load_settings_reads_minimal_fixture() -> None:
    """load_settings works with the checked-in minimal.yaml fixture."""
    settings = load_settings(FIXTURES_DIR / "minimal.yaml")

    assert settings.app.timezone == "Asia/Singapore"
    assert settings.storage.path == "./data/radar.db"
    assert settings.channels.webhook.enabled is True

    page = settings.sources.official_pages.pages[0]
    assert str(page.url) == "https://api-docs.deepseek.com/"
    assert page.whitelist_keywords == ["release", "update"]


def test_validate_config_cli_command() -> None:
    """validate-config CLI command prints 'config ok' for the minimal fixture."""
    runner = CliRunner()
    result = runner.invoke(cli, ["validate-config", str(FIXTURES_DIR / "minimal.yaml")])

    assert result.exit_code == 0
    assert "config ok" in result.output


# --- TDD: unknown keys must be rejected ---

def test_unknown_top_level_key_raises(tmp_path: Path) -> None:
    """An unrecognised top-level key must raise ValidationError."""
    config_path = tmp_path / "bad.yaml"
    config_path.write_text(
        """
app:
  timezone: UTC
storage:
  path: ./data/radar.db
channels:
  webhook:
    enabled: false
  email:
    enabled: false
sources:
  github:
    enabled: false
  official_pages:
    enabled: false
unknown_top_key: oops
""".strip()
    )
    with pytest.raises(ValidationError):
        load_settings(config_path)


# --- TDD: enabled-source completeness ---

def test_github_enabled_with_no_queries_raises(tmp_path: Path) -> None:
    """github.enabled=true with an empty queries list must raise ValidationError."""
    config_path = tmp_path / "bad.yaml"
    config_path.write_text(
        """
app:
  timezone: UTC
storage:
  path: ./data/radar.db
channels:
  webhook:
    enabled: false
  email:
    enabled: false
sources:
  github:
    enabled: true
    queries: []
  official_pages:
    enabled: false
""".strip()
    )
    with pytest.raises(ValidationError, match="queries"):
        load_settings(config_path)


def test_github_disabled_with_no_queries_is_valid(tmp_path: Path) -> None:
    """github.enabled=false with no queries must be accepted."""
    config_path = tmp_path / "ok.yaml"
    config_path.write_text(
        """
app:
  timezone: UTC
storage:
  path: ./data/radar.db
channels:
  webhook:
    enabled: false
  email:
    enabled: false
sources:
  github:
    enabled: false
  official_pages:
    enabled: false
  huggingface:
    enabled: false
""".strip()
    )
    settings = load_settings(config_path)
    assert settings.sources.github.enabled is False


def test_huggingface_enabled_without_organizations_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "radar.yaml"
    config_path.write_text(
        """
app:
  timezone: UTC
storage:
  path: ./data/radar.db
channels:
  webhook:
    enabled: false
  email:
    enabled: false
sources:
  github:
    enabled: false
  official_pages:
    enabled: false
  huggingface:
    enabled: true
""".strip()
    )

    with pytest.raises(ValueError, match="organizations"):
        load_settings(config_path)


def test_huggingface_enabled_with_empty_organizations_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "radar.yaml"
    config_path.write_text(
        """
app:
  timezone: UTC
storage:
  path: ./data/radar.db
channels:
  webhook:
    enabled: false
  email:
    enabled: false
sources:
  github:
    enabled: false
  official_pages:
    enabled: false
  huggingface:
    enabled: true
    organizations: []
""".strip()
    )

    with pytest.raises(ValueError, match="organizations"):
        load_settings(config_path)


def test_huggingface_enabled_accepts_organizations(tmp_path: Path) -> None:
    config_path = tmp_path / "radar.yaml"
    config_path.write_text(
        """
app:
  timezone: UTC
storage:
  path: ./data/radar.db
channels:
  webhook:
    enabled: false
  email:
    enabled: false
sources:
  github:
    enabled: false
  official_pages:
    enabled: false
  huggingface:
    enabled: true
    organizations:
      - deepseek
""".strip()
    )

    settings = load_settings(config_path)
    assert settings.sources.huggingface.organizations == ["deepseek"]


def test_official_pages_enabled_with_no_pages_raises(tmp_path: Path) -> None:
    """official_pages.enabled=true with an empty pages list must raise ValidationError."""
    config_path = tmp_path / "bad.yaml"
    config_path.write_text(
        """
app:
  timezone: UTC
storage:
  path: ./data/radar.db
channels:
  webhook:
    enabled: false
  email:
    enabled: false
sources:
  github:
    enabled: false
  official_pages:
    enabled: true
    pages: []
""".strip()
    )
    with pytest.raises(ValidationError, match="pages"):
        load_settings(config_path)


def test_official_pages_disabled_with_no_pages_is_valid(tmp_path: Path) -> None:
    """official_pages.enabled=false with no pages must be accepted."""
    config_path = tmp_path / "ok.yaml"
    config_path.write_text(
        """
app:
  timezone: UTC
storage:
  path: ./data/radar.db
channels:
  webhook:
    enabled: false
  email:
    enabled: false
sources:
  github:
    enabled: false
  official_pages:
    enabled: false
  huggingface:
    enabled: false
""".strip()
    )
    settings = load_settings(config_path)
    assert settings.sources.official_pages.enabled is False


# --- TDD: enabled-channel completeness ---

def test_webhook_enabled_with_no_url_raises(tmp_path: Path) -> None:
    """webhook.enabled=true without a url must raise ValidationError."""
    config_path = tmp_path / "bad.yaml"
    config_path.write_text(
        """
app:
  timezone: UTC
storage:
  path: ./data/radar.db
channels:
  webhook:
    enabled: true
  email:
    enabled: false
sources:
  github:
    enabled: false
  official_pages:
    enabled: false
  huggingface:
    enabled: false
""".strip()
    )
    with pytest.raises(ValidationError, match="url"):
        load_settings(config_path)


def test_email_enabled_with_no_smtp_host_raises(tmp_path: Path) -> None:
    """email.enabled=true without smtp_host must raise ValidationError."""
    config_path = tmp_path / "bad.yaml"
    config_path.write_text(
        """
app:
  timezone: UTC
storage:
  path: ./data/radar.db
channels:
  webhook:
    enabled: false
  email:
    enabled: true
sources:
  github:
    enabled: false
  official_pages:
    enabled: false
  huggingface:
    enabled: false
""".strip()
    )
    with pytest.raises(ValidationError, match="smtp_host"):
        load_settings(config_path)


def test_unknown_nested_key_raises(tmp_path: Path) -> None:
    """An unrecognised key nested inside a sub-model must raise ValidationError."""
    config_path = tmp_path / "bad_nested.yaml"
    config_path.write_text(
        """
app:
  timezone: UTC
  typo_key: should_not_be_here
storage:
  path: ./data/radar.db
channels:
  webhook:
    enabled: false
  email:
    enabled: false
sources:
  github:
    enabled: false
  official_pages:
    enabled: false
  huggingface:
    enabled: false
""".strip()
    )
    with pytest.raises(ValidationError):
        load_settings(config_path)
