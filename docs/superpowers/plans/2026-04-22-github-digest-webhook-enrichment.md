# GitHub Digest Webhook Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `daily_digest` webhook items include `repo_name`, `repo_url`, and `repo_description` for GitHub entries so Feishu can map real repository metadata without manual payload crafting.

**Architecture:** Keep webhook fan-out in `radar.app` unchanged and enrich digest items earlier, inside the digest-construction path. Add one repository read helper that joins `Alert` and `Entity`, and for GitHub also reads the latest matching `Observation.normalized_payload`, then have `radar.jobs.daily_digest.run_daily_digest_job()` serialize GitHub-only repository metadata from that helper into the emitted digest payload.

**Tech Stack:** Python, SQLAlchemy ORM, pytest

---

### Task 1: Add a repository helper for digest-ready items

**Files:**
- Modify: `radar/core/repositories.py`
- Test: `tests/core/test_repositories.py`

- [ ] **Step 1: Write the failing repository test**

```python
def test_get_digest_candidate_items_includes_github_repo_metadata(tmp_path: Path) -> None:
    engine, session_factory = create_engine_and_session_factory(tmp_path / "radar.db")
    init_db(engine)
    repo = RadarRepository(session_factory)

    entity = repo.upsert_entity(
        source="github",
        entity_type="repo",
        canonical_name="github:vllm-project/vllm",
        display_name="vllm-project/vllm",
        url="https://github.com/vllm-project/vllm",
    )
    repo.record_observation(
        entity_id=entity.id,
        source="github",
        raw_payload={"description": "A high-throughput and memory-efficient inference and serving engine for LLMs"},
        normalized_payload={"description": "A high-throughput and memory-efficient inference and serving engine for LLMs"},
        dedupe_key="obs:github:vllm",
        content_hash="obs:github:vllm",
    )
    alert = repo.create_alert(
        alert_type="github_burst",
        entity_id=entity.id,
        source="github",
        score=0.91,
        dedupe_key="digest:github:vllm",
        reason={"full_name": "vllm-project/vllm", "stars": 77644, "forks": 15924},
    )

    items = repo.get_digest_candidate_items()

    assert items == [
        {
            "alert_id": alert.id,
            "alert_type": "github_burst",
            "source": "github",
            "score": 0.91,
            "repo_name": "vllm-project/vllm",
            "repo_url": "https://github.com/vllm-project/vllm",
            "repo_description": "A high-throughput and memory-efficient inference and serving engine for LLMs",
        }
    ]
```

- [ ] **Step 2: Run the repository test to verify RED**

Run: `pytest -q tests/core/test_repositories.py -k digest_candidate_items`

Expected: FAIL with `AttributeError` because `RadarRepository` does not yet expose `get_digest_candidate_items()`.

- [ ] **Step 3: Write the minimal repository implementation**

```python
def get_digest_candidate_items(self, *, limit: int = 50, window_hours: int = 24) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    with self._session_factory() as session:
        rows = session.execute(
            select(Alert, Entity, Observation)
            .join(Entity, Entity.id == Alert.entity_id)
            .outerjoin(
                Observation,
                (Observation.entity_id == Alert.entity_id) & (Observation.source == Alert.source),
            )
            .where(Alert.created_at >= cutoff)
            .order_by(Alert.score.desc())
            .limit(limit)
        )
        items: list[dict] = []
        for alert, entity, observation in rows:
            item = {
                "alert_id": alert.id,
                "alert_type": alert.alert_type,
                "source": alert.source,
                "score": alert.score,
            }
            if alert.source == "github":
                item["repo_name"] = entity.display_name
                item["repo_url"] = entity.url
                normalized_payload = observation.normalized_payload if observation is not None else {}
                description = normalized_payload.get("description") if isinstance(normalized_payload, dict) else None
                if description:
                    item["repo_description"] = description
            items.append(item)
        return items
```

- [ ] **Step 4: Run the repository test to verify GREEN**

Run: `pytest -q tests/core/test_repositories.py -k digest_candidate_items`

Expected: PASS.

- [ ] **Step 5: Commit the repository helper**

```bash
git add tests/core/test_repositories.py radar/core/repositories.py
git commit -m "feat: add digest candidate repository metadata"
```

### Task 2: Make the daily digest job emit enriched GitHub items

**Files:**
- Modify: `radar/jobs/daily_digest.py`
- Test: `tests/jobs/test_daily_digest.py`

- [ ] **Step 1: Write the failing digest job tests**

