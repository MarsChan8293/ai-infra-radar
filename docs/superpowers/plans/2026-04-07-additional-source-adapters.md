# Additional Source Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ModelScope, Modelers, and GitCode as source adapters that publish new/update alerts through the existing radar runtime.

**Architecture:** Implement three independent vertical slices that reuse the existing source-adapter pattern: source-specific client, source-specific normalization pipeline, source-specific job, and one `AlertService` entrypoint per source. Keep runtime wiring in `radar/app.py`, validation in `radar/core/config.py`, and CLI aliases in `radar/cli.py`, while preserving the per-organization resilience behavior already used by Hugging Face.

**Tech Stack:** Python 3.12, FastAPI runtime wiring, httpx, pytest, SQLAlchemy repository layer, existing alert/dispatcher pipeline

---

## Scope Check

This plan covers one coherent family of work: three more source adapters that follow the same runtime pattern. They are implemented as separate source slices so each one remains testable and reviewable on its own.

## File Map

- Create: `radar/sources/modelscope/client.py` — fetch ModelScope model listings for an organization
- Create: `radar/sources/modelscope/pipeline.py` — normalize ModelScope items
- Create: `radar/jobs/modelscope_models.py` — poll/normalize/dispatch ModelScope items
- Create: `tests/sources/modelscope/test_models_pipeline.py` — ModelScope client, pipeline, and job coverage
- Create: `radar/sources/modelers/client.py` — fetch Modelers model listings for an organization
- Create: `radar/sources/modelers/pipeline.py` — normalize Modelers items
- Create: `radar/jobs/modelers_models.py` — poll/normalize/dispatch Modelers items
- Create: `tests/sources/modelers/test_models_pipeline.py` — Modelers client, pipeline, and job coverage
- Create: `radar/sources/gitcode/client.py` — fetch GitCode organization repositories with token auth
- Create: `radar/sources/gitcode/pipeline.py` — normalize GitCode repo items
- Create: `radar/jobs/gitcode_repos.py` — poll/normalize/dispatch GitCode repos
- Create: `tests/sources/gitcode/test_repos_pipeline.py` — GitCode client, pipeline, and job coverage
- Modify: `radar/alerts/service.py` — add per-source process methods
- Modify: `radar/app.py` — instantiate clients and register new jobs
- Modify: `radar/core/config.py` — add three new settings blocks and validation
- Modify: `radar/cli.py` — add `backfill-source` aliases
- Modify: `tests/api/test_config.py` — runtime registration and per-org failure continuation coverage
- Modify: `tests/core/test_config.py` — config and CLI alias coverage
- Modify: `tests/smoke/test_mvp_paths.py` — smoke path assertions
- Modify: `README.md` — document config and job usage

## Task 1: Add the ModelScope source slice

**Files:**
- Create: `radar/sources/modelscope/client.py`
- Create: `radar/sources/modelscope/pipeline.py`
- Create: `radar/jobs/modelscope_models.py`
- Modify: `radar/alerts/service.py`
- Modify: `radar/core/config.py`
- Modify: `radar/app.py`
- Modify: `radar/cli.py`
- Modify: `tests/api/test_config.py`
- Modify: `tests/core/test_config.py`
- Create: `tests/sources/modelscope/test_models_pipeline.py`

- [ ] **Step 1: Write the failing ModelScope tests**

