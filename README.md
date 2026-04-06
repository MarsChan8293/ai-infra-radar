# ai-infra-radar

Track AI infrastructure releases, GitHub activity bursts, and deliver a daily digest via webhook or email.

## Bootstrap

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Configuration

Copy `tests/fixtures/minimal.yaml` as a starting point and fill in real values:

```yaml
app:
  timezone: UTC          # any tz string accepted by APScheduler

storage:
  path: ./data/radar.db  # SQLite file path

channels:
  webhook:
    enabled: true
    url: https://hooks.example.com/abc123
  email:
    enabled: false
    smtp_host: smtp.example.com
    smtp_port: 587
    username: radar@example.com
    password: secret
    from: radar@example.com
    to:
      - team@example.com

sources:
  github:
    enabled: true
    token: ghp_…          # GitHub personal access token
    queries:
      - "sglang stars:>100"
    burst_threshold: 0.6  # minimum burst score [0, 1] to trigger an alert
  official_pages:
    enabled: true
    pages:
      - url: https://api-docs.deepseek.com/
        whitelist_keywords:
          - release
          - update
```

## Run the server

```bash
RADAR_CONFIG=config/radar.yaml uvicorn radar.main:app --reload
```

Key endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check |
| `GET` | `/alerts` | List persisted alerts |
| `POST` | `/jobs/run/{job_name}` | Trigger a job immediately |
| `POST` | `/config/reload` | Hot-reload `config.yaml` without restart |

Registered job names: `official_pages`, `github_burst`, `daily_digest`.

## MVP paths

### 1 · Official-page monitoring

Polls configured URLs every 10 minutes. When a page's visible text contains a
whitelisted keyword the pipeline hashes the content, deduplicates, and sends one
alert per unique change.

```bash
# Trigger manually:
curl -X POST http://localhost:8000/jobs/run/official_pages
```

### 2 · GitHub burst detection

Queries the GitHub search API every 15 minutes. Repositories whose computed
burst score (stars × forks normalised) meets `burst_threshold` emit a
`github_burst` alert.

```bash
curl -X POST http://localhost:8000/jobs/run/github_burst
```

### 3 · Daily digest

Once per day the digest job ranks all stored alerts by score (descending) and
dispatches a single summary payload to every enabled channel.

```bash
curl -X POST http://localhost:8000/jobs/run/daily_digest
```

## CLI

```bash
# Validate a config file without starting the server
python3 -m radar.cli validate-config config/radar.yaml

# Trigger a job from the CLI
python3 -m radar.cli run-job github_burst --config config/radar.yaml

# Backfill one source
python3 -m radar.cli backfill-source github --config config/radar.yaml

# Send a test webhook
python3 -m radar.cli send-test-notification webhook --config config/radar.yaml
```

## Run tests

```bash
python3 -m pytest
```
