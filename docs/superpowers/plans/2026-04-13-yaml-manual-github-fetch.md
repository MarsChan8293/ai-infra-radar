# YAML Manual GitHub Fetch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `/ops` manual GitHub fetch form with a YAML editor that accepts a `sources.github`-style fragment while preserving the current coarse / second-pass / errors analysis view.

**Architecture:** Parse a pasted YAML fragment on the backend into a temporary GitHub config object, reuse the existing GitHub config models plus the current README collection / README AI filter pipeline, and keep runtime credentials in app state. On the frontend, replace the split form with one YAML textarea seeded from a config-shaped template and keep the current result rendering contract.

**Tech Stack:** FastAPI, Pydantic, PyYAML, vanilla JS, pytest

---

## File Map

- **Modify:** `radar/api/routes/ops_github.py`
  - Replace the current request model with a YAML-based payload
  - Parse and validate a `sources.github` fragment
  - Execute multiple queries with existing README and AI-filter helpers
  - Preserve coarse / second-pass / errors response sections
- **Modify:** `radar/ui/index.html`
  - Replace the current date/query/prompt controls with one YAML textarea
- **Modify:** `radar/ui/app.js`
  - Seed the YAML editor
  - Submit `{ github_config_yaml }`
  - Keep disabled-state, stale-result clearing, and result rendering
- **Modify:** `radar/ui/styles.css`
  - Style the YAML textarea and simplified form layout
- **Modify:** `tests/api/test_ops_github.py`
  - Cover YAML request parsing, invalid YAML, multiple queries, and pasted filter config behavior
- **Modify:** `tests/api/test_ui.py`
  - Cover the YAML editor shell and JS request body changes
- **Modify:** `README.md`
  - Document the new YAML-based `/ops` manual fetch interaction

### Task 1: Replace the backend request with YAML parsing

**Files:**
- Modify: `tests/api/test_ops_github.py`
- Modify: `radar/api/routes/ops_github.py`
- Reference: `radar/core/config.py`

- [ ] **Step 1: Write the failing YAML request tests**

```python
def test_manual_fetch_accepts_github_config_yaml_fragment() -> None:
    client = _make_client(
        github_client=_FakeGitHubClient([], readmes={}),
        github_readme_ai_filter=_FakeReadmeAIFilter({}),
    )

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
                  default_prompt: test prompt
                """
            ).strip()
        },
    )

    assert response.status_code == 200


def test_manual_fetch_rejects_invalid_yaml_fragment() -> None:
    client = _make_client(
        github_client=_ExplodingGitHubClient(),
        github_readme_ai_filter=_FakeReadmeAIFilter({}),
    )

    response = client.post(
        "/ops/github/manual-fetch",
        json={"github_config_yaml": "queries:\n  - ok\n    - broken"},
    )

    assert response.status_code == 422
    assert "github_config_yaml" in response.text
```

- [ ] **Step 2: Run the backend request tests to verify they fail**

Run: `pytest tests/api/test_ops_github.py -k 'github_config_yaml or invalid_yaml_fragment' -q`

Expected: FAIL because the route still expects `start_date`, `end_date`, `query`, and `readme_prompt`.

- [ ] **Step 3: Implement the YAML request model and parser**

```python
class ManualGitHubFetchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    github_config_yaml: str

    @field_validator("github_config_yaml")
    @classmethod
    def _require_non_blank_yaml(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


def _load_manual_github_settings(yaml_text: str) -> GitHubSettings:
    try:
        payload = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid github_config_yaml: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="github_config_yaml must decode to a mapping.")
    try:
        return GitHubSettings.model_validate(
            {
                "enabled": True,
                "token": None,
                **payload,
            }
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
```

- [ ] **Step 4: Run the backend request tests to verify they pass**

Run: `pytest tests/api/test_ops_github.py -k 'github_config_yaml or invalid_yaml_fragment' -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/api/test_ops_github.py radar/api/routes/ops_github.py
git commit -m "feat: parse yaml manual github config"
```

### Task 2: Execute multiple queries and pasted filter settings

**Files:**
- Modify: `tests/api/test_ops_github.py`
- Modify: `radar/api/routes/ops_github.py`
- Reference: `radar/sources/github/manual_fetch.py`
- Reference: `radar/sources/github/readme_ai_filter.py`

- [ ] **Step 1: Write the failing multi-query/filter test**

```python
def test_manual_fetch_runs_multiple_queries_and_keyword_filter_before_ai() -> None:
    github_client = _FakeGitHubClient(
        items_by_query={
            '"speculative decoding" created:>2026-04-12': [spec_repo, notes_repo],
            '"kv cache" inference created:>2026-04-12': [kv_repo],
        },
        readmes={
            "acme/spec-repo": "# Citation\n\n@inproceedings{spec}",
            "acme/notes": "# Notes only",
            "acme/kv-cache": "# BibTeX\n\n@article{kv}",
        },
    )
    ai_filter = _FakeReadmeAIFilter(
        {
            "acme/spec-repo": {"keep": True, "reason_zh": "命中。", "matched_signals": ["speculative decoding"]},
            "acme/kv-cache": {"keep": False, "reason_zh": "不够直接。", "matched_signals": []},
        }
    )
    client = _make_client(github_client=github_client, github_readme_ai_filter=ai_filter)

    response = client.post("/ops/github/manual-fetch", json={"github_config_yaml": YAML_FRAGMENT})

    body = response.json()
    assert github_client.queries == [
        '"speculative decoding" created:>2026-04-12',
        '"kv cache" inference created:>2026-04-12',
    ]
    assert [item["full_name"] for item in body["coarse_results"]] == [
        "acme/spec-repo",
        "acme/notes",
        "acme/kv-cache",
    ]
    assert [item["full_name"] for item in body["secondary_results"]] == ["acme/spec-repo"]
    assert [call["full_name"] for call in ai_filter.calls] == ["acme/spec-repo", "acme/kv-cache"]
```