```python
import httpx
import pytest
import respx

from radar.jobs.modelscope_models import run_modelscope_models_job
from radar.sources.modelscope.client import ModelScopeClient
from radar.sources.modelscope.pipeline import build_modelscope_observation


@respx.mock
def test_modelscope_client_lists_models_for_organization() -> None:
    route = respx.put("https://www.modelscope.cn/api/v1/models/").mock(
        return_value=httpx.Response(
            200,
            json={
                "Code": 200,
                "Success": True,
                "Data": {
                    "Models": [
                        {
                            "Id": 665336,
                            "Name": "Qwen3.5-397B-A17B",
                            "Path": "Qwen",
                            "CreatedTime": 1771213910,
                            "LastUpdatedTime": 1772414875,
                            "Downloads": 98560,
                        }
                    ],
                    "TotalCount": 1,
                },
            },
        )
    )

    client = ModelScopeClient()
    items = client.list_models_for_organization("Qwen")

    assert route.called
    assert items[0]["Name"] == "Qwen3.5-397B-A17B"
    assert items[0]["Path"] == "Qwen"


def test_build_modelscope_observation_maps_fields() -> None:
    observation = build_modelscope_observation(
        {
            "Id": 665336,
            "Name": "Qwen3.5-397B-A17B",
            "Path": "Qwen",
            "CreatedTime": 1771213910,
            "LastUpdatedTime": 1772414875,
            "Downloads": 98560,
        }
    )

    assert observation["canonical_name"] == "modelscope:Qwen/Qwen3.5-397B-A17B"
    assert observation["url"] == "https://www.modelscope.cn/models/Qwen/Qwen3.5-397B-A17B"
    assert observation["normalized_payload"]["last_updated_time"] == 1772414875


def test_run_modelscope_models_job_processes_items(alert_service) -> None:
    created = run_modelscope_models_job(
        [
            {
                "Id": 665336,
                "Name": "Qwen3.5-397B-A17B",
                "Path": "Qwen",
                "CreatedTime": 1771213910,
                "LastUpdatedTime": 1772414875,
                "Downloads": 98560,
            }
        ],
        alert_service=alert_service,
    )

    assert created == 1
```

- [ ] **Step 2: Run the ModelScope tests to verify they fail**

Run: `python3 -m pytest tests/sources/modelscope/test_models_pipeline.py -q`
Expected: FAIL because the ModelScope modules and job do not exist yet

- [ ] **Step 3: Implement the minimal ModelScope client, pipeline, job, and alert path**

```python
# radar/sources/modelscope/client.py
from __future__ import annotations

import httpx


class ModelScopeClient:
    def __init__(self, timeout: float = 15.0) -> None:
        self._timeout = timeout

    def list_models_for_organization(self, organization: str, page_size: int = 100) -> list[dict]:
        response = httpx.put(
            "https://www.modelscope.cn/api/v1/models/",
            json={"Path": organization, "PageNumber": 1, "PageSize": page_size},
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return payload["Data"]["Models"]
```

```python
# radar/sources/modelscope/pipeline.py
from __future__ import annotations

import hashlib


def build_modelscope_observation(item: dict) -> dict:
    model_id = f"{item['Path']}/{item['Name']}"
    last_updated_time = item["LastUpdatedTime"]
    content_hash = hashlib.sha256(f"{model_id}|{last_updated_time}".encode()).hexdigest()
    return {
        "canonical_name": f"modelscope:{model_id}",
        "display_name": model_id,
        "url": f"https://www.modelscope.cn/models/{model_id}",
        "content_hash": content_hash,
        "raw_payload": item,
        "normalized_payload": {
            "model_id": model_id,
            "organization": item["Path"],
            "modelscope_id": item["Id"],
            "created_time": item["CreatedTime"],
            "last_updated_time": last_updated_time,
            "downloads": item.get("Downloads"),
            "content_hash": content_hash,
        },
    }
```

```python
# radar/jobs/modelscope_models.py
from __future__ import annotations

from radar.sources.modelscope.pipeline import build_modelscope_observation


def run_modelscope_models_job(items: list[dict], *, alert_service) -> int:
    created = 0
    for item in items:
        observation = build_modelscope_observation(item)
        created += alert_service.process_modelscope_model(observation)
    return created
```

