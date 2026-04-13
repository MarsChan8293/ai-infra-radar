from __future__ import annotations

import textwrap
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from radar.app import create_app


class _FakeGitHubClient:
    def __init__(self, items: list[dict], readmes: dict[str, str | None] | None = None) -> None:
        self._items = items
        self._readmes = readmes or {}
        self.queries: list[str] = []

    def search_repositories(self, query: str) -> list[dict]:
        self.queries.append(query)
        return list(self._items)

    def fetch_readme_text(self, full_name: str) -> str | None:
        value = self._readmes[full_name]
        if isinstance(value, Exception):
            raise value
        return value


class _FakeReadmeAIFilter:
    def __init__(self, responses: dict[str, dict]) -> None:
        self._responses = responses
        self.calls: list[dict] = []

    def evaluate(self, *, repository: dict, readme_text: str, prompt: str) -> dict:
        self.calls.append(
            {
                "full_name": repository["full_name"],
                "readme_text": readme_text,
                "prompt": prompt,
            }
        )
        return self._responses[repository["full_name"]]


class _ExplodingGitHubClient:
    def __init__(self) -> None:
        self.called = False

    def search_repositories(self, query: str) -> list[dict]:
        self.called = True
        return []

    def fetch_readme_text(self, full_name: str) -> str | None:
        raise AssertionError("fetch_readme_text should not be called")


class _DummyRepo:
    def list_alerts(self) -> list[object]:
        return []


def _make_client(
    *,
    github_client: object,
    github_readme_ai_filter: object | None,
    default_prompt: str | None = None,
) -> TestClient:
    app = create_app()
    app.state.repo = _DummyRepo()
    app.state.scheduler = None
    app.state.settings = SimpleNamespace(
        sources=SimpleNamespace(
            github=SimpleNamespace(
                ai_readme_filter=SimpleNamespace(default_prompt=default_prompt)
            )
        )
    )
    app.state.github_client = github_client
    app.state.github_readme_ai_filter = github_readme_ai_filter
    return TestClient(app)


