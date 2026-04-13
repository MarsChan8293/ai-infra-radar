# Hugging Face Models Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Hugging Face Models as the next source adapter so users can monitor one or more organizations for new models and metadata-timestamp updates through the existing alerting and digest pipeline.

**Architecture:** Reuse the current modular-monolith shape: a Hugging Face client fetches organization model listings, a pipeline normalizes each model into the shared observation structure, a job orchestrates polling and change detection, and `AlertService` emits Hugging Face-specific alerts through the shared dispatcher and digest flow. No new storage engine, worker process, or API surface is introduced; the new source plugs into the existing scheduler, `/jobs/run/{job_name}`, and `/alerts` endpoints.

**Tech Stack:** Python 3.12, FastAPI, APScheduler, Pydantic v2, SQLAlchemy 2.x, httpx, pytest, respx, SQLite

---

## File Map

- Create: `radar/sources/huggingface/__init__.py` — package marker
- Create: `radar/sources/huggingface/client.py` — Hugging Face organization model fetch client
- Create: `radar/sources/huggingface/pipeline.py` — normalization helpers for model records
- Create: `radar/jobs/huggingface_models.py` — organization polling job
- Modify: `radar/core/config.py` — add `huggingface` source settings and validation
- Modify: `radar/core/repositories.py` — add entity/observation lookup helpers for change detection
- Modify: `radar/alerts/service.py` — add `process_huggingface_model(...)`
- Modify: `radar/app.py` — wire Hugging Face client + scheduler registration into `build_runtime`
- Modify: `README.md` — document Hugging Face source config and manual trigger
- Create: `tests/fixtures/huggingface/models_by_org.json` — stable API fixture
- Create: `tests/sources/huggingface/__init__.py` — package marker
- Create: `tests/sources/huggingface/test_models_pipeline.py` — config, client, pipeline, and job coverage
- Modify: `tests/core/test_config.py` — Hugging Face config validation coverage
- Modify: `tests/smoke/test_mvp_paths.py` — add Hugging Face smoke path

### Task 1: Add Hugging Face source settings and config validation

**Files:**
- Modify: `radar/core/config.py`
- Modify: `tests/core/test_config.py`

- [ ] **Step 1: Write the failing config tests**

```python
# tests/core/test_config.py
def test_huggingface_enabled_requires_organizations(tmp_path: Path) -> None:
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
```

- [ ] **Step 2: Run the config tests to verify they fail**

Run: `python -m pytest tests/core/test_config.py -q`
Expected: FAIL with a Pydantic validation error because `huggingface` is not yet part of `SourceSettings`

- [ ] **Step 3: Add the Hugging Face settings models**

```python
# radar/core/config.py
class HuggingFaceSettings(BaseModel):
    model_config = _FORBID
    enabled: bool
    organizations: list[str] = []

    @model_validator(mode="after")
    def _require_orgs_when_enabled(self) -> "HuggingFaceSettings":
        if self.enabled and not self.organizations:
            raise ValueError("organizations must contain at least one entry when huggingface is enabled")
        return self


class SourceSettings(BaseModel):
    model_config = _FORBID
    github: GitHubSettings
    official_pages: OfficialPagesSettings
    huggingface: HuggingFaceSettings
```

- [ ] **Step 4: Re-run the config tests**

Run: `python -m pytest tests/core/test_config.py -q`
Expected: PASS

- [ ] **Step 5: Commit the config slice**

```bash
git add radar/core/config.py tests/core/test_config.py
git commit -m "feat: add huggingface source settings"
```

### Task 2: Add repository lookup helpers for Hugging Face change detection

**Files:**
- Modify: `radar/core/repositories.py`
- Create: `tests/sources/huggingface/test_models_pipeline.py`

- [ ] **Step 1: Write the failing repository helper tests**

```python
# tests/sources/huggingface/test_models_pipeline.py
def test_get_entity_by_canonical_name_returns_existing(repo: RadarRepository) -> None:
    entity = repo.upsert_entity(
        source="huggingface",
        entity_type="model",
        canonical_name="huggingface:deepseek/deepseek-v3",
        display_name="deepseek/deepseek-v3",
        url="https://huggingface.co/deepseek/deepseek-v3",
    )

    fetched = repo.get_entity_by_canonical_name("huggingface:deepseek/deepseek-v3")
    assert fetched is not None
    assert fetched.id == entity.id


def test_get_latest_observation_for_entity_returns_last_snapshot(repo: RadarRepository) -> None:
    entity = repo.upsert_entity(
        source="huggingface",
        entity_type="model",
        canonical_name="huggingface:deepseek/deepseek-v3",
        display_name="deepseek/deepseek-v3",
        url="https://huggingface.co/deepseek/deepseek-v3",
    )
    repo.record_observation(
        entity_id=entity.id,
        source="huggingface",
        raw_payload={"lastModified": "2026-04-06T00:00:00Z"},
        normalized_payload={"last_modified": "2026-04-06T00:00:00Z"},
        dedupe_key="hf:obs:1",
        content_hash="hash-1",
    )
    latest = repo.record_observation(
        entity_id=entity.id,
        source="huggingface",
        raw_payload={"lastModified": "2026-04-07T00:00:00Z"},
        normalized_payload={"last_modified": "2026-04-07T00:00:00Z"},
        dedupe_key="hf:obs:2",
        content_hash="hash-2",
    )

    fetched = repo.get_latest_observation_for_entity(entity.id, source="huggingface")
    assert fetched is not None
    assert fetched.id == latest.id
```