```python
# radar/alerts/service.py
    def process_modelscope_model(self, observation: dict) -> int:
        normalized = observation["normalized_payload"]
        canonical_name = observation["canonical_name"]
        existing_entity = self._repo.get_entity_by_canonical_name(canonical_name)
        existing_observation = (
            self._repo.get_latest_observation_for_entity(existing_entity.id, source="modelscope")
            if existing_entity is not None
            else None
        )
        is_new = existing_entity is None
        if existing_observation is not None:
            if existing_observation.normalized_payload["last_updated_time"] == normalized["last_updated_time"]:
                return 0

        entity = self._repo.upsert_entity(
            source="modelscope",
            entity_type="model",
            canonical_name=canonical_name,
            display_name=observation["display_name"],
            url=observation["url"],
        )
        self._repo.record_observation(
            entity_id=entity.id,
            source="modelscope",
            raw_payload=observation["raw_payload"],
            normalized_payload=normalized,
            dedupe_key=observation["content_hash"],
            content_hash=observation["content_hash"],
        )
        alert_type = "modelscope_model_new" if is_new else "modelscope_model_updated"
        return self.emit_alert(
            alert_type=alert_type,
            entity_id=entity.id,
            source="modelscope",
            score=1.0,
            dedupe_key=f"modelscope:{alert_type}:{normalized['model_id']}:{normalized['last_updated_time']}",
            reason={
                "model_id": normalized["model_id"],
                "last_updated_time": normalized["last_updated_time"],
            },
            alert_payload={
                "title": normalized["model_id"],
                "url": observation["url"],
                "score": 1.0,
            },
        )
```

- [ ] **Step 4: Wire ModelScope config, runtime job registration, and CLI alias**

```python
# radar/core/config.py
class ModelScopeSettings(BaseModel):
    model_config = _FORBID
    enabled: bool
    organizations: list[str] = []

    @model_validator(mode="after")
    def _require_orgs_when_enabled(self) -> "ModelScopeSettings":
        if self.enabled and not self.organizations:
            raise ValueError("organizations must contain at least one entry when modelscope is enabled")
        return self
```

```python
# radar/app.py
from radar.jobs.modelscope_models import run_modelscope_models_job
from radar.sources.modelscope.client import ModelScopeClient

modelscope_client = ModelScopeClient()

if settings.sources.modelscope.enabled:
    def _run_modelscope_models() -> int:
        created = 0
        failures: list[tuple[str, Exception]] = []
        for organization in settings.sources.modelscope.organizations:
            try:
                items = modelscope_client.list_models_for_organization(organization)
            except Exception as exc:
                failures.append((organization, exc))
                continue
            created += run_modelscope_models_job(items, alert_service=alert_service)
        if failures:
            failed = ", ".join(f"{organization} ({exc})" for organization, exc in failures)
            raise RuntimeError(f"modelscope_models failed for organizations: {failed}")
        return created

    scheduler.register("modelscope_models", _run_modelscope_models, minutes=30)
```

```python
# radar/cli.py
_SOURCE_TO_JOB = {
    "official_pages": "official_pages",
    "github": "github_burst",
    "huggingface": "huggingface_models",
    "modelscope": "modelscope_models",
}
```

- [ ] **Step 5: Re-run the targeted ModelScope tests**

Run: `python3 -m pytest tests/sources/modelscope/test_models_pipeline.py tests/core/test_config.py tests/api/test_config.py -q`
Expected: PASS

- [ ] **Step 6: Commit the ModelScope slice**

```bash
git add radar/sources/modelscope/client.py radar/sources/modelscope/pipeline.py radar/jobs/modelscope_models.py radar/alerts/service.py radar/core/config.py radar/app.py radar/cli.py tests/sources/modelscope/test_models_pipeline.py tests/core/test_config.py tests/api/test_config.py
git commit -m "feat: add modelscope source adapter" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 2: Add the Modelers source slice

**Files:**
- Create: `radar/sources/modelers/client.py`
- Create: `radar/sources/modelers/pipeline.py`
- Create: `radar/jobs/modelers_models.py`
- Modify: `radar/alerts/service.py`
- Modify: `radar/core/config.py`
- Modify: `radar/app.py`
- Modify: `radar/cli.py`
- Modify: `tests/api/test_config.py`
- Modify: `tests/core/test_config.py`
- Create: `tests/sources/modelers/test_models_pipeline.py`

- [ ] **Step 1: Write the failing Modelers tests**

```python
import httpx
import respx

