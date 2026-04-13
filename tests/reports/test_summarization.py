from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest
import respx
import yaml

from radar.app import RuntimeState, apply_runtime, build_runtime, create_app, shutdown_runtime
from radar.reports.summarization import NullReportSummarizer, OpenAIReportSummarizer
from radar.sources.github.readme_ai_filter import OpenAIGitHubReadmeAIFilter


def _write_config(
    tmp_path: Path,
    *,
    summarization: dict | None = None,
    github: dict | None = None,
) -> Path:
    config = {
        "app": {"timezone": "UTC"},
        "storage": {"path": str(tmp_path / "radar.db")},
        "channels": {
            "webhook": {"enabled": False},
            "email": {"enabled": False},
        },
        "sources": {
            "github": github or {"enabled": False},
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


@respx.mock
def test_openai_report_summarizer_retries_transient_remote_protocol_errors() -> None:
    attempts = {"count": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx.RemoteProtocolError("server disconnected")
        return httpx.Response(
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

    respx.post("https://example.com/v1/chat/completions").mock(side_effect=_handler)

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

    assert attempts["count"] == 2
    assert result["title_zh"] == "仓库热度上升"


@respx.mock
def test_openai_report_summarizer_maps_response_to_daily_briefing_fields() -> None:
    respx.post("https://example.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "briefing_zh": "今日 AI 基础设施项目整体保持活跃。",
                                    "briefing_en": "AI infrastructure projects remained active today.",
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

    result = summarizer.summarize_daily_briefing(
        date="2026-04-09",
        entries=[{"display_name": "acme/tool", "source": "github", "reason": {}}],
    )

    assert result == {
        "briefing_zh": "今日 AI 基础设施项目整体保持活跃。",
        "briefing_en": "AI infrastructure projects remained active today.",
    }


@respx.mock
def test_openai_report_summarizer_retries_retryable_status_codes() -> None:
    attempts = {"count": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "briefing_zh": "今日 AI 基础设施项目整体保持活跃。",
                                    "briefing_en": "AI infrastructure projects remained active today.",
                                }
                            )
                        }
                    }
                ]
            },
        )

    respx.post("https://example.com/v1/chat/completions").mock(side_effect=_handler)

    summarizer = OpenAIReportSummarizer(
        base_url="https://example.com/v1",
        api_key="test-key",
        model="test-model",
        timeout_seconds=20,
        max_input_chars=4000,
    )

    result = summarizer.summarize_daily_briefing(
        date="2026-04-09",
        entries=[{"display_name": "acme/tool", "source": "github", "reason": {}}],
    )

    assert attempts["count"] == 2
    assert result["briefing_en"] == "AI infrastructure projects remained active today."


@respx.mock
def test_openai_github_readme_ai_filter_retries_transient_remote_protocol_errors() -> None:
    attempts = {"count": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx.RemoteProtocolError("server disconnected")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "keep": True,
                                    "reason_zh": "README 与推理系统直接相关。",
                                    "matched_signals": ["inference serving"],
                                }
                            )
                        }
                    }
                ]
            },
        )

    respx.post("https://example.com/v1/chat/completions").mock(side_effect=_handler)

    readme_filter = OpenAIGitHubReadmeAIFilter(
        base_url="https://example.com/v1",
        api_key="test-key",
        model="readme-filter-model",
        timeout_seconds=20,
        max_input_chars=4000,
    )

    result = readme_filter.evaluate(
        repository={"full_name": "acme/serve-fast"},
        readme_text="README serving and throughput details",
        prompt="Decide if the README is relevant to inference systems.",
    )

    assert attempts["count"] == 2
    assert result["keep"] is True