- [ ] **Step 2: Run the repository helper tests to verify they fail**

Run: `python -m pytest tests/sources/huggingface/test_models_pipeline.py -q`
Expected: FAIL with `AttributeError: 'RadarRepository' object has no attribute 'get_entity_by_canonical_name'`

- [ ] **Step 3: Add the minimal repository helpers**

```python
# radar/core/repositories.py
def get_entity_by_canonical_name(self, canonical_name: str) -> Entity | None:
    with self._session_factory() as session:
        return session.scalar(
            select(Entity).where(Entity.canonical_name == canonical_name)
        )


def get_latest_observation_for_entity(
    self,
    entity_id: int,
    *,
    source: str,
) -> Observation | None:
    with self._session_factory() as session:
        return session.scalar(
            select(Observation)
            .where(Observation.entity_id == entity_id, Observation.source == source)
            .order_by(Observation.id.desc())
        )
```

- [ ] **Step 4: Re-run the repository helper tests**

Run: `python -m pytest tests/sources/huggingface/test_models_pipeline.py -q`
Expected: PASS for the two helper tests

- [ ] **Step 5: Commit the repository helper slice**

```bash
git add radar/core/repositories.py tests/sources/huggingface/test_models_pipeline.py
git commit -m "feat: add huggingface repository lookup helpers"
```

### Task 3: Add Hugging Face client and normalization pipeline

**Files:**
- Create: `radar/sources/huggingface/__init__.py`
- Create: `radar/sources/huggingface/client.py`
- Create: `radar/sources/huggingface/pipeline.py`
- Create: `tests/fixtures/huggingface/models_by_org.json`
- Create: `tests/sources/huggingface/__init__.py`
- Modify: `tests/sources/huggingface/test_models_pipeline.py`

- [ ] **Step 1: Add the Hugging Face fixture**

```json
{
  "items": [
    {
      "id": "deepseek/deepseek-v3",
      "author": "deepseek",
      "lastModified": "2026-04-07T00:00:00Z",
      "private": false,
      "gated": false,
      "downloads": 123456
    },
    {
      "id": "deepseek/deepseek-r1",
      "author": "deepseek",
      "lastModified": "2026-04-06T00:00:00Z",
      "private": false,
      "gated": true,
      "downloads": 654321
    }
  ]
}
```

- [ ] **Step 2: Write the failing client and pipeline tests**

```python
# tests/sources/huggingface/test_models_pipeline.py
@respx.mock
def test_huggingface_client_lists_models_for_organization() -> None:
    payload = json.loads(Path("tests/fixtures/huggingface/models_by_org.json").read_text())
    route = respx.get("https://huggingface.co/api/models").mock(
        return_value=httpx.Response(200, json=payload["items"])
    )

    client = HuggingFaceClient()
    items = client.list_models_for_organization("deepseek")

    assert route.called
    assert items[0]["id"] == "deepseek/deepseek-v3"


def test_build_huggingface_observation_normalizes_core_fields() -> None:
    item = json.loads(Path("tests/fixtures/huggingface/models_by_org.json").read_text())["items"][0]
    observation = build_huggingface_observation(item)

    assert observation["canonical_name"] == "huggingface:deepseek/deepseek-v3"
    assert observation["display_name"] == "deepseek/deepseek-v3"
    assert observation["url"] == "https://huggingface.co/deepseek/deepseek-v3"
    assert observation["normalized_payload"]["last_modified"] == "2026-04-07T00:00:00Z"
```

- [ ] **Step 3: Run the source tests to verify they fail**

Run: `python -m pytest tests/sources/huggingface/test_models_pipeline.py -q`
Expected: FAIL with missing `radar.sources.huggingface` modules

- [ ] **Step 4: Implement the client and normalization helpers**