from radar.jobs.modelers_models import run_modelers_models_job
from radar.sources.modelers.client import ModelersClient
from radar.sources.modelers.pipeline import build_modelers_observation


@respx.mock
def test_modelers_client_lists_models_for_organization() -> None:
    route = respx.get("https://modelers.cn/server/model").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": "",
                "msg": "",
                "data": {
                    "total": 1,
                    "models": [
                        {
                            "id": "80838",
                            "owner": "MindSpore-Lab",
                            "name": "Qwen3-VL-30B-A3B-Instruct",
                            "created_at": 1759655730,
                            "updated_at": 1759662143,
                            "download_count": 3791,
                            "visibility": "public",
                        }
                    ],
                },
            },
        )
    )

    client = ModelersClient()
    items = client.list_models_for_organization("MindSpore-Lab")

    assert route.called
    assert items[0]["owner"] == "MindSpore-Lab"
```

- [ ] **Step 2: Run the Modelers tests to verify they fail**

Run: `python3 -m pytest tests/sources/modelers/test_models_pipeline.py -q`
Expected: FAIL because the Modelers modules and job do not exist yet

- [ ] **Step 3: Implement the minimal Modelers client, pipeline, job, and alert path**

```python
# radar/sources/modelers/client.py
from __future__ import annotations

import httpx


