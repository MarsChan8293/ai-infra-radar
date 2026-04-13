# Manual GitHub Fetch and README AI Filtering Design

## Goal

Add a manual GitHub research workflow to `/ops` so an operator can enter a date range, a GitHub query, and a README AI prompt, then inspect both:

1. the coarse GitHub search result set
2. the README-based AI second-pass result set

This workflow must not write alerts or observations into the database. It is a manual analysis surface only.

At the same time, the new README AI second-pass filtering logic must be reusable by the scheduled GitHub pipeline so that manual and scheduled filtering stay aligned.

## Non-goals

- Persisting manual fetch runs or results
- Writing manual fetch output into alerts, observations, reports, or feeds
- Changing result-page search/filter/dedup contracts
- Replacing the existing keyword-based `readme_filter.require_any` prefilter

## User-approved decisions

- Date range is entered as separate `start_date` and `end_date` fields
- The system automatically composes the GitHub time clause into the query
- The default time dimension is `created`, not `pushed`
- Manual fetch results are shown in `/ops` only and are not persisted
- README second-pass filtering uses a default prompt template that is editable in the page
- Manual and scheduled GitHub filtering should share the same README AI filtering core

## Existing context

Current GitHub burst execution is:

1. expand configured query placeholders
2. call `GitHubClient.search_repositories(...)`
3. optionally apply keyword README filtering via `readme_filter.require_any`
4. score results and emit alerts

Current operations UI already supports read-only inspection and job triggering, but has no manual GitHub fetch form and no ad-hoc AI README filtering flow.

## Proposed architecture

Introduce a reusable GitHub candidate filtering pipeline with three layers:

### 1. Coarse search layer

Build a GitHub search query from:

- user/base query
- `created:{start}..{end}` clause

This layer returns the raw GitHub repository candidates.

### 2. README fetch layer

For each candidate, fetch README text and attach one of:

- `ok` + fetched README text
- `missing_readme`
- `fetch_error`

This layer is reused by both manual `/ops` fetches and scheduled GitHub filtering.

### 3. README AI second-pass layer

Send each fetched candidate to a dedicated README AI filter that returns structured JSON:

```json
{
  "keep": true,
  "reason_zh": "该仓库 README 明确描述了推理服务和缓存优化场景。",
  "matched_signals": ["inference serving", "kv cache"]
}
```

This second-pass layer is the shared source of truth for:

- `/ops` manual analysis output
- optional scheduled GitHub README AI filtering

## Why a dedicated README AI filter instead of reusing report summarization directly

The report summarizer explains already-selected results for the reader UI. README second-pass filtering decides whether a repository should remain in the candidate set at all. Those are different responsibilities.

To keep boundaries clear:

- keep a dedicated README AI filter abstraction for repository filtering
- optionally share provider/client plumbing with the existing OpenAI-compatible summarization integration

This preserves architectural clarity while avoiding duplicated low-level request logic.

## Backend changes

### New manual ops API

Add a manual operations endpoint, for example:

- `POST /ops/github/manual-fetch`

Request body:

```json
{
  "start_date": "2026-04-01",
  "end_date": "2026-04-10",
  "query": "\"speculative decoding\"",
  "readme_prompt": "Use this README to decide whether the repository is relevant to AI inference systems..."
}
```

Response body:

```json
{
  "request": {
    "query": "\"speculative decoding\" created:2026-04-01..2026-04-10",
    "start_date": "2026-04-01",
    "end_date": "2026-04-10",
    "readme_prompt": "..."
  },
  "summary": {
    "coarse_count": 12,
    "readme_success_count": 10,
    "readme_failure_count": 2,
    "secondary_keep_count": 4
  },
  "coarse_results": [
    {
      "full_name": "org/repo",
      "html_url": "https://github.com/org/repo",
      "description": "Repository description",
      "stars": 120,
      "forks": 17,
      "readme_status": "ok"
    }
  ],
  "secondary_results": [
    {
      "full_name": "org/repo",
      "html_url": "https://github.com/org/repo",
      "description": "Repository description",
      "stars": 120,
      "forks": 17,
      "reason_zh": "README 明确描述了推理服务相关能力。",
      "matched_signals": ["serving", "throughput"]
    }
  ],
  "errors": [
    {
      "full_name": "org/bad-repo",
      "stage": "readme_fetch",
      "message": "404 not found"
    }
  ]
}
```