```python
# radar/sources/huggingface/client.py
class HuggingFaceClient:
    def __init__(self, timeout: float = 15.0) -> None:
        self._timeout = timeout

    def list_models_for_organization(self, organization: str) -> list[dict]:
        response = httpx.get(
            "https://huggingface.co/api/models",
            params={"author": organization, "full": "true"},
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()
```

```python
# radar/sources/huggingface/pipeline.py
def build_huggingface_observation(item: dict) -> dict:
    model_id = item["id"]
    last_modified = item["lastModified"]
    content_hash = hashlib.sha256(f"{model_id}|{last_modified}".encode()).hexdigest()
    return {
        "canonical_name": f"huggingface:{model_id}",
        "display_name": model_id,
        "url": f"https://huggingface.co/{model_id}",
        "content_hash": content_hash,
        "raw_payload": item,
        "normalized_payload": {
            "model_id": model_id,
            "organization": model_id.split("/", 1)[0],
            "last_modified": last_modified,
            "private": item.get("private", False),
            "gated": item.get("gated", False),
            "downloads": item.get("downloads"),
            "content_hash": content_hash,
        },
    }
```

- [ ] **Step 5: Re-run the source tests**

Run: `python -m pytest tests/sources/huggingface/test_models_pipeline.py -q`
Expected: PASS for the client and normalization tests

- [ ] **Step 6: Commit the source adapter slice**

```bash
git add radar/sources/huggingface/__init__.py radar/sources/huggingface/client.py radar/sources/huggingface/pipeline.py tests/fixtures/huggingface/models_by_org.json tests/sources/huggingface/__init__.py tests/sources/huggingface/test_models_pipeline.py
git commit -m "feat: add huggingface source client and pipeline"
```

### Task 4: Add Hugging Face alert processing and polling job

**Files:**
- Modify: `radar/alerts/service.py`
- Create: `radar/jobs/huggingface_models.py`
- Modify: `tests/sources/huggingface/test_models_pipeline.py`

- [ ] **Step 1: Write the failing job and alert-service tests**

```python
# tests/sources/huggingface/test_models_pipeline.py
def test_process_huggingface_model_creates_new_model_alert(repo: RadarRepository) -> None:
    dispatcher = AlertDispatcher(repository=repo, send_webhook=lambda url, payload: None)
    service = AlertService(repository=repo, dispatcher=dispatcher, channels={"webhook": "https://hooks.example.com/test"})
    item = json.loads(Path("tests/fixtures/huggingface/models_by_org.json").read_text())["items"][0]
    observation = build_huggingface_observation(item)

    created = service.process_huggingface_model(observation)

    assert created == 1
    assert repo.list_alerts()[0].alert_type == "huggingface_model_new"


def test_process_huggingface_model_skips_unchanged_model(repo: RadarRepository) -> None:
    item = json.loads(Path("tests/fixtures/huggingface/models_by_org.json").read_text())["items"][0]
    observation = build_huggingface_observation(item)
    dispatcher = AlertDispatcher(repository=repo, send_webhook=lambda url, payload: None)
    service = AlertService(repository=repo, dispatcher=dispatcher, channels={"webhook": "https://hooks.example.com/test"})

    first = service.process_huggingface_model(observation)
    second = service.process_huggingface_model(observation)

    assert first == 1
    assert second == 0


def test_run_huggingface_models_job_returns_created_count(repo: RadarRepository) -> None:
    item = json.loads(Path("tests/fixtures/huggingface/models_by_org.json").read_text())["items"][0]

    class FakeAlertService:
        def process_huggingface_model(self, observation: dict) -> int:
            assert observation["canonical_name"] == "huggingface:deepseek/deepseek-v3"
            return 1

    created = run_huggingface_models_job([item], repository=repo, alert_service=FakeAlertService())
    assert created == 1
```

- [ ] **Step 2: Run the Hugging Face tests to verify they fail**

Run: `python -m pytest tests/sources/huggingface/test_models_pipeline.py -q`
Expected: FAIL with missing `process_huggingface_model` and missing `run_huggingface_models_job`

- [ ] **Step 3: Implement alert processing and polling job**

