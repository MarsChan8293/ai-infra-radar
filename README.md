# ai-infra-radar

Track AI infrastructure releases, model updates across Hugging Face / ModelScope / Modelers, GitHub and GitCode activity, and deliver a daily digest via webhook or email.

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
  huggingface:
    enabled: false
    organizations:
      - deepseek
  modelscope:
    enabled: false
    organizations:
      - Qwen
  modelers:
    enabled: false
    organizations:
      - MindSpore-Lab
  gitcode:
    enabled: false
    token: your-gitcode-token  # requires org-read scope
    organizations:
      - gitcode
```

## Run the server

```bash
RADAR_CONFIG=config/radar.yaml uvicorn radar.main:app --reload
```

Key endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check |
| `GET` | `/` | Radar results homepage |
| `GET` | `/alerts` | List persisted alerts |
| `GET` | `/ops` | Operations console |
| `POST` | `/jobs/run/{job_name}` | Trigger a job immediately |
| `POST` | `/config/reload` | Hot-reload `config.yaml` without restart |

Registered job names: `official_pages`, `github_burst`, `huggingface_models`, `modelscope_models`, `modelers_models`, `gitcode_repos`, `daily_digest`.

## Web UI

Start the server with a valid config:

```bash
RADAR_CONFIG=config/radar.yaml uvicorn radar.main:app --reload
```

Then visit:

```text
http://127.0.0.1:8000/
```

The default homepage is the radar results browser:

- date-first browsing of grouped report data
- source/topic filtering inside the selected day
- report summary plus event list

The operations console is available at:

```text
http://127.0.0.1:8000/ops
```

The operations console includes:

- alert list and detail inspection
- manual job trigger buttons
- config reload feedback

## GitHub Pages

Export the radar results browser as a static site:

```bash
python3 -m radar.cli export-pages --config config/radar.yaml --output site
```

The exporter writes a GitHub Pages-friendly archive with:

- `index.html`
- `app.js`
- `styles.css`
- `manifest.json`
- `reports/YYYY-MM-DD.json`

The repository workflow supports both **scheduled publishing** and **manual
workflow dispatch**. Configure a `RADAR_CONFIG_YAML` repository secret so the
workflow can build runtime settings, collect current source data, preserve the
existing static archive, and deploy the refreshed site to GitHub Pages.

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

To narrow the candidate set down to paper-code repositories, enable the
optional README secondary filter. This fetches each matched repository's README
and keeps only repositories whose README contains at least one configured
keyword such as `citation`, `bibtex`, or `@inproceedings{`.

Example for AI inference performance optimization repositories:

```yaml
sources:
  github:
    enabled: true
    token: ghp_example
    queries:
      - '"speculative decoding" created:>@today-7d'
      - '"kv cache" inference created:>@today-7d'
      - '"prefix caching" llm created:>@today-7d'
      - '"continuous batching" llm created:>@today-7d'
      - '"paged attention" created:>@today-7d'
    burst_threshold: 0.25
    readme_filter:
      enabled: true
      require_any:
        - citation
        - bibtex
        - "@inproceedings{"
        - "@article{"
```

Filtering is case-insensitive. Repositories without a matching README are
excluded from the GitHub alert path.

GitHub itself only accepts absolute dates, but AI Infra Radar supports the
relative placeholders `@today`, `@today-7d`, and `@today+3d` inside GitHub
queries and resolves them to `YYYY-MM-DD` before calling the GitHub API.

```bash
curl -X POST http://localhost:8000/jobs/run/github_burst
```

### 3 · Hugging Face model monitoring

Polls configured Hugging Face organizations and emits one alert when a model is
first seen, plus an update alert when the upstream `lastModified` timestamp
changes.

```bash
curl -X POST http://localhost:8000/jobs/run/huggingface_models
```

### 4 · ModelScope model monitoring

Polls configured ModelScope organizations and emits one alert when a model is
first seen, plus an update alert when the upstream `LastUpdatedTime` changes.

```bash
curl -X POST http://localhost:8000/jobs/run/modelscope_models
```

### 5 · Modelers model monitoring

Polls configured Modelers organizations and emits one alert when a model is
first seen, plus an update alert when the upstream `updated_at` changes.

```bash
curl -X POST http://localhost:8000/jobs/run/modelers_models
```

### 6 · GitCode repository monitoring

Polls configured GitCode organizations through the authenticated API and emits
one alert when a repository is first seen, plus an update alert when the
upstream `updated_at` changes.

```bash
curl -X POST http://localhost:8000/jobs/run/gitcode_repos
```

### 7 · Daily digest

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
python3 -m radar.cli run-job huggingface_models --config config/radar.yaml
python3 -m radar.cli run-job modelscope_models --config config/radar.yaml
python3 -m radar.cli run-job modelers_models --config config/radar.yaml
python3 -m radar.cli run-job gitcode_repos --config config/radar.yaml

# Backfill one source
python3 -m radar.cli backfill-source github --config config/radar.yaml
python3 -m radar.cli backfill-source huggingface --config config/radar.yaml
python3 -m radar.cli backfill-source modelscope --config config/radar.yaml
python3 -m radar.cli backfill-source modelers --config config/radar.yaml
python3 -m radar.cli backfill-source gitcode --config config/radar.yaml

# Send a test webhook
python3 -m radar.cli send-test-notification webhook --config config/radar.yaml
```

## Run tests

```bash
python3 -m pytest
```
