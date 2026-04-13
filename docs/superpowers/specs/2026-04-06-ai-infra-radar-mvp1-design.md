# AI Infra Radar MVP-1 Design

## 1. Goal

Build the first production-usable slice of AI Infra Radar as a **single-process service** that continuously monitors:

- GitHub
- Official Release Pages

and emits:

- Burst Alert
- Official Release Alert
- Daily Digest

through:

- Webhook
- Email

The MVP must be deployable as one service process with a CLI management entrypoint, use SQLite for persistence, YAML for configuration, and FastAPI for health/query/manual-trigger endpoints.

## 2. Scope

### In scope

- FastAPI application runtime
- APScheduler embedded in the same process
- CLI entrypoint for local/manual operations
- YAML config loading and schema validation
- SQLite persistence
- GitHub source adapter
- Official Release Pages source adapter
- Common normalization pipeline
- Feature/scoring pipeline sufficient for MVP alerts
- Alert building, dedupe, suppression, dispatch
- Webhook delivery
- Email delivery
- Alert history and health endpoints

### Out of scope

- Dashboard UI
- Hugging Face / ModelScope / Modelers / GitCode adapters
- CrossPlatformBonus
- Queue/worker split
- Multi-tenant SaaS capabilities
- PostgreSQL / ClickHouse

## 3. Chosen Architecture

The system will use a **modular monolith** architecture:

1. **FastAPI runtime** hosts the API surface and process lifecycle.
2. **APScheduler** runs polling and digest jobs inside the same process.
3. **CLI commands** reuse the same application services for local debugging, manual job triggers, and backfills.
4. **Source adapters** are isolated per source and only expose source-specific fetch/parse behavior.
5. **Common pipeline services** handle normalization, feature extraction, scoring, dedupe, suppression, and alert assembly.
6. **Dispatchers** send finalized alerts to webhook/email and record delivery attempts.

This keeps MVP delivery simple while preserving future split points between API, jobs, and workers.

## 4. Runtime Boundaries

### 4.1 Process model

- One long-running service process
- One SQLite database file
- In-process scheduler
- Stateless API layer over shared application services

### 4.2 Source boundaries

Only two source adapters are implemented in MVP-1:

- `github`
- `official_pages`

Both must publish into the same normalized observation format so later alerting and history logic remain source-agnostic.

### 4.3 Output boundaries

The domain decides whether to create an alert first. Delivery is handled separately.

- `alert`: domain object representing a candidate/issued alert
- `delivery_log`: operational record of webhook/email attempts

Retries must not mutate alert semantics.

## 5. Core Data Model

MVP-1 should stay intentionally small. The core records are:

### 5.1 `entity`

Canonical monitored object.

Examples:

- GitHub repo
- Official page
- Official release item

Suggested fields:

- `id`
- `source`
- `entity_type`
- `canonical_name`
- `display_name`
- `url`
- `owner`
- `metadata_json`
- `created_at`
- `updated_at`

### 5.2 `observation`

Normalized snapshot/event produced from a source fetch or webhook.

Suggested fields:

- `id`
- `entity_id`
- `source`
- `observed_at`
- `raw_payload_json`
- `normalized_payload_json`
- `dedupe_key`
- `content_hash`

### 5.3 `alert`

Represents a decided alert item.

Suggested fields:

- `id`
- `alert_type`
- `entity_id`
- `source`
- `score`
- `reason_json`
- `status`
- `created_at`

### 5.4 `delivery_log`

Represents delivery attempts and results.

Suggested fields:

- `id`
- `alert_id`
- `channel`
- `idempotency_key`
- `attempt`
- `status`
- `response_summary`
- `created_at`

### 5.5 `job_run`

Tracks scheduler/manual execution history.

Suggested fields:

- `id`
- `job_name`
- `started_at`
- `finished_at`
- `status`
- `error_summary`

## 6. Module Layout