### Shared GitHub manual/scheduled helpers

Extract shared helpers for:

- building created-range search queries
- collecting GitHub candidate metadata
- fetching README text with structured status
- applying the README AI filter

The scheduled GitHub path should continue to support the existing keyword prefilter. When AI README filtering is enabled in config, it should run after the keyword prefilter and before alert creation.

### Validation and failure model

- `start_date`, `end_date`, and `query` are required
- `start_date <= end_date`
- empty prompt falls back to the configured default prompt template in the UI/request path
- README fetch failures are reported per candidate, not as a whole-request crash
- AI filter failures are reported per candidate when possible; if provider configuration is missing, the request returns a clear top-level failure explaining that README AI filtering is unavailable

No silent fallback to “everything passed second stage” is allowed.

## Configuration changes

Add dedicated README AI filter settings under the GitHub source configuration, for example:

```yaml
sources:
  github:
    enabled: true
    token: ghp_example
    queries:
      - '"speculative decoding" created:>@today-7d'
    burst_threshold: 0.25
    readme_filter:
      enabled: true
      require_any:
        - citation
        - bibtex
    ai_readme_filter:
      enabled: true
      model: gpt-4.1-mini
      default_prompt: |
        Read this repository README and decide whether it is directly relevant
        to AI inference, serving, runtime optimization, memory efficiency, or
        model deployment infrastructure. Return JSON with keep, reason_zh,
        matched_signals.
```

Provider transport settings should reuse the existing OpenAI-compatible configuration shape where practical, but the feature should remain clearly scoped as README filtering rather than report summarization.

## `/ops` UI design

Add a new `Manual GitHub Fetch` panel to the operations UI with:

- `Start date`
- `End date`
- `Query`
- `README AI prompt`
- `Run fetch`

### Result regions

#### Run summary

Display:

- expanded query string
- coarse result count
- README fetch success/failure counts
- second-pass keep count

#### Coarse results list

Per item:

- repository name
- description
- stars / forks
- GitHub link
- README status

#### Second-pass results list

Per item:

- repository name
- description
- stars / forks
- GitHub link
- Chinese second-pass reason
- matched signals if present

### UX rules

- disable the submit button while a request is in flight
- keep results ephemeral in page state only
- show per-item README/AI failures instead of blank rows
- avoid mixing this manual result panel with persisted alerts data

## Scheduled GitHub pipeline alignment

The scheduled GitHub job should continue to own alert persistence, but its candidate filtering should be able to reuse the same README AI filter core.

Intended order for scheduled execution:

1. GitHub search
2. keyword README prefilter (`readme_filter.require_any`) if enabled
3. README AI second-pass filter if enabled
4. scoring / threshold
5. alert creation

This guarantees that manual `/ops` inspection and scheduled GitHub filtering stay behaviorally aligned.

## Testing strategy

### Config tests

- validate new `ai_readme_filter` config shape
- ensure required fields are enforced when enabled

### Backend API tests

- manual fetch endpoint returns separate coarse and second-pass lists
- date range is composed into the GitHub query
- invalid date ranges fail clearly
- README fetch failures surface as structured item errors
- AI second-pass output is rendered as structured JSON fields

### Scheduled pipeline tests

- scheduled GitHub path reuses the shared README AI filter helper when enabled
- keyword prefilter still works as before
- AI second-pass rejects repositories before alert creation

### UI tests

- `/ops` shell includes the new manual fetch form
- request submission wiring exists in the ops script
- result summary, coarse list, second-pass list, and errors render correctly

## Rollout expectations

After implementation:

- operators can experiment with ad-hoc GitHub queries and README prompts in `/ops`
- the same second-pass filtering architecture can be enabled for scheduled GitHub jobs
- manual analysis remains non-persistent and cannot pollute production alerts
