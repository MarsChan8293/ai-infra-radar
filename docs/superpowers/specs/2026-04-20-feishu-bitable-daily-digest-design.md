# Feishu Bitable Daily Digest Design

## Goal

Reuse the existing YAML `channels.webhook` configuration to push `daily_digest`
data into a Feishu Base automation webhook, with one webhook event per digest
item so the automation can map each event into one Bitable row.

## Scope

This design only covers Feishu delivery for `daily_digest`.

It does not change the behavior of:

- normal per-alert webhook delivery
- email delivery
- the generic webhook sender used outside the digest flow

## Decisions

1. Keep the existing `channels.webhook` YAML structure.
2. Configure the Feishu automation URL in `config/radar.yaml`.
3. Only adapt the `daily_digest` dispatch path for Feishu.
4. Split one digest payload into multiple webhook posts, one per `item`.
5. Keep delivery semantics best-effort: one failed item must not block the rest.

## Configuration

The existing webhook configuration remains the single source of truth:

```yaml
channels:
  webhook:
    enabled: true
    url: https://pcnfy7i3x66l.feishu.cn/base/automation/webhook/event/WQoaaghK2wMQ33humAqcfrPnnBb
```

No new `feishu` or `bitable` config block is introduced.

## Architecture

### Digest generation

`radar.jobs.daily_digest.run_daily_digest_job()` continues to generate the
generic digest payload:

```python
{
    "type": "daily_digest",
    "count": <int>,
    "items": [...],
}
```

The digest job remains transport-agnostic and does not learn Feishu-specific
behavior.

### Digest dispatch adaptation

`radar.app.build_runtime()` already wires a dedicated `_dispatch_daily_digest()`
callback. That callback becomes the only place where digest payloads are adapted
for Feishu webhook delivery.

Behavior:

1. Keep the current channel assembly from `_build_channels(settings)`.
2. When dispatching a `daily_digest` payload to the webhook channel, iterate
   over `payload["items"]`.
3. Build one webhook event per item.
4. Send each event independently through the existing webhook sender path.
5. Leave non-webhook channels unchanged.

This keeps the Feishu-specific behavior isolated to the digest flow and avoids
changing the semantics of normal alert dispatch.

## Feishu event shape

Each digest item becomes one webhook JSON payload with the following fields:

```json
{
  "event_type": "daily_digest_item",
  "digest_type": "daily_digest",
  "digest_count": 3,
  "item_index": 1,
  "alert_id": 42,
  "alert_type": "github_burst",
  "source": "github",
  "score": 0.91
}
```

Recommended optional passthrough fields:

- `title`
- `url`
- `entity_name`

These optional fields should only be included if they are already available from
the digest payload without widening repository or model responsibilities for this
feature. The minimum viable implementation only requires the core system fields
above.

## Failure semantics

Delivery stays best-effort:

- if one digest item webhook fails, remaining items are still attempted
- webhook failures are recorded as failed delivery logs
- successful items are still recorded as sent
- email delivery, when enabled, continues to use the current raw digest path

This prevents a single bad item or transient webhook failure from dropping the
entire daily digest.

## File changes

### `config/radar.yaml`

- enable the existing webhook channel
- set the Feishu automation webhook URL

### `radar/app.py`

- adapt `_dispatch_daily_digest()` to split digest items into multiple webhook
  deliveries
- preserve the existing raw dispatch path for non-webhook channels

### `radar/cli.py`

- update `send-test-notification webhook` to send a Feishu-compatible sample
  digest-item event instead of the current plain text payload

### `README.md`

- document the Feishu webhook configuration
- document that daily digests are sent as one webhook event per digest item
- update the manual webhook test example accordingly

### Tests

- `tests/jobs/test_daily_digest.py`
- `tests/alerts/test_dispatcher.py`
- any runtime/config regression tests touched by the digest dispatch wiring

## Testing strategy

The implementation should verify:

1. A digest with `n` items results in `n` webhook calls.
2. Normal alert webhook delivery remains single-request and unchanged.
3. A failed digest item webhook does not stop later items from sending.
4. Delivery logs still record sent and failed outcomes correctly.
5. The CLI webhook test command emits a payload shape that Feishu automation can
   consume.

## Out of scope

- introducing a new dedicated Feishu channel type
- changing non-digest alert payload formats
- redesigning repository queries only to enrich Feishu rows
- adding field-mapping configuration for arbitrary Bitable schemas
