# Disable Automatic Pages Deploy Design

## Goal

Stop automatic GitHub Pages deployment for the radar site while keeping
`Deploy Radar Pages` available for manual `workflow_dispatch` runs.

## Scope

This design only changes the Pages deployment workflow contract.

It does not change:

- site export generation
- data collection jobs
- manual Pages publishing
- any non-Pages workflow

## Decisions

1. Remove the `schedule` trigger from `.github/workflows/deploy-pages.yml`.
2. Keep `workflow_dispatch` so Pages can still be published on demand.
3. Update tests so they assert manual publishing support without requiring
   automatic scheduling.
4. Update any directly conflicting documentation so it no longer claims Pages
   publishes automatically.

## Architecture

`Deploy Radar Pages` currently supports both manual and scheduled execution:

```yaml
on:
  workflow_dispatch:
  schedule:
    - cron: "0 * * * *"
```

The workflow contract becomes manual-only:

```yaml
on:
  workflow_dispatch:
```

No job steps change. Build, export, archive commit, artifact upload, and Pages
deployment remain exactly as they are today when the workflow is triggered
manually.

## File Changes

### `.github/workflows/deploy-pages.yml`

- remove the `schedule` trigger
- keep `workflow_dispatch`

### `tests/pages/test_export.py`

- rename or rewrite the workflow expectation so it no longer requires
  `schedule:`
- keep assertions that the workflow exists and still supports manual publish

### Related docs

- update only text that explicitly claims the Pages workflow auto-publishes on a
  schedule

## Testing Strategy

Run the existing Pages-related regression coverage after the change:

```bash
python3 -m pytest tests/pages/test_export.py -q
```

If any documentation-linked workflow expectations fail elsewhere, update those
expectations and rerun the affected existing tests.
