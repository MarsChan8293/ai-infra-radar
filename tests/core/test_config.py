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
""".strip()
    )
    with pytest.raises(ValidationError):
        load_settings(config_path)