@respx.mock
def test_openai_github_readme_ai_filter_does_not_retry_non_retryable_status_codes() -> None:
    attempts = {"count": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(400, json={"error": "bad request"})

    respx.post("https://example.com/v1/chat/completions").mock(side_effect=_handler)

    readme_filter = OpenAIGitHubReadmeAIFilter(
        base_url="https://example.com/v1",
        api_key="test-key",
        model="readme-filter-model",
        timeout_seconds=20,
        max_input_chars=4000,
    )

    with pytest.raises(httpx.HTTPStatusError):
        readme_filter.evaluate(
            repository={"full_name": "acme/serve-fast"},
            readme_text="README serving and throughput details",
            prompt="Decide if the README is relevant to inference systems.",
        )

    assert attempts["count"] == 1


@pytest.mark.parametrize(
    ("provider_payload", "message"),
    [
        (
            {"choices": []},
            "choices[0].message.content string",
        ),
        (
            {"choices": [{"message": {"content": "{not-json"}}]},
            "content was not valid JSON",
        ),
        (
            {"choices": [{"message": {"content": "[]"}}]},
            "JSON object",
        ),
    ],
)
@respx.mock
def test_openai_report_summarizer_raises_runtime_error_for_malformed_provider_output(
    provider_payload: dict, message: str
) -> None:
    respx.post("https://example.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=provider_payload)
    )

    summarizer = OpenAIReportSummarizer(
        base_url="https://example.com/v1",
        api_key="test-key",
        model="test-model",
        timeout_seconds=20,
        max_input_chars=4000,
    )

    with pytest.raises(RuntimeError, match=re.escape(message)):
        summarizer.summarize_entry(
            {
                "display_name": "acme/tool",
                "source": "github",
                "reason": {"full_name": "acme/tool", "stars": 25},
            }
        )


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("title_zh", 123),
        ("reason_text_zh", ["unexpected"]),
        ("reason_text_en", {"unexpected": True}),
    ],
)
@respx.mock
def test_openai_report_summarizer_raises_runtime_error_for_invalid_entry_field_types(
    field_name: str, field_value: object
) -> None:
    respx.post("https://example.com/v1/chat/completions").mock(
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
                                    field_name: field_value,
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

    with pytest.raises(
        RuntimeError,
        match=re.escape(
            f"Malformed summarization provider output: field {field_name!r} must be a string or null."
        ),
    ):
        summarizer.summarize_entry(
            {
                "display_name": "acme/tool",
                "source": "github",
                "reason": {"full_name": "acme/tool", "stars": 25},
            }
        )


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("briefing_zh", 123),
        ("briefing_en", ["unexpected"]),
    ],
)
@respx.mock
def test_openai_report_summarizer_raises_runtime_error_for_invalid_daily_briefing_field_types(
    field_name: str, field_value: object
) -> None:
    respx.post("https://example.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "briefing_zh": "今日 AI 基础设施项目整体保持活跃。",
                                    "briefing_en": "AI infrastructure projects remained active today.",
                                    field_name: field_value,
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

    with pytest.raises(
        RuntimeError,
        match=re.escape(
            f"Malformed summarization provider output: field {field_name!r} must be a string or null."
        ),
    ):
        summarizer.summarize_daily_briefing(
            date="2026-04-09",
            entries=[{"display_name": "acme/tool", "source": "github", "reason": {}}],
        )


def test_build_runtime_uses_null_report_summarizer_when_disabled(tmp_path: Path) -> None:
    runtime = build_runtime(_write_config(tmp_path))

    try:
        assert isinstance(runtime.report_summarizer, NullReportSummarizer)
    finally:
        runtime.report_summarizer.close()
        runtime.engine.dispose()


def test_build_runtime_defaults_github_readme_ai_filter_to_none(tmp_path: Path) -> None:
    runtime = build_runtime(_write_config(tmp_path))

    try:
        assert runtime.github_readme_ai_filter is None
    finally:
        runtime.report_summarizer.close()
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
        runtime.report_summarizer.close()
        runtime.engine.dispose()


@respx.mock
def test_build_runtime_wires_openai_github_readme_ai_filter_when_enabled(
    tmp_path: Path,
) -> None:
    route = respx.post("https://example.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "keep": True,
                                    "reason_zh": "README 与推理系统直接相关。",
                                    "matched_signals": ["inference serving"],
                                }
                            )
                        }
                    }
                ]
            },
        )
    )

    runtime = build_runtime(
        _write_config(
            tmp_path,
            summarization={
                "enabled": False,
                "base_url": "https://example.com/v1",
                "api_key": "test-key",
                "timeout_seconds": 15,
                "max_input_chars": 3000,
            },
            github={
                "enabled": False,
                "ai_readme_filter": {
                    "enabled": True,
                    "model": "readme-filter-model",
                    "default_prompt": "Decide if the README is relevant to inference systems.",
                },
            },
        )
    )

    try:
        assert runtime.github_readme_ai_filter is not None
        result = runtime.github_readme_ai_filter.evaluate(
            repository={"full_name": "acme/serve-fast"},
            readme_text="README serving and throughput details",
            prompt="Decide if the README is relevant to inference systems.",
        )
        assert result == {
            "keep": True,
            "reason_zh": "README 与推理系统直接相关。",
            "matched_signals": ["inference serving"],
        }
        request = route.calls[0].request
        assert request.headers["Authorization"] == "Bearer test-key"
        assert json.loads(request.read().decode())["model"] == "readme-filter-model"
    finally:
        if runtime.github_readme_ai_filter is not None:
            runtime.github_readme_ai_filter.close()
        runtime.report_summarizer.close()
        runtime.engine.dispose()