```python
# radar/alerts/service.py
def process_huggingface_model(self, observation: dict) -> int:
    normalized = observation["normalized_payload"]
    canonical_name = observation["canonical_name"]
    existing_entity = self._repo.get_entity_by_canonical_name(canonical_name)
    existing_observation = (
        self._repo.get_latest_observation_for_entity(existing_entity.id, source="huggingface")
        if existing_entity is not None
        else None
    )
    is_new = existing_entity is None
    if existing_observation is not None:
        previous_last_modified = existing_observation.normalized_payload["last_modified"]
        if previous_last_modified == normalized["last_modified"]:
            return 0

    entity = self._repo.upsert_entity(
        source="huggingface",
        entity_type="model",
        canonical_name=canonical_name,
        display_name=observation["display_name"],
        url=observation["url"],
    )
    self._repo.record_observation(
        entity_id=entity.id,
        source="huggingface",
        raw_payload=observation["raw_payload"],
        normalized_payload=normalized,
        dedupe_key=observation["content_hash"],
        content_hash=observation["content_hash"],
    )
    alert_type = "huggingface_model_new" if is_new else "huggingface_model_updated"
    return self.emit_alert(
        alert_type=alert_type,
        entity_id=entity.id,
        source="huggingface",
        score=1.0,
        dedupe_key=f"hf:{alert_type}:{normalized['model_id']}:{normalized['last_modified']}",
        reason={"model_id": normalized["model_id"], "last_modified": normalized["last_modified"]},
        alert_payload={"title": normalized["model_id"], "url": observation["url"], "score": 1.0},
    )
```

```python
# radar/jobs/huggingface_models.py
def run_huggingface_models_job(
    items: list[dict],
    *,
    repository,
    alert_service,
) -> int:
    created = 0
    for item in items:
        observation = build_huggingface_observation(item)
        created += alert_service.process_huggingface_model(observation)
    return created
```

- [ ] **Step 4: Re-run the Hugging Face tests**

Run: `python -m pytest tests/sources/huggingface/test_models_pipeline.py -q`
Expected: PASS

- [ ] **Step 5: Commit the Hugging Face job slice**

```bash
git add radar/alerts/service.py radar/jobs/huggingface_models.py tests/sources/huggingface/test_models_pipeline.py
git commit -m "feat: add huggingface models alert job"
```

### Task 5: Wire Hugging Face into runtime, smoke tests, and docs

**Files:**
- Modify: `radar/app.py`
- Modify: `tests/core/test_config.py`
- Modify: `tests/smoke/test_mvp_paths.py`
- Modify: `README.md`

- [ ] **Step 1: Write the failing runtime and smoke tests**

```python
# tests/smoke/test_mvp_paths.py
def test_huggingface_path_smoke(repo, alert_service) -> None:
    item = {
        "id": "deepseek/deepseek-v3",
        "author": "deepseek",
        "lastModified": "2026-04-07T00:00:00Z",
        "private": False,
        "gated": False,
    }

    created = run_huggingface_models_job(
        [item],
        repository=repo,
        alert_service=alert_service,
    )

    assert created == 1
    assert repo.list_alerts()[0].alert_type == "huggingface_model_new"
```

```python
# tests/core/test_config.py
def test_runtime_registers_huggingface_job(tmp_path: Path) -> None:
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

    runtime = build_runtime(config_path)
    assert "huggingface_models" in runtime.scheduler.known_jobs()
```

- [ ] **Step 2: Run the runtime and smoke tests to verify they fail**

Run: `python -m pytest tests/core/test_config.py tests/smoke/test_mvp_paths.py -q`
Expected: FAIL because `build_runtime()` does not yet register a Hugging Face job

- [ ] **Step 3: Wire Hugging Face into `build_runtime()` and update docs**

```python
# radar/app.py
from radar.jobs.huggingface_models import run_huggingface_models_job
from radar.sources.huggingface.client import HuggingFaceClient

@dataclass
class RuntimeState:
    settings: Settings
    config_path: Path
    engine: Any
    repo: RadarRepository
    scheduler: RadarScheduler
    alert_service: AlertService
    github_client: GitHubClient
    huggingface_client: HuggingFaceClient


if settings.sources.huggingface.enabled:
    huggingface_client = HuggingFaceClient()

    def _run_huggingface_models() -> int:
        items: list[dict] = []
        for organization in settings.sources.huggingface.organizations:
            items.extend(huggingface_client.list_models_for_organization(organization))
        return run_huggingface_models_job(
            items,
            repository=repo,
            alert_service=alert_service,
        )

    scheduler.register("huggingface_models", _run_huggingface_models, minutes=20)
else:
    huggingface_client = HuggingFaceClient()
```

```md
<!-- README.md -->
sources:
  huggingface:
    enabled: true
    organizations:
      - deepseek

# Trigger a Hugging Face scan manually
curl -X POST http://localhost:8000/jobs/run/huggingface_models
```

- [ ] **Step 4: Re-run the runtime and smoke tests**

Run: `python -m pytest tests/core/test_config.py tests/smoke/test_mvp_paths.py -q`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 6: Commit the runtime/docs slice**

```bash
git add radar/app.py tests/smoke/test_mvp_paths.py README.md tests/core/test_config.py
git commit -m "feat: wire huggingface models into runtime"
```