The implementation should be organized around responsibility boundaries instead of technical layers only.

```text
radar/
  core/
    config/
    logging/
    scheduler/
    storage/
    models/

  sources/
    github/
    official_pages/

  pipeline/
    normalize/
    features/
    scoring/
    dedupe/
    suppress/

  alerts/
    builders/
    formatter/
    dispatcher/
    channels/

  api/
    routes/

  cli/

  jobs/
```

Design rule:

- source-specific code stays under `sources/`
- reusable business logic stays under `pipeline/` and `alerts/`
- FastAPI and CLI must call the same services instead of duplicating orchestration

## 7. MVP-1 Flows

### 7.1 Official Release Pages flow

1. Scheduler loads configured watched pages
2. Fetch page
3. Extract structured content using configured strategy
4. Compute hash/diff against prior observation
5. Create/update entity and observation
6. Decide whether change qualifies as official release signal
7. Build alert with explanation
8. Apply dedupe/suppression
9. Dispatch webhook/email
10. Record delivery logs

### 7.2 GitHub burst flow

1. Scheduler executes GitHub recall job
2. Fetch candidate repos / activity snapshots
3. Normalize repo/activity state into common observation shape
4. Compute burst-related features
5. Produce burst score
6. Build alert candidate if threshold is crossed
7. Apply dedupe/suppression
8. Dispatch webhook/email
9. Record delivery logs

### 7.3 Daily digest flow

1. Scheduled digest job queries alertable items in the digest window
2. Rank and group results
3. Render digest payload
4. Send via webhook/email
5. Record delivery logs

## 8. API and CLI

MVP-1 API surface should stay minimal:

- `GET /health`
- `GET /alerts`
- `GET /alerts/{id}`
- `POST /jobs/run/{job_name}`
- `POST /config/reload`

CLI commands should support:

- validate config
- run one job once
- backfill one source in a bounded window
- send a test notification

## 9. Development Order

The project should be built in this order:

### Phase 1: Foundation

- project skeleton
- config loader and validation
- SQLite storage layer
- common models
- logging and job-run recording
- FastAPI bootstrap
- APScheduler bootstrap
- CLI bootstrap

### Phase 2: Official Pages vertical slice

- fetcher
- extractor
- diff/hash detection
- normalization
- official-release scoring/decision
- alert dispatch

### Phase 3: GitHub vertical slice

- recall/query client
- repo/activity normalization
- burst features
- burst scoring
- alert dispatch reuse

### Phase 4: Operational surface

- alert history API
- manual trigger API/CLI
- config reload
- health endpoints
- smoke-path hardening

The rule is: each phase must leave the system in a runnable state.

## 10. Testing Strategy

### Unit tests

- YAML schema validation
- Official page extraction
- Official page diff/hash rules
- GitHub normalization
- GitHub burst scoring
- Dedupe and suppression rules
- Alert formatting

### Integration tests

- Fixture HTML page -> extracted release item -> alert
- Mocked GitHub responses -> normalized observation -> burst alert
- SQLite persistence for entity/observation/alert lifecycle

### Smoke tests

- Official page end-to-end alert path
- GitHub end-to-end burst path
- Daily digest rendering and send path

## 11. Key Risks and Mitigations

1. **Page structure drift**
   Keep extractor strategies configurable and source-specific.

2. **GitHub rate/shape variability**
   Isolate API client and normalize upstream differences before scoring.

3. **False-positive alerts**
   Keep dedupe, suppression, and explanation output in the MVP, not as a later add-on.

4. **Architecture overgrowth**
   Do not introduce queue/worker infrastructure before it is needed.

## 12. Acceptance for This Spec

This spec is considered satisfied when MVP-1 can:

- load YAML config
- run scheduled/manual jobs
- monitor GitHub and Official Pages
- persist normalized observations
- emit burst / official release / daily digest alerts
- deliver alerts via webhook/email
- expose health and alert history

