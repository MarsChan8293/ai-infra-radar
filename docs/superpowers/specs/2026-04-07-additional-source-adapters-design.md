# AI Infra Radar Additional Source Adapters Design

## 1. Goal

Add the next three source adapters after Hugging Face:

- **ModelScope models**
- **Modelers models**
- **GitCode repositories**

This slice must let a user configure one or more organizations for each source, detect newly seen items, detect later metadata-timestamp updates, and emit alerts through the existing alert, dispatcher, digest, scheduler, and CLI flows.

## 2. Scope

### In scope

- new `modelscope`, `modelers`, and `gitcode` source blocks under `sources`
- one client module per source
- one normalization pipeline per source
- one polling job per source
- one `AlertService` processing entrypoint per source
- runtime wiring, manual job trigger support, and CLI backfill aliases
- tests for config, client, pipeline, job/runtime integration, and smoke paths

### Out of scope

- datasets, spaces, comments, likes, or discussion activity
- search-based discovery as the primary monitoring mode
- auth flows beyond static token configuration
- per-source scoring heuristics beyond event-style new/update alerts
- UI work for the new sources

## 3. Decomposition

This work contains three independent source slices that share the same architecture:

1. **ModelScope models** — public model listings for an organization
2. **Modelers models** — public model listings for an organization
3. **GitCode repositories** — organization repository listings via authenticated API

They should be implemented as three end-to-end adapter slices, not as a single large generic abstraction. The shared behavior already exists in the repository, observation, alert, scheduler, and dispatcher layers.

## 4. Chosen Approach

Use the existing source-adapter pattern already established by:

- `github`
- `official_pages`
- `huggingface`

For each new source:

1. fetch items for one configured organization
2. normalize each item into the shared observation shape
3. persist via the existing entity/observation tables
4. emit one alert for a newly seen item or a later metadata timestamp change

This keeps each source bounded and readable while avoiding a premature cross-source abstraction.

## 5. Source-Specific Design

### 5.1 ModelScope

**Discovery model:** organization-based polling

**Endpoint choice:** use the same public REST path used by the open-source ModelScope SDK:

- `PUT https://www.modelscope.cn/api/v1/models/`
- JSON body: `{"Path": "<organization>", "PageNumber": 1, "PageSize": N}`

This endpoint is publicly readable and returns model metadata including:

- `Name`
- `Path`
- `Id`
- `CreatedTime`
- `LastUpdatedTime`
- `Downloads`

**Detection rule:**

- new model → emit `modelscope_model_new`
- existing model with changed `LastUpdatedTime` → emit `modelscope_model_updated`

### 5.2 Modelers

**Discovery model:** organization-based polling

**Endpoint choice:** use the public JSON endpoint observed on the site:

- `GET https://modelers.cn/server/model?page_num=1&count_per_page=N&count=true&owner=<organization>`

This endpoint returns model metadata including:

- `id`
- `owner`
- `name`
- `created_at`
- `updated_at`
- `download_count`
- `visibility`

**Detection rule:**

- new model → emit `modelers_model_new`
- existing model with changed `updated_at` → emit `modelers_model_updated`

### 5.3 GitCode

**Discovery model:** organization-based polling

**Endpoint choice:** use the documented GitCode API v5 organization repository listing endpoint:

- `GET https://api.gitcode.com/api/v5/orgs/{org}/repos`

GitCode requires a token with organization-read scope for this endpoint. The client should send the configured token using the standard API auth style (`Authorization: Bearer ...` is acceptable).

Expected repository fields include:

- `full_name`
- `name`
- `html_url`
- `updated_at`

**Detection rule:**

- new repository → emit `gitcode_repository_new`
- existing repository with changed `updated_at` → emit `gitcode_repository_updated`

## 6. Configuration Design

Add three new source settings blocks:

```yaml
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
    token: ${GITCODE_TOKEN}
    organizations:
      - gitcode
```

### Validation rules

