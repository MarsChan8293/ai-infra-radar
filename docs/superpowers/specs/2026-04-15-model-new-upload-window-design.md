# Model New Upload Window Design

## Problem

The current model ingestion flow for `huggingface`, `modelscope`, and `modelers`
treats the first-seen entity as `*_new` and later timestamp changes as
`*_updated`. That does not match the desired behavior. Model alerts should only
cover repositories/models that were newly uploaded on the source platform within
a configurable recent time window. Updated older models should not be ingested,
persisted, or alerted.

## Goal

Change model ingestion so that each model source only processes models whose
source-side creation timestamp falls within a YAML-configured recent window.

## Non-Goals

- Changing GitHub or official page ingestion
- Changing `gitcode` repository behavior
- Backfilling or deleting historical model alerts already stored in the database
- Adding UI for this setting

## Proposed Approach

Add a per-source YAML field named `new_upload_window_days` to:

- `sources.huggingface`
- `sources.modelscope`
- `sources.modelers`

Each field defaults to `1`.

At runtime, each model job will filter items by source creation timestamp before
passing them into `AlertService`. Only items created within the last
`new_upload_window_days` days continue into observation persistence and
`*_new` alert emission.

This changes the definition of "new" from "first time seen locally" to
"created recently on the upstream source."

## Configuration

Example shape:

```yaml
sources:
  huggingface:
    enabled: true
    organizations:
      - deepseek-ai
    new_upload_window_days: 1

  modelscope:
    enabled: true
    organizations:
      - deepseek-ai
    new_upload_window_days: 1

  modelers:
    enabled: false
    organizations:
      - Eco-Tech
    new_upload_window_days: 1
```

Validation requirements:

- Field type is integer
- Default is `1`
- Values must be greater than or equal to `1`

## Source-Specific Timestamp Rules

### Hugging Face

Use the source model creation timestamp, not `lastModified`.

The current pipeline only normalizes `lastModified`, so the implementation must
also carry the upstream creation timestamp into the normalized observation.
Filtering will use that creation timestamp. `lastModified` may remain available
as raw context, but it will no longer decide whether a model is eligible.

### ModelScope

Use the existing `CreatedTime` / normalized `created_time` field.

### Modelers

Use the existing `created_at` field.

## Filtering Behavior

For each source:

1. Fetch raw items from the client.
2. Normalize the source creation timestamp into the observation data.
3. Compute the cutoff as `now - timedelta(days=new_upload_window_days)`.
4. Skip any item whose creation timestamp is older than the cutoff.
5. Skip any item whose creation timestamp is missing or unparsable.
6. Only pass eligible items into `AlertService`.

## Persistence and Alerting Behavior

### Eligible items

- Observation is recorded
- `*_new` alert may be emitted

### Ineligible items

- No observation is recorded
- No `*_updated` alert is emitted
- No fallback alert type is emitted

This means model update alerts stop being produced for the three model sources.

## Why Filtering Happens Before AlertService

Filtering at the job boundary keeps the behavior aligned with the request:
"only ingest newly uploaded models." It also avoids persisting observations for
items that should never have been considered in scope.

This is preferred over filtering inside `AlertService`, where skipped items
would already have crossed part of the ingestion boundary.

## Error Handling

- Missing creation timestamp: skip item
- Unparsable creation timestamp: skip item
- Window configuration missing: use default `1`
- Window configuration invalid: config load fails during validation

There is no fallback to update timestamps, because that would blur the intended
meaning of "new upload" and reintroduce updated older models.

## Testing Plan

### Config tests

- Each of the three model source settings accepts `new_upload_window_days`
- Default value is `1`
- Invalid values such as `0` or negative numbers are rejected

### Pipeline/job tests

- Item created within the window is processed
- Item created outside the window is skipped
- Item with missing creation timestamp is skipped
- Item with invalid creation timestamp is skipped

### Behavior regression tests

- Existing `*_updated` model alert tests are replaced with assertions that
  updated existing models are skipped
- Existing `*_new` model alert tests continue to pass for in-window items
- Hugging Face gets coverage for creation timestamp normalization and filtering

## Compatibility Notes

- Existing stored `*_updated` alerts remain in the database until manually
  removed; the change only affects future ingestion.
- `gitcode` repository alerts keep their current new/update behavior.
- No API or UI contract changes are required beyond config shape changes.

## Recommended Implementation Boundaries

- `radar/core/config.py`: add per-source config field and validation
- `config/radar.yaml`: document/populate the new setting
- `radar/sources/huggingface/pipeline.py`: normalize upstream creation timestamp
- `radar/jobs/huggingface_models.py`: apply recent-upload filtering
- `radar/jobs/modelscope_models.py`: apply recent-upload filtering
- `radar/jobs/modelers_models.py`: apply recent-upload filtering
- `tests/core/test_config.py`: config coverage
- `tests/sources/huggingface/test_models_pipeline.py`: Hugging Face behavior
- `tests/sources/modelscope/test_models_pipeline.py`: ModelScope behavior
- `tests/sources/modelers/test_models_pipeline.py`: Modelers behavior

## Chosen Design

Implement per-source `new_upload_window_days` with a default of `1`, filter
each model source by upstream creation timestamp before `AlertService`, and stop
emitting model update alerts for `huggingface`, `modelscope`, and `modelers`.