- [ ] **Step 2: Run the multi-query/filter test to verify it fails**

Run: `pytest tests/api/test_ops_github.py -k 'multiple_queries_and_keyword_filter_before_ai' -q`

Expected: FAIL because the route still executes only one query and does not read pasted `readme_filter` / `ai_readme_filter` settings.

- [ ] **Step 3: Implement multi-query execution with pasted filters**

```python
search_items: list[dict[str, Any]] = []
for query in github_settings.queries:
    expanded_query = expand_query_date_placeholders(query)
    search_items.extend(github_client.search_repositories(expanded_query))

candidates = collect_readme_candidates(
    search_items,
    fetch_readme_text=github_client.fetch_readme_text,
)

filtered_candidates = candidates
if github_settings.readme_filter.enabled:
    filtered_candidates = [
        candidate
        for candidate in candidates
        if candidate["readme_status"] == "ok"
        and readme_matches_keywords(
            candidate.get("readme_text"),
            github_settings.readme_filter.require_any,
        )
    ]

secondary_results = []
for candidate in filtered_candidates:
    ...
```

- [ ] **Step 4: Add and pass a failure-path test for malformed YAML filter settings**

```python
def test_manual_fetch_rejects_yaml_without_queries() -> None:
    response = client.post(
        "/ops/github/manual-fetch",
        json={"github_config_yaml": "burst_threshold: 0.01"},
    )
    assert response.status_code == 422
    assert "queries" in response.text
```

Run: `pytest tests/api/test_ops_github.py -k 'multiple_queries_and_keyword_filter_before_ai or yaml_without_queries' -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/api/test_ops_github.py radar/api/routes/ops_github.py
git commit -m "feat: run yaml manual github queries"
```

### Task 3: Replace the `/ops` form with a YAML editor

**Files:**
- Modify: `tests/api/test_ui.py`
- Modify: `radar/ui/index.html`
- Modify: `radar/ui/app.js`
- Modify: `radar/ui/styles.css`

- [ ] **Step 1: Write the failing UI shell and JS tests**

```python
def test_ops_shell_contains_yaml_manual_fetch_editor() -> None:
    client = TestClient(create_app())
    response = client.get("/ops")

    assert 'id="manual-fetch-config-yaml"' in response.text
    assert 'id="manual-fetch-start-date"' not in response.text
    assert 'id="manual-fetch-query"' not in response.text


def test_ops_script_posts_yaml_manual_fetch_payload() -> None:
    result = _run_ops_app_scenario(
        manual_response={...},
        extra_steps=textwrap.dedent(
            """
            document.getElementById("manual-fetch-config-yaml").value = "queries:\\n  - test";
            document.getElementById("manual-fetch-form").dispatchEvent({ type: "submit" });
            """
        ),
    )

    assert json.loads(result["lastManualRequest"]["body"]) == {
        "github_config_yaml": "queries:\\n  - test"
    }
```

- [ ] **Step 2: Run the UI tests to verify they fail**

Run: `pytest tests/api/test_ui.py -k 'yaml_manual_fetch_editor or posts_yaml_manual_fetch_payload' -q`

Expected: FAIL because the HTML and JS still reference the old split fields.

- [ ] **Step 3: Implement the YAML editor and request body**

```html
<label class="field-group field-group-wide">
  <span>GitHub config YAML</span>
  <textarea
    id="manual-fetch-config-yaml"
    name="github_config_yaml"
    rows="16"
  ></textarea>
</label>
```

```javascript
const DEFAULT_MANUAL_FETCH_CONFIG = `queries:
  - '"speculative decoding" created:>@today-1d'
burst_threshold: 0.01
readme_filter:
  enabled: true
  require_any:
    - citation
ai_readme_filter:
  enabled: true
  model: nvidia/nemotron-3-super-120b-a12b
  default_prompt: |
    Read this repository README and decide whether it is directly relevant
    ...`;

body: JSON.stringify({
  github_config_yaml: document.getElementById("manual-fetch-config-yaml").value,
})
```

- [ ] **Step 4: Run the UI tests to verify they pass**

Run: `pytest tests/api/test_ui.py -k 'yaml_manual_fetch_editor or posts_yaml_manual_fetch_payload or stale_manual_fetch_results_after_failed_rerun' -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/api/test_ui.py radar/ui/index.html radar/ui/app.js radar/ui/styles.css
git commit -m "feat: switch ops manual fetch to yaml editor"
```

### Task 4: Update docs and run focused verification

**Files:**
- Modify: `README.md`
- Modify: `tests/api/test_ops_github.py`
- Modify: `tests/api/test_ui.py`

- [ ] **Step 1: Update the README wording for `/ops` manual fetch**

```md
- a manual GitHub fetch panel with a YAML editor for a `sources.github`-style
  config fragment, plus coarse results, second-pass results, and per-item errors
```

- [ ] **Step 2: Run focused regression tests**

Run: `pytest tests/api/test_ops_github.py tests/api/test_ui.py tests/api/test_config.py tests/sources/github/test_burst_pipeline.py -q`

Expected: PASS

- [ ] **Step 3: Run the full suite**

Run: `python3 -m pytest -q`

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add README.md tests/api/test_ops_github.py tests/api/test_ui.py
git commit -m "docs: describe yaml manual github fetch"
```