```python
def test_payload_items_include_github_repo_metadata(repo) -> None:
    entity = repo.upsert_entity(
        source="github",
        entity_type="repository",
        canonical_name="github:vllm-project/vllm",
        display_name="vllm-project/vllm",
        url="https://github.com/vllm-project/vllm",
    )
    repo.create_alert(
        alert_type="github_burst",
        entity_id=entity.id,
        source="github",
        score=0.8,
        dedupe_key="digest:github:repo-metadata",
        reason={"full_name": "vllm-project/vllm", "stars": 77644, "forks": 15924},
    )

    dispatched = []
    run_daily_digest_job(repo, dispatch=dispatched.append)

    assert dispatched[0]["items"][0]["repo_name"] == "vllm-project/vllm"
    assert dispatched[0]["items"][0]["repo_url"] == "https://github.com/vllm-project/vllm"
    assert dispatched[0]["items"][0]["repo_description"] == "A high-throughput and memory-efficient inference and serving engine for LLMs"


def test_payload_items_leave_non_github_sources_unenriched(repo) -> None:
    entity = repo.upsert_entity(
        source="official_pages",
        entity_type="page",
        canonical_name="official:deepseek",
        display_name="DeepSeek News",
        url="https://api-docs.deepseek.com/",
    )
    repo.create_alert(
        alert_type="official_release",
        entity_id=entity.id,
        source="official_pages",
        score=0.7,
        dedupe_key="digest:official:page",
        reason={"description": "DeepSeek release note"},
    )

    dispatched = []
    run_daily_digest_job(repo, dispatch=dispatched.append)

    item = dispatched[0]["items"][0]
    assert "repo_name" not in item
    assert "repo_url" not in item
    assert "repo_description" not in item
```

- [ ] **Step 2: Run the digest job tests to verify RED**

Run: `pytest -q tests/jobs/test_daily_digest.py -k "repo_metadata or unenriched"`

Expected: FAIL because `run_daily_digest_job()` still serializes only the four core fields.

- [ ] **Step 3: Write the minimal digest job implementation**

```python
def run_daily_digest_job(
    repository: Any,
    dispatch: Callable[[dict], None],
) -> int:
    candidates = repository.get_digest_candidate_items()
    if not candidates:
        return 0

    payload = {
        "type": "daily_digest",
        "count": len(candidates),
        "items": candidates,
    }
    dispatch(payload)
    return 1
```

- [ ] **Step 4: Run the digest job tests to verify GREEN**

Run: `pytest -q tests/jobs/test_daily_digest.py`

Expected: PASS.

- [ ] **Step 5: Commit the digest job enrichment**

```bash
git add tests/jobs/test_daily_digest.py radar/jobs/daily_digest.py
git commit -m "feat: enrich github daily digest items"
```

### Task 3: Lock webhook payload expectations and run regressions

**Files:**
- Modify: `tests/test_app.py`
- Verify: `radar/app.py`

- [ ] **Step 1: Write the failing webhook payload expectation**

```python
def test_build_daily_digest_webhook_payloads_preserves_github_repo_metadata() -> None:
    payload = {
        "type": "daily_digest",
        "count": 1,
        "items": [
            {
                "alert_id": 101,
                "alert_type": "github_burst",
                "source": "github",
                "score": 0.91,
                "repo_name": "vllm-project/vllm",
                "repo_url": "https://github.com/vllm-project/vllm",
                "repo_description": "A high-throughput and memory-efficient inference and serving engine for LLMs",
            }
        ],
    }

    assert _build_daily_digest_webhook_payloads(payload) == [
        {
            "event_type": "daily_digest_item",
            "digest_type": "daily_digest",
            "digest_count": 1,
            "item_index": 1,
            "alert_id": 101,
            "alert_type": "github_burst",
            "source": "github",
            "score": 0.91,
            "repo_name": "vllm-project/vllm",
            "repo_url": "https://github.com/vllm-project/vllm",
            "repo_description": "A high-throughput and memory-efficient inference and serving engine for LLMs",
        }
    ]
```

- [ ] **Step 2: Run the app test to verify RED**

Run: `pytest -q tests/test_app.py -k github_repo_metadata`

Expected: FAIL until the assertion is added; this proves the regression test exists.

- [ ] **Step 3: Keep production code unchanged if tests already pass after adding the assertion**

`radar.app._build_daily_digest_webhook_payloads()` already splats item fields before applying reserved digest metadata, so no production change is expected here. Only change production code if the new test reveals a real gap.

- [ ] **Step 4: Run the focused regression suite**

Run: `pytest -q tests/test_app.py tests/jobs/test_daily_digest.py tests/core/test_repositories.py`

Expected: PASS.

- [ ] **Step 5: Run the broader repository suite**

Run: `python3 -m pytest -q`

Expected: PASS.

- [ ] **Step 6: Commit the regression coverage**

```bash
git add tests/test_app.py tests/jobs/test_daily_digest.py tests/core/test_repositories.py radar/core/repositories.py radar/jobs/daily_digest.py
git commit -m "test: cover github digest webhook enrichment"
```
