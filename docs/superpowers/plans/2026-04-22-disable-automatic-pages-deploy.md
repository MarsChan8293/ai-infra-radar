# Disable Automatic Pages Deploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop automatic GitHub Pages deployment while keeping manual `workflow_dispatch` publishing available.

**Architecture:** Narrow the change to the workflow contract and the assertions that describe it. Remove the Pages workflow `schedule` trigger, keep all build/deploy steps unchanged for manual runs, and update documentation/tests so the repository consistently describes Pages as a manual publish flow.

**Tech Stack:** GitHub Actions YAML, Markdown documentation, Python `pytest`

---

## File Map

- Modify: `.github/workflows/deploy-pages.yml` — keep the workflow implementation, but remove the scheduled trigger.
- Modify: `tests/pages/test_export.py` — change the workflow regression to assert manual-only publishing.
- Modify: `README.md` — stop claiming the workflow publishes on a schedule and describe manual dispatch instead.

### Task 1: Lock the workflow contract to manual-only publish

**Files:**
- Modify: `tests/pages/test_export.py`
- Modify: `.github/workflows/deploy-pages.yml`
- Test: `tests/pages/test_export.py`

- [ ] **Step 1: Write the failing test**

Replace the workflow expectation with a manual-only assertion:

```python
def test_pages_workflow_exists_and_supports_manual_publish() -> None:
    workflow = Path(".github/workflows/deploy-pages.yml")

    assert workflow.exists()
    content = workflow.read_text()
    assert "workflow_dispatch:" in content
    assert "schedule:" not in content
    assert "concurrency:" in content
    assert "ref:" in content
    assert "actions/deploy-pages" in content
    assert "export-pages" in content
    assert "git push origin HEAD:" in content
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/pages/test_export.py::test_pages_workflow_exists_and_supports_manual_publish -q`

Expected: FAIL because `.github/workflows/deploy-pages.yml` still contains `schedule:`.

- [ ] **Step 3: Write the minimal implementation**

Remove the scheduled trigger and keep manual dispatch:

```yaml
on:
  workflow_dispatch:
```

The rest of `.github/workflows/deploy-pages.yml` stays unchanged.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/pages/test_export.py::test_pages_workflow_exists_and_supports_manual_publish -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/pages/test_export.py .github/workflows/deploy-pages.yml
git commit -m "chore: disable scheduled pages deploy" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Align the README with manual publish behavior

**Files:**
- Modify: `README.md`
- Modify: `tests/pages/test_export.py`
- Test: `tests/pages/test_export.py`

- [ ] **Step 1: Write the failing README assertion**

Add a new regression that locks the manual-only wording:

```python
def test_readme_describes_manual_pages_publish() -> None:
    readme = Path("README.md").read_text()

    assert "manual workflow dispatch" in readme
    assert "scheduled publishing" not in readme
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/pages/test_export.py::test_readme_describes_manual_pages_publish -q`

Expected: FAIL because `README.md` still says the workflow supports scheduled publishing.

- [ ] **Step 3: Write the minimal implementation**

Update the GitHub Pages section to manual-only wording:

```md
The repository workflow supports **manual workflow dispatch**. Configure a
`RADAR_CONFIG_YAML` repository secret so the workflow can build runtime
settings, collect current source data, preserve the existing static archive, and
deploy the refreshed site to GitHub Pages when triggered on demand.
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/pages/test_export.py::test_readme_describes_manual_pages_publish -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add README.md tests/pages/test_export.py
git commit -m "docs: describe manual pages publish" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Run the Pages regression sweep

**Files:**
- Test: `tests/pages/test_export.py`

- [ ] **Step 1: Run the focused Pages regression suite**

Run: `python3 -m pytest tests/pages/test_export.py -q`

Expected: PASS

- [ ] **Step 2: Run the full repository test suite**

Run: `python3 -m pytest -q`

Expected: PASS

- [ ] **Step 3: Commit the final verified state if Tasks 1 and 2 were not committed separately**

```bash
git add .github/workflows/deploy-pages.yml README.md tests/pages/test_export.py
git commit -m "chore: disable automatic pages deploy" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
