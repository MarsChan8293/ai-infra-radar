# AI Infra Radar Hugging Face Models Design

## 1. Goal

Add the next source adapter after MVP-1 by integrating **Hugging Face Models** into the existing single-process radar service.

The first Hugging Face slice must let a user:

- configure one or more **organizations** to watch (for example `deepseek`)
- detect **new models**
- detect **metadata-based model updates**
- emit alerts through the existing alert / dispatcher / digest pipeline

This slice extends the current MVP architecture; it does not replace it.

## 2. Scope

### In scope

- new `huggingface` source configuration under `sources`
- polling Hugging Face model listings by **organization**
- normalization of Hugging Face model records into the shared observation shape
- persistence through the existing entity / observation / alert tables
- alert emission for:
  - new model discovered
  - existing model with changed metadata timestamp
- scheduler and manual trigger integration
- tests for client, pipeline, job, and smoke path

### Out of scope

- Hugging Face datasets
- Hugging Face spaces
- keyword search as the primary discovery mode
- likes / downloads / trend scoring
- model card textual diffing
- cross-source resonance logic
- dashboard/UI work

## 3. Chosen Approach

Use **organization-based polling** as the first implementation.

For each configured Hugging Face organization:

1. fetch that organization's models from the Hugging Face API
2. normalize each model into the common observation structure
3. compare the normalized snapshot against stored state using the shared dedupe path
4. emit one alert for a newly seen model or a model whose metadata update timestamp changed

This is the recommended approach because it matches the user's requested monitoring model, keeps configuration simple, and fits naturally into the existing source-adapter pattern already used by GitHub and official pages.

## 4. Runtime Fit

Hugging Face becomes a third source adapter alongside:

- `github`
- `official_pages`
- `huggingface`

The source must remain a bounded module:

- `radar/sources/huggingface/client.py` handles API fetches only
- `radar/sources/huggingface/pipeline.py` handles normalization only
- `radar/jobs/huggingface_models.py` handles polling orchestration only
- `AlertService` gains one Hugging Face-specific processing entrypoint that still delegates into the shared `emit_alert(...)` path

No new runtime process, queue, or storage engine is introduced.

## 5. Configuration Design

Add a new settings block:

```yaml
sources:
  huggingface:
    enabled: true
    organizations:
      - deepseek
      - Qwen
```

### Validation rules

- `enabled=false` may allow an empty `organizations` list
- `enabled=true` requires at least one organization
- organization names are stored as plain strings

The first version does not add source-specific thresholds because this slice is event-based, not score-threshold-based.

## 6. Data Model Mapping

The design intentionally reuses the existing tables.

### 6.1 Entity

Each Hugging Face model becomes one `entity`.

Suggested mapping:

- `source = "huggingface"`
- `entity_type = "model"`
- `canonical_name = "huggingface:<org>/<model>"`
- `display_name = "<org>/<model>"`
- `url = "https://huggingface.co/<org>/<model>"`

### 6.2 Observation

Each poll result becomes one normalized observation candidate.

Minimum normalized fields:

- `model_id`
- `organization`
- `last_modified`
- `private`
- `gated`
- `downloads` if available from the API response, but not used for first-version alert decisions

### 6.3 Alert types

Two alert types are introduced:

- `huggingface_model_new`
- `huggingface_model_updated`

## 7. Detection and Dedupe Rules

### 7.1 New model

If a Hugging Face model is not yet known in persistence, create:

- entity
- observation
- `huggingface_model_new` alert

Suggested dedupe key:

- `hf:new:<org>/<model>`

### 7.2 Updated model

If the model already exists and the Hugging Face metadata timestamp changed, create:

- observation
- `huggingface_model_updated` alert

Suggested dedupe key:

- `hf:update:<org>/<model>:<last_modified>`

### 7.3 No-op case

If the same model is seen again with the same metadata timestamp, no alert is emitted.

## 8. Client and Job Design

### 8.1 Client

The client should fetch models for one organization at a time using the public Hugging Face API.

Client responsibilities:

- build the request
- apply timeout
- raise explicit errors on non-2xx
- return decoded JSON model items

The client should not:

- do alert logic
- do persistence
- do dedupe

### 8.2 Job

The job loops through configured organizations and processes returned items.

Behavior:

1. fetch items for one organization
2. normalize each item
3. hand off to alert service
4. continue organization-by-organization even if one organization fails

The job should return an integer count of alerts created, matching current source job contracts.

## 9. Error Handling

- network failure for one organization must not abort all remaining organizations
- API errors should be surfaced as explicit job failures/loggable errors, not silently swallowed
- retries may be lightweight and bounded; no infinite retry loops
- invalid configuration must fail during settings validation, not at job runtime

## 10. Testing Strategy

The first implementation must include:

1. **client tests**
   - success path
   - non-2xx failure
   - timeout / transient failure behavior
2. **pipeline tests**
   - canonical name mapping
   - URL mapping
   - dedupe-relevant content hash or timestamp mapping
3. **job tests**
   - new model emits alert
   - changed `last_modified` emits update alert
   - unchanged model emits no alert
4. **smoke coverage**
   - Hugging Face path joins the current MVP smoke suite cleanly

## 11. Success Criteria

This design is successful when:

- a user can configure one or more Hugging Face organizations
- a newly published model under that organization produces one alert
- a later metadata timestamp change for that model produces one update alert
- repeated polls of the same unchanged metadata snapshot do not emit duplicate alerts
- the new source fits the existing runtime, scheduler, API, and digest flow without architectural special cases