class ModelersClient:
    def __init__(self, timeout: float = 15.0) -> None:
        self._timeout = timeout

    def list_models_for_organization(self, organization: str, page_size: int = 100) -> list[dict]:
        response = httpx.get(
            "https://modelers.cn/server/model",
            params={
                "page_num": 1,
                "count_per_page": page_size,
                "count": "true",
                "owner": organization,
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()["data"]["models"]
```

```python
# radar/sources/modelers/pipeline.py
from __future__ import annotations

import hashlib


def build_modelers_observation(item: dict) -> dict:
    model_id = f"{item['owner']}/{item['name']}"
    updated_at = item["updated_at"]
    content_hash = hashlib.sha256(f"{model_id}|{updated_at}".encode()).hexdigest()
    return {
        "canonical_name": f"modelers:{model_id}",
        "display_name": model_id,
        "url": f"https://modelers.cn/models/{model_id}",
        "content_hash": content_hash,
        "raw_payload": item,
        "normalized_payload": {
            "model_id": model_id,
            "organization": item["owner"],
            "created_at": item["created_at"],
            "updated_at": updated_at,
            "download_count": item.get("download_count"),
            "visibility": item.get("visibility"),
            "content_hash": content_hash,
        },
    }
```

```python
# radar/jobs/modelers_models.py
from __future__ import annotations

from radar.sources.modelers.pipeline import build_modelers_observation


def run_modelers_models_job(items: list[dict], *, alert_service) -> int:
    created = 0
    for item in items:
        created += alert_service.process_modelers_model(build_modelers_observation(item))
    return created
```

- [ ] **Step 4: Wire Modelers config, runtime job registration, and CLI alias**

```python
# radar/core/config.py
class ModelersSettings(BaseModel):
    model_config = _FORBID
    enabled: bool
    organizations: list[str] = []

    @model_validator(mode="after")
    def _require_orgs_when_enabled(self) -> "ModelersSettings":
        if self.enabled and not self.organizations:
            raise ValueError("organizations must contain at least one entry when modelers is enabled")
        return self
```

```python
# radar/cli.py
_SOURCE_TO_JOB = {
    "official_pages": "official_pages",
    "github": "github_burst",
    "huggingface": "huggingface_models",
    "modelscope": "modelscope_models",
    "modelers": "modelers_models",
}
```

- [ ] **Step 5: Re-run the targeted Modelers tests**

Run: `python3 -m pytest tests/sources/modelers/test_models_pipeline.py tests/core/test_config.py tests/api/test_config.py -q`
Expected: PASS

- [ ] **Step 6: Commit the Modelers slice**

```bash
git add radar/sources/modelers/client.py radar/sources/modelers/pipeline.py radar/jobs/modelers_models.py radar/alerts/service.py radar/core/config.py radar/app.py radar/cli.py tests/sources/modelers/test_models_pipeline.py tests/core/test_config.py tests/api/test_config.py
git commit -m "feat: add modelers source adapter" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 3: Add the GitCode source slice

**Files:**
- Create: `radar/sources/gitcode/client.py`
- Create: `radar/sources/gitcode/pipeline.py`
- Create: `radar/jobs/gitcode_repos.py`
- Modify: `radar/alerts/service.py`
- Modify: `radar/core/config.py`
- Modify: `radar/app.py`
- Modify: `radar/cli.py`
- Modify: `tests/api/test_config.py`
- Modify: `tests/core/test_config.py`
- Create: `tests/sources/gitcode/test_repos_pipeline.py`

- [ ] **Step 1: Write the failing GitCode tests**

```python
import httpx
import pytest
import respx

from radar.jobs.gitcode_repos import run_gitcode_repos_job
from radar.sources.gitcode.client import GitCodeClient
from radar.sources.gitcode.pipeline import build_gitcode_observation


@respx.mock
def test_gitcode_client_lists_org_repositories() -> None:
    route = respx.get("https://api.gitcode.com/api/v5/orgs/gitcode/repos").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "full_name": "gitcode/example-repo",
                    "name": "example-repo",
                    "html_url": "https://gitcode.com/gitcode/example-repo",
                    "updated_at": "2024-01-08T10:03:24+08:00",
                }
            ],
        )
    )

    client = GitCodeClient(token="token")
    items = client.list_repositories_for_organization("gitcode")

    assert route.called
    assert items[0]["full_name"] == "gitcode/example-repo"


def test_build_gitcode_observation_maps_fields() -> None:
    observation = build_gitcode_observation(
        {
            "full_name": "gitcode/example-repo",
            "name": "example-repo",
            "html_url": "https://gitcode.com/gitcode/example-repo",
            "updated_at": "2024-01-08T10:03:24+08:00",
        }
    )

    assert observation["canonical_name"] == "gitcode:gitcode/example-repo"
    assert observation["normalized_payload"]["updated_at"] == "2024-01-08T10:03:24+08:00"
```

- [ ] **Step 2: Run the GitCode tests to verify they fail**

Run: `python3 -m pytest tests/sources/gitcode/test_repos_pipeline.py -q`
Expected: FAIL because the GitCode modules and job do not exist yet

- [ ] **Step 3: Implement the minimal GitCode client, pipeline, job, and alert path**

```python
# radar/sources/gitcode/client.py
from __future__ import annotations

import httpx


class GitCodeClient:
    def __init__(self, token: str, timeout: float = 15.0) -> None:
        self._token = token
        self._timeout = timeout

    def list_repositories_for_organization(self, organization: str, per_page: int = 100) -> list[dict]:
        response = httpx.get(
            f"https://api.gitcode.com/api/v5/orgs/{organization}/repos",
            params={"type": "public", "page": 1, "per_page": per_page},
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()
```

```python
# radar/sources/gitcode/pipeline.py
from __future__ import annotations

import hashlib


def build_gitcode_observation(item: dict) -> dict:
    full_name = item["full_name"]
    updated_at = item["updated_at"]
    content_hash = hashlib.sha256(f"{full_name}|{updated_at}".encode()).hexdigest()
    organization, _repo_name = full_name.split("/", 1)
    return {
        "canonical_name": f"gitcode:{full_name}",
        "display_name": full_name,
        "url": item["html_url"],
        "content_hash": content_hash,
        "raw_payload": item,
        "normalized_payload": {
            "full_name": full_name,
            "organization": organization,
            "repo_name": item["name"],
            "updated_at": updated_at,
            "content_hash": content_hash,
        },
    }
```

```python
# radar/jobs/gitcode_repos.py
from __future__ import annotations

from radar.sources.gitcode.pipeline import build_gitcode_observation


def run_gitcode_repos_job(items: list[dict], *, alert_service) -> int:
    created = 0
    for item in items:
        created += alert_service.process_gitcode_repository(build_gitcode_observation(item))
    return created
```

- [ ] **Step 4: Wire GitCode config, runtime job registration, and CLI alias**

```python
# radar/core/config.py
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
```

```python
# radar/cli.py
_SOURCE_TO_JOB = {
    "official_pages": "official_pages",
    "github": "github_burst",
    "huggingface": "huggingface_models",
    "modelscope": "modelscope_models",
    "modelers": "modelers_models",
    "gitcode": "gitcode_repos",
}
```

- [ ] **Step 5: Re-run the targeted GitCode tests**

Run: `python3 -m pytest tests/sources/gitcode/test_repos_pipeline.py tests/core/test_config.py tests/api/test_config.py -q`
Expected: PASS

- [ ] **Step 6: Commit the GitCode slice**

```bash
git add radar/sources/gitcode/client.py radar/sources/gitcode/pipeline.py radar/jobs/gitcode_repos.py radar/alerts/service.py radar/core/config.py radar/app.py radar/cli.py tests/sources/gitcode/test_repos_pipeline.py tests/core/test_config.py tests/api/test_config.py
git commit -m "feat: add gitcode source adapter" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 4: Document the new sources and run the regression set

**Files:**
- Modify: `README.md`
- Modify: `tests/smoke/test_mvp_paths.py`
- Test: `tests/sources/modelscope/test_models_pipeline.py`
- Test: `tests/sources/modelers/test_models_pipeline.py`
- Test: `tests/sources/gitcode/test_repos_pipeline.py`
- Test: `tests/api/test_config.py`
- Test: `tests/core/test_config.py`

- [ ] **Step 1: Write the failing README and smoke expectations**

```python
from pathlib import Path


def test_readme_mentions_additional_sources() -> None:
    readme = Path("README.md").read_text()

    assert "modelscope" in readme
    assert "modelers" in readme
    assert "gitcode" in readme
```

- [ ] **Step 2: Run the README/smoke expectations to verify they fail**

Run: `python3 -m pytest tests/smoke/test_mvp_paths.py -q`
Expected: FAIL because the smoke path and docs do not mention the new sources yet

- [ ] **Step 3: Update README and smoke coverage**

```md
sources:
  modelscope:
    enabled: true
    organizations:
      - Qwen

  modelers:
    enabled: true
    organizations:
      - MindSpore-Lab

  gitcode:
    enabled: true
    token: your-gitcode-token
    organizations:
      - gitcode
```

```python
# tests/smoke/test_mvp_paths.py
assert "modelscope_models" in runtime.scheduler.known_jobs()
assert "modelers_models" in runtime.scheduler.known_jobs()
assert "gitcode_repos" in runtime.scheduler.known_jobs()
```

- [ ] **Step 4: Run targeted regression tests**

Run: `python3 -m pytest tests/sources/modelscope/test_models_pipeline.py tests/sources/modelers/test_models_pipeline.py tests/sources/gitcode/test_repos_pipeline.py tests/api/test_config.py tests/core/test_config.py tests/smoke/test_mvp_paths.py -q`
Expected: PASS

- [ ] **Step 5: Run the full test suite**

Run: `python3 -m pytest -q`
Expected: PASS

- [ ] **Step 6: Commit the docs and verification state**

```bash
git add README.md tests/smoke/test_mvp_paths.py tests/sources/modelscope/test_models_pipeline.py tests/sources/modelers/test_models_pipeline.py tests/sources/gitcode/test_repos_pipeline.py tests/api/test_config.py tests/core/test_config.py
git commit -m "docs: document additional source adapters" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