class _FakeScheduler:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


class _FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


class _FakeSummarizer:
    def __init__(self) -> None:
        self.closed = False

    def summarize_entry(self, entry: dict[str, object]) -> dict[str, str | None]:
        return {"title_zh": None, "reason_text_zh": None, "reason_text_en": None}

    def summarize_daily_briefing(
        self, *, date: str, entries: list[dict[str, object]]
    ) -> dict[str, str | None]:
        return {"briefing_zh": None, "briefing_en": None}

    def close(self) -> None:
        self.closed = True


class _FakeReadmeAIFilter:
    def __init__(self) -> None:
        self.closed = False

    def evaluate(
        self, *, repository: dict[str, object], readme_text: str, prompt: str
    ) -> dict[str, object]:
        return {"keep": True, "reason_zh": "", "matched_signals": []}

    def close(self) -> None:
        self.closed = True


def _runtime_with(
    scheduler: _FakeScheduler,
    engine: _FakeEngine,
    summarizer: _FakeSummarizer,
    github_readme_ai_filter: object | None = None,
) -> RuntimeState:
    return RuntimeState(
        settings=object(),
        config_path=Path("radar.yaml"),
        engine=engine,
        repo=object(),
        scheduler=scheduler,
        alert_service=object(),
        github_client=object(),
        huggingface_client=object(),
        modelscope_client=object(),
        modelers_client=object(),
        gitcode_client=object(),
        report_summarizer=summarizer,
        github_readme_ai_filter=github_readme_ai_filter,
    )


def test_apply_runtime_closes_previous_report_summarizer() -> None:
    app = create_app()
    old_scheduler = _FakeScheduler()
    old_engine = _FakeEngine()
    old_summarizer = _FakeSummarizer()
    app.state.scheduler = old_scheduler
    app.state.engine = old_engine
    app.state.report_summarizer = old_summarizer

    new_scheduler = _FakeScheduler()
    new_engine = _FakeEngine()
    new_summarizer = _FakeSummarizer()

    apply_runtime(app, _runtime_with(new_scheduler, new_engine, new_summarizer))

    assert old_scheduler.stopped is True
    assert old_engine.disposed is True
    assert old_summarizer.closed is True
    assert new_scheduler.started is True
    assert app.state.report_summarizer is new_summarizer


def test_apply_runtime_sets_github_readme_ai_filter_on_app_state() -> None:
    app = create_app()
    runtime = _runtime_with(_FakeScheduler(), _FakeEngine(), _FakeSummarizer())
    github_readme_ai_filter = object()
    runtime.github_readme_ai_filter = github_readme_ai_filter

    apply_runtime(app, runtime)

    assert app.state.github_readme_ai_filter is github_readme_ai_filter


def test_apply_runtime_closes_previous_github_readme_ai_filter() -> None:
    app = create_app()
    app.state.scheduler = _FakeScheduler()
    app.state.engine = _FakeEngine()
    app.state.report_summarizer = _FakeSummarizer()
    old_readme_ai_filter = _FakeReadmeAIFilter()
    app.state.github_readme_ai_filter = old_readme_ai_filter

    apply_runtime(app, _runtime_with(_FakeScheduler(), _FakeEngine(), _FakeSummarizer()))

    assert old_readme_ai_filter.closed is True


def test_shutdown_runtime_closes_report_summarizer() -> None:
    app = create_app()
    scheduler = _FakeScheduler()
    engine = _FakeEngine()
    summarizer = _FakeSummarizer()
    app.state.scheduler = scheduler
    app.state.engine = engine
    app.state.report_summarizer = summarizer

    shutdown_runtime(app)

    assert scheduler.stopped is True
    assert engine.disposed is True
    assert summarizer.closed is True


def test_shutdown_runtime_closes_github_readme_ai_filter() -> None:
    app = create_app()
    app.state.scheduler = _FakeScheduler()
    app.state.engine = _FakeEngine()
    app.state.report_summarizer = _FakeSummarizer()
    readme_ai_filter = _FakeReadmeAIFilter()
    app.state.github_readme_ai_filter = readme_ai_filter

    shutdown_runtime(app)

    assert readme_ai_filter.closed is True


def test_create_app_defaults_github_readme_ai_filter_to_none() -> None:
    app = create_app()

    assert app.state.github_readme_ai_filter is None
