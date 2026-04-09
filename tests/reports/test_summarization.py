from __future__ import annotations

import json
from pathlib import Path

import httpx
import respx
import yaml

from radar.app import build_runtime
from radar.reports.summarization import NullReportSummarizer, OpenAIReportSummarizer


def _write_config(tmp_path: Path, *, summarization: dict | None = None) -> Path:
    config = {
        "app": {"timezone": "UTC"},
        "storage": {"path": str(tmp_path / "radar.db")},
        "channels": {
            "webhook": {"enabled": False},
            "email": {"enabled": False},
        },
        "sources": {
            "github": {"enabled": False},
            "official_pages": {"enabled": False},
            "huggingface": {"enabled": False},
            "modelscope": {"enabled": False},
            "modelers": {"enabled": False},
            "gitcode": {"enabled": False},
        },
    }
    if summarization is not None:
        config["summarization"] = summarization

    config_path = tmp_path / "radar.yaml"
    config_path.write_text(yaml.dump(config))
    return config_path


def test_null_report_summarizer_returns_empty_fields() -> None:
    summarizer = NullReportSummarizer()

    entry = summarizer.summarize_entry(
        {
            "display_name": "acme/tool",
            "source": "github",
            "reason": {"full_name": "acme/tool", "stars": 25},
        }
    )

    assert entry == {"title_zh": None, "reason_text_zh": None, "reason_text_en": None}


def test_null_report_summarizer_returns_empty_daily_briefing_fields() -> None:
    summarizer = NullReportSummarizer()

    briefing = summarizer.summarize_daily_briefing(date="2026-04-09", entries=[])

    assert briefing == {"briefing_zh": None, "briefing_en": None}


@respx.mock
def test_openai_report_summarizer_maps_response_to_entry_fields() -> None:
    route = respx.post("https://example.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "title_zh": "仓库热度上升",
                                    "reason_text_zh": "该仓库近期活跃度上升。",
                                    "reason_text_en": "The repository saw a recent burst in activity.",
                                }
                            )
                        }
                    }
                ]
            },
        )
    )

    summarizer = OpenAIReportSummarizer(
        base_url="https://example.com/v1",
        api_key="test-key",
        model="test-model",
        timeout_seconds=20,
        max_input_chars=4000,
    )

    result = summarizer.summarize_entry(
        {
            "display_name": "acme/tool",
            "source": "github",
            "reason": {"full_name": "acme/tool", "stars": 25},
        }
    )

    assert result["title_zh"] == "仓库热度上升"
    assert "活跃度上升" in result["reason_text_zh"]
    assert "burst in activity" in result["reason_text_en"]
    assert route.called is True
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer test-key"
    assert request.read().decode()
    assert json.loads(request.read().decode())["response_format"] == {
        "type": "json_object"
    }


def test_build_runtime_uses_null_report_summarizer_when_disabled(tmp_path: Path) -> None:
    runtime = build_runtime(_write_config(tmp_path))

    try:
        assert isinstance(runtime.report_summarizer, NullReportSummarizer)
    finally:
        runtime.engine.dispose()


def test_build_runtime_uses_openai_report_summarizer_when_enabled(tmp_path: Path) -> None:
    runtime = build_runtime(
        _write_config(
            tmp_path,
            summarization={
                "enabled": True,
                "base_url": "https://example.com/v1",
                "api_key": "test-key",
                "model": "test-model",
                "timeout_seconds": 15,
                "max_input_chars": 3000,
            },
        )
    )

    try:
        assert isinstance(runtime.report_summarizer, OpenAIReportSummarizer)
    finally:
        runtime.engine.dispose()