- `enabled=false` may allow an empty `organizations` list
- `enabled=true` requires at least one organization
- `gitcode.enabled=true` additionally requires a non-empty token

## 7. Data Model Mapping

Reuse the existing tables for all three sources.

### 7.1 ModelScope entities

- `source = "modelscope"`
- `entity_type = "model"`
- `canonical_name = "modelscope:<org>/<name>"`
- `display_name = "<org>/<name>"`
- `url = "https://www.modelscope.cn/models/<org>/<name>"`

Normalized payload fields:

- `model_id`
- `organization`
- `modelscope_id`
- `created_time`
- `last_updated_time`
- `downloads`

### 7.2 Modelers entities

- `source = "modelers"`
- `entity_type = "model"`
- `canonical_name = "modelers:<org>/<name>"`
- `display_name = "<org>/<name>"`
- `url = "https://modelers.cn/models/<org>/<name>"`

Normalized payload fields:

- `model_id`
- `organization`
- `created_at`
- `updated_at`
- `download_count`
- `visibility`

### 7.3 GitCode entities

- `source = "gitcode"`
- `entity_type = "repository"`
- `canonical_name = "gitcode:<org>/<repo>"`
- `display_name = "<org>/<repo>"`
- `url = "<html_url from API>"`

Normalized payload fields:

- `full_name`
- `organization`
- `repo_name`
- `updated_at`

## 8. Dedupe Rules

Each source follows the same event model:

- if entity does not exist yet → create entity, record observation, emit `*_new`
- if entity exists and timestamp changed → record observation, emit `*_updated`
- if timestamp is unchanged → no alert

Suggested alert dedupe key shape:

- ModelScope: `modelscope:<alert_type>:<org>/<name>:<last_updated_time>`
- Modelers: `modelers:<alert_type>:<org>/<name>:<updated_at>`
- GitCode: `gitcode:<alert_type>:<org>/<repo>:<updated_at>`

## 9. Runtime Fit

Each source remains a bounded module:

- `radar/sources/<source>/client.py` — fetch only
- `radar/sources/<source>/pipeline.py` — normalize only
- `radar/jobs/<source_job>.py` — orchestration only
- `AlertService` — source-specific persist/emit entrypoint

`radar/app.py` will:

- instantiate the new clients
- register the jobs if their source is enabled
- continue organization-by-organization on per-org fetch failure
- raise a summarized error after processing remaining orgs, matching the Hugging Face resilience model

## 10. CLI and Scheduler Design

Add these job names:

- `modelscope_models`
- `modelers_models`
- `gitcode_repos`

Add `backfill-source` aliases:

- `modelscope -> modelscope_models`
- `modelers -> modelers_models`
- `gitcode -> gitcode_repos`

## 11. Error Handling

- per-organization network/API failures must not abort remaining organizations for that source
- summarized failures must be raised after remaining organizations are processed
- client non-2xx responses must raise explicit errors
- invalid config must fail during settings validation
- no silent fallback to empty results

## 12. Testing Strategy

For each source, add:

1. **client tests**
   - success path
   - non-2xx failure
   - timeout/transient propagation where applicable
2. **pipeline tests**
   - canonical name mapping
   - URL mapping
   - timestamp/content-hash mapping
3. **job + alert-service tests**
   - new item emits alert
   - updated timestamp emits alert
   - unchanged timestamp emits no alert
4. **config/runtime tests**
   - source validation rules
   - runtime job registration
   - per-org failure continuation
5. **smoke coverage**
   - the new sources appear in the MVP smoke path cleanly

## 13. Success Criteria

This design is successful when:

- a user can configure organizations for ModelScope, Modelers, and GitCode
- a newly published model/repository under a configured organization emits one alert
- a later timestamp update emits one update alert
- repeated unchanged polls do not emit duplicate alerts
- GitCode auth requirements are explicit in config and docs
- all three sources fit the existing runtime without architectural special cases
