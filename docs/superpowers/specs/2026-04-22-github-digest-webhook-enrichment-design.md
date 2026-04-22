# GitHub Digest Webhook Enrichment Design

## Goal

Extend `daily_digest` webhook items so GitHub entries include `repo_name`,
`repo_url`, and `repo_description`, allowing Feishu automation to map a real
repository name, link, and description into table fields without custom manual
payloads.

## Scope

This design only changes `daily_digest` payload enrichment for `source ==
"github"`.

It does not change:

- non-GitHub digest items
- normal per-alert webhook delivery
- webhook transport/retry behavior
- external API dependencies during dispatch

## Decisions

1. Only GitHub digest items get the new repository fields.
2. Enrichment happens while building the digest payload, not inside the webhook
   sender.
3. Data comes from existing persisted `Entity` fields plus the latest GitHub
   `Observation.normalized_payload`.
4. Missing GitHub metadata stays best-effort: absent values do not fail digest
   delivery.
5. Existing digest webhook fan-out behavior stays unchanged.

## Architecture

### Digest payload enrichment

`radar.jobs.daily_digest.run_daily_digest_job()` currently emits digest items
with only:

```python
{
    "alert_id": ...,
    "alert_type": ...,
    "source": ...,
    "score": ...,
}
```

This becomes the enrichment point. For each candidate alert:

- keep the existing core fields
- if `alert.source == "github"`, load the related `Entity`
- copy `entity.display_name` into `repo_name`
- copy `entity.url` into `repo_url`
- copy the latest GitHub observation's
  `normalized_payload["description"]` into `repo_description` when present

The final digest payload remains transport-agnostic. `radar.app` keeps its
existing responsibility: split one digest into one webhook event per item.

### Data source

The repository layer already stores the required pieces:

- `Alert.entity_id`
- `Entity.display_name`
- `Entity.url`
- GitHub `Observation.normalized_payload["description"]`

Add a repository helper that returns digest candidates together with the related
entity data and the latest matching GitHub observation needed for digest
serialization. This avoids pushing SQL/session knowledge into the job layer and
keeps enrichment data local to digest construction.

## Payload shape

GitHub webhook items become:

```json
{
  "event_type": "daily_digest_item",
  "digest_type": "daily_digest",
  "digest_count": 1,
  "item_index": 1,
  "alert_id": 42,
  "alert_type": "github_burst",
  "source": "github",
  "score": 0.91,
  "repo_name": "vllm-project/vllm",
  "repo_url": "https://github.com/vllm-project/vllm",
  "repo_description": "A high-throughput and memory-efficient inference and serving engine for LLMs"
}
```

Non-GitHub items keep the existing shape and do not receive placeholder
repository fields.

## File changes

### `radar/core/repositories.py`

- add a digest-oriented read helper that joins `Alert` with `Entity`
- return enough data for digest serialization without requiring later lookups

### `radar/jobs/daily_digest.py`

- enrich GitHub digest items with repository metadata from the repository helper
- preserve the existing payload contract for non-GitHub items

### `tests/test_app.py`

- update webhook payload expectations so GitHub items include the new fields
- keep non-GitHub expectations unchanged

### `tests/jobs/test_daily_digest.py` or the existing digest job test location

- add job-level coverage for GitHub enrichment at payload construction time
- verify non-GitHub items remain unenriched

## Testing strategy

Implementation must verify:

1. GitHub digest items include `repo_name`, `repo_url`, and
   `repo_description`.
2. Non-GitHub digest items do not include those fields.
3. Existing digest webhook fan-out still sends one webhook event per item.
4. Existing raw digest delivery for non-webhook channels is unchanged.

## Out of scope

- enriching non-GitHub sources with source-specific metadata
- fetching repository descriptions from live GitHub APIs during digest dispatch
- changing Feishu-specific field mapping behavior
- redesigning generic alert payloads outside `daily_digest`