def test_manual_fetch_accepts_github_config_yaml_fragment() -> None:
    github_client = _FakeGitHubClient(
        [
            {
                "full_name": "acme/serve-fast",
                "name": "serve-fast",
                "owner": {"login": "acme"},
                "html_url": "https://github.com/acme/serve-fast",
                "description": "High-throughput inference server",
                "stargazers_count": 120,
                "forks_count": 17,
                "language": "Python",
                "topics": ["inference", "serving"],
                "created_at": "2026-04-03T00:00:00Z",
                "updated_at": "2026-04-10T00:00:00Z",
                "pushed_at": "2026-04-10T00:00:00Z",
                "default_branch": "main",
            }
        ],
        readmes={"acme/serve-fast": "README serving and throughput details"},
    )
    ai_filter = _FakeReadmeAIFilter(
        {
            "acme/serve-fast": {
                "keep": True,
                "reason_zh": "README 明确描述了推理服务能力。",
                "matched_signals": ["serving", "throughput"],
            }
        }
    )
    client = _make_client(github_client=github_client, github_readme_ai_filter=ai_filter)

    response = client.post(
        "/ops/github/manual-fetch",
        json={
            "github_config_yaml": textwrap.dedent(
                """
                queries:
                  - '"speculative decoding" created:>@today-1d'
                burst_threshold: 0.01
                readme_filter:
                  enabled: false
                ai_readme_filter:
                  enabled: true
                  model: nvidia/nemotron-3-super-120b-a12b
                  default_prompt: Decide if this repository is relevant to inference systems.
                """
            ).strip()
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["coarse_count"] == 1
    assert body["request"]["readme_prompt"] == (
        "Decide if this repository is relevant to inference systems."
    )


def test_manual_fetch_rejects_invalid_yaml_fragment() -> None:
    github_client = _ExplodingGitHubClient()
    client = _make_client(
        github_client=github_client,
        github_readme_ai_filter=_FakeReadmeAIFilter({}),
    )

    response = client.post(
        "/ops/github/manual-fetch",
        json={
            "github_config_yaml": "queries: [unterminated",
        },
    )

    assert response.status_code == 422
    assert "github_config_yaml" in response.text
    assert github_client.called is False


def test_manual_fetch_returns_coarse_and_secondary_results() -> None:
    items = [
        {
            "full_name": "acme/serve-fast",
            "name": "serve-fast",
            "owner": {"login": "acme"},
            "html_url": "https://github.com/acme/serve-fast",
            "description": "High-throughput inference server",
            "stargazers_count": 120,
            "forks_count": 17,
            "language": "Python",
            "topics": ["inference", "serving"],
            "created_at": "2026-04-03T00:00:00Z",
            "updated_at": "2026-04-10T00:00:00Z",
            "pushed_at": "2026-04-10T00:00:00Z",
            "default_branch": "main",
        },
        {
            "full_name": "acme/dev-notes",
            "name": "dev-notes",
            "owner": {"login": "acme"},
            "html_url": "https://github.com/acme/dev-notes",
            "description": "Research notes",
            "stargazers_count": 12,
            "forks_count": 2,
            "language": "Markdown",
            "topics": ["notes"],
            "created_at": "2026-04-04T00:00:00Z",
            "updated_at": "2026-04-10T00:00:00Z",
            "pushed_at": "2026-04-10T00:00:00Z",
            "default_branch": "main",
        },
    ]
    github_client = _FakeGitHubClient(
        items,
        readmes={
            "acme/serve-fast": "README serving and throughput details",
            "acme/dev-notes": "README with personal notes only",
        },
    )
    ai_filter = _FakeReadmeAIFilter(
        {
            "acme/serve-fast": {
                "keep": True,
                "reason_zh": "README 明确描述了推理服务能力。",
                "matched_signals": ["serving", "throughput"],
            },
            "acme/dev-notes": {
                "keep": False,
                "reason_zh": "README 更像是研究笔记。",
                "matched_signals": [],
            },
        }
    )
    client = _make_client(github_client=github_client, github_readme_ai_filter=ai_filter)

    response = client.post(
        "/ops/github/manual-fetch",
        json={
            "start_date": "2026-04-01",
            "end_date": "2026-04-10",
            "query": '"speculative decoding"',
            "readme_prompt": "Decide if this repository is relevant to inference systems.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["request"] == {
        "query": '"speculative decoding" created:2026-04-01..2026-04-10',
        "start_date": "2026-04-01",
        "end_date": "2026-04-10",
        "readme_prompt": "Decide if this repository is relevant to inference systems.",
    }
    assert body["summary"] == {
        "coarse_count": 2,
        "readme_success_count": 2,
        "readme_failure_count": 0,
        "secondary_keep_count": 1,
    }
    assert body["coarse_results"] == [
        {
            "full_name": "acme/serve-fast",
            "name": "serve-fast",
            "owner_login": "acme",
            "html_url": "https://github.com/acme/serve-fast",
            "description": "High-throughput inference server",
            "stars": 120,
            "forks": 17,
            "language": "Python",
            "topics": ["inference", "serving"],
            "created_at": "2026-04-03T00:00:00Z",
            "updated_at": "2026-04-10T00:00:00Z",
            "pushed_at": "2026-04-10T00:00:00Z",
            "default_branch": "main",
            "readme_status": "ok",
        },
        {
            "full_name": "acme/dev-notes",
            "name": "dev-notes",
            "owner_login": "acme",
            "html_url": "https://github.com/acme/dev-notes",
            "description": "Research notes",
            "stars": 12,
            "forks": 2,
            "language": "Markdown",
            "topics": ["notes"],
            "created_at": "2026-04-04T00:00:00Z",
            "updated_at": "2026-04-10T00:00:00Z",
            "pushed_at": "2026-04-10T00:00:00Z",
            "default_branch": "main",
            "readme_status": "ok",
        },
    ]
    assert body["secondary_results"] == [
        {
            "full_name": "acme/serve-fast",
            "name": "serve-fast",
            "owner_login": "acme",
            "html_url": "https://github.com/acme/serve-fast",
            "description": "High-throughput inference server",
            "stars": 120,
            "forks": 17,
            "language": "Python",
            "topics": ["inference", "serving"],
            "created_at": "2026-04-03T00:00:00Z",
            "updated_at": "2026-04-10T00:00:00Z",
            "pushed_at": "2026-04-10T00:00:00Z",
            "default_branch": "main",
            "readme_status": "ok",
            "reason_zh": "README 明确描述了推理服务能力。",
            "matched_signals": ["serving", "throughput"],
        }
    ]
    assert body["errors"] == []
    assert github_client.queries == ['"speculative decoding" created:2026-04-01..2026-04-10']
    assert ai_filter.calls == [
        {
            "full_name": "acme/serve-fast",
            "readme_text": "README serving and throughput details",
            "prompt": "Decide if this repository is relevant to inference systems.",
        },
        {
            "full_name": "acme/dev-notes",
            "readme_text": "README with personal notes only",
            "prompt": "Decide if this repository is relevant to inference systems.",
        },
    ]


def test_manual_fetch_rejects_invalid_date_range() -> None:
    client = _make_client(
        github_client=_FakeGitHubClient([], {}),
        github_readme_ai_filter=_FakeReadmeAIFilter({}),
    )

    response = client.post(
        "/ops/github/manual-fetch",
        json={
            "start_date": "2026-04-10",
            "end_date": "2026-04-01",
            "query": '"speculative decoding"',
            "readme_prompt": "Decide if this repository is relevant to inference systems.",
        },
    )

    assert response.status_code == 422
    assert "start_date" in response.text
    assert "end_date" in response.text


def test_manual_fetch_rejects_blank_query() -> None:
    client = _make_client(
        github_client=_FakeGitHubClient([], {}),
        github_readme_ai_filter=_FakeReadmeAIFilter({}),
    )

    response = client.post(
        "/ops/github/manual-fetch",
        json={
            "start_date": "2026-04-01",
            "end_date": "2026-04-10",
            "query": "   ",
            "readme_prompt": "Decide if this repository is relevant to inference systems.",
        },
    )

    assert response.status_code == 422
    assert "query" in response.text


def test_manual_fetch_blank_prompt_falls_back_to_default_prompt() -> None:
    github_client = _FakeGitHubClient(
        [
            {
                "full_name": "acme/serve-fast",
                "name": "serve-fast",
                "owner": {"login": "acme"},
                "html_url": "https://github.com/acme/serve-fast",
                "description": "High-throughput inference server",
                "stargazers_count": 120,
                "forks_count": 17,
                "language": "Python",
                "topics": ["inference", "serving"],
                "created_at": "2026-04-03T00:00:00Z",
                "updated_at": "2026-04-10T00:00:00Z",
                "pushed_at": "2026-04-10T00:00:00Z",
                "default_branch": "main",
            }
        ],
        readmes={"acme/serve-fast": "README serving and throughput details"},
    )
    ai_filter = _FakeReadmeAIFilter(
        {
            "acme/serve-fast": {
                "keep": True,
                "reason_zh": "README 明确描述了推理服务能力。",
                "matched_signals": ["serving", "throughput"],
            }
        }
    )
    default_prompt = "Use the configured default README prompt."
    client = _make_client(
        github_client=github_client,
        github_readme_ai_filter=ai_filter,
        default_prompt=default_prompt,
    )

    response = client.post(
        "/ops/github/manual-fetch",
        json={
            "start_date": "2026-04-01",
            "end_date": "2026-04-10",
            "query": '"speculative decoding"',
            "readme_prompt": "   ",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["request"]["readme_prompt"] == default_prompt
    assert ai_filter.calls == [
        {
            "full_name": "acme/serve-fast",
            "readme_text": "README serving and throughput details",
            "prompt": default_prompt,
        }
    ]



def test_manual_fetch_reports_readme_fetch_errors() -> None:
    items = [
        {
            "full_name": "acme/serve-fast",
            "name": "serve-fast",
            "owner": {"login": "acme"},
            "html_url": "https://github.com/acme/serve-fast",
            "description": "High-throughput inference server",
            "stargazers_count": 120,
            "forks_count": 17,
        },
        {
            "full_name": "acme/broken-readme",
            "name": "broken-readme",
            "owner": {"login": "acme"},
            "html_url": "https://github.com/acme/broken-readme",
            "description": "Broken README fetch",
            "stargazers_count": 7,
            "forks_count": 1,
        },
    ]
    github_client = _FakeGitHubClient(
        items,
        readmes={
            "acme/serve-fast": "README throughput docs",
            "acme/broken-readme": RuntimeError("github readme down"),
        },
    )
    ai_filter = _FakeReadmeAIFilter(
        {
            "acme/serve-fast": {
                "keep": False,
                "reason_zh": "README 不够相关。",
                "matched_signals": [],
            }
        }
    )
    client = _make_client(github_client=github_client, github_readme_ai_filter=ai_filter)

    response = client.post(
        "/ops/github/manual-fetch",
        json={
            "start_date": "2026-04-01",
            "end_date": "2026-04-10",
            "query": "kv cache",
            "readme_prompt": "Decide if this repository is relevant to inference systems.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {
        "coarse_count": 2,
        "readme_success_count": 1,
        "readme_failure_count": 1,
        "secondary_keep_count": 0,
    }
    assert body["errors"] == [
        {
            "full_name": "acme/broken-readme",
            "stage": "readme_fetch",
            "message": "github readme down",
        }
    ]
    assert body["coarse_results"][1]["readme_status"] == "fetch_error"
    assert body["secondary_results"] == []


def test_manual_fetch_counts_and_reports_missing_readme() -> None:
    items = [
        {
            "full_name": "acme/serve-fast",
            "name": "serve-fast",
            "owner": {"login": "acme"},
            "html_url": "https://github.com/acme/serve-fast",
            "description": "High-throughput inference server",
            "stargazers_count": 120,
            "forks_count": 17,
        },
        {
            "full_name": "acme/no-readme",
            "name": "no-readme",
            "owner": {"login": "acme"},
            "html_url": "https://github.com/acme/no-readme",
            "description": "Repository without a README",
            "stargazers_count": 7,
            "forks_count": 1,
        },
    ]
    github_client = _FakeGitHubClient(
        items,
        readmes={
            "acme/serve-fast": "README throughput docs",
            "acme/no-readme": None,
        },
    )
    ai_filter = _FakeReadmeAIFilter(
        {
            "acme/serve-fast": {
                "keep": False,
                "reason_zh": "README 不够相关。",
                "matched_signals": [],
            }
        }
    )
    client = _make_client(github_client=github_client, github_readme_ai_filter=ai_filter)

    response = client.post(
        "/ops/github/manual-fetch",
        json={
            "start_date": "2026-04-01",
            "end_date": "2026-04-10",
            "query": "kv cache",
            "readme_prompt": "Decide if this repository is relevant to inference systems.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {
        "coarse_count": 2,
        "readme_success_count": 1,
        "readme_failure_count": 1,
        "secondary_keep_count": 0,
    }
    assert body["errors"] == [
        {
            "full_name": "acme/no-readme",
            "stage": "readme_fetch",
            "message": "README not found.",
        }
    ]
    assert body["coarse_results"][1]["readme_status"] == "missing_readme"
    assert body["secondary_results"] == []



def test_manual_fetch_fails_clearly_when_ai_filter_runtime_is_missing() -> None:
    github_client = _ExplodingGitHubClient()
    client = _make_client(github_client=github_client, github_readme_ai_filter=None)

    response = client.post(
        "/ops/github/manual-fetch",
        json={
            "start_date": "2026-04-01",
            "end_date": "2026-04-10",
            "query": "kv cache",
            "readme_prompt": "Decide if this repository is relevant to inference systems.",
        },
    )

    assert response.status_code == 503
    assert "README AI filtering is unavailable" in response.json()["detail"]
    assert github_client.called is False
