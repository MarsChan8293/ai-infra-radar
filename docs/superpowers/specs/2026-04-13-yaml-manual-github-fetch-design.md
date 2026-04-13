# YAML-Style Manual GitHub Fetch Design

## Goal

Replace the current `/ops` manual GitHub fetch form with a YAML-driven editor so
operators can paste and edit a `sources.github`-style config fragment directly,
instead of filling separate date/query/prompt fields.

The result view remains an **analysis surface**, not an alert simulator:

1. coarse GitHub/README results
2. README AI second-pass results
3. per-item errors

## User-approved decisions

- The `/ops` input should be a single YAML editor
- Users paste only the contents of `sources.github`, not the outer `github:` key
- Runtime credentials and provider transport settings still come from the live
  server config, not from the pasted YAML
- The result panes remain `coarse_results`, `secondary_results`, and `errors`
- `burst_threshold` is still accepted and validated, but does **not** change the
  meaning of the manual analysis panes

## Non-goals

- Replacing the scheduled `github_burst` config format
- Turning the manual page into a final alert/threshold dashboard
- Asking operators to paste tokens or provider secrets into the page
- Persisting manual runs into alerts, reports, feed output, or database records

## Current problem

The current manual fetch UI is form-based:

- `start_date`
- `end_date`
- `query`
- `readme_prompt`

That shape works for a single ad-hoc query but is awkward for the real workflow,
where operators already think in terms of the existing YAML config:

- multiple queries
- keyword README prefilter
- AI README filter settings
- burst threshold

## Proposed UX

The `/ops` manual fetch panel becomes a YAML editor with a default template based
on the current `sources.github` config structure.

Example editor contents:

```yaml
queries:
  - '"speculative decoding" created:>@today-1d'
  - '"kv cache" inference created:>@today-1d'
burst_threshold: 0.01
readme_filter:
  enabled: true
  require_any:
    - citation
    - bibtex
ai_readme_filter:
  enabled: true
  model: nvidia/nemotron-3-super-120b-a12b
  default_prompt: |
    Read this repository README and decide whether it is directly relevant
    to AI inference, serving, runtime optimization, memory efficiency, or
    model deployment infrastructure. Return JSON with:
    - keep: boolean
    - reason_zh: concise Chinese reason
    - matched_signals: list of short strings
```

The panel still includes:

- `Run fetch`
- summary block
- coarse results
- second-pass results
- errors

## Backend contract

Replace the request shape for `POST /ops/github/manual-fetch` with a YAML-based
payload, for example:

```json
{
  "github_config_yaml": "queries:\n  - \"speculative decoding\" created:>@today-1d\n..."
}
```

The server will:

1. wrap the pasted YAML as a temporary GitHub config fragment
2. validate it with the existing GitHub config model
3. merge in runtime-only dependencies from the live app state:
   - GitHub client/token
   - README AI runtime dependency
   - shared provider transport config already loaded by the app
4. run the same manual analysis pipeline used today, but across all configured
   queries instead of one `query` field

## Query and filtering behavior

Manual YAML execution should behave like this:

1. run every configured query
2. merge the returned repository candidates
3. collect README status for each candidate
4. apply keyword README prefilter when `readme_filter.enabled`
5. apply README AI second-pass filtering when `ai_readme_filter.enabled`
6. return analysis results

The manual endpoint remains **analysis-first**, so:

- `coarse_results` means the README collection stage output
- `secondary_results` means the AI second-pass keep set
- `errors` covers missing README, README fetch failures, and AI failures

`burst_threshold` is parsed and validated because it belongs to the pasted YAML
shape, but it does not filter these manual analysis panes. It may appear in the
summary/request echo for operator context only.

## Validation and error model

The endpoint should fail fast for:

- invalid YAML
- YAML that does not match the accepted `sources.github` fragment shape
- missing `queries`
- `ai_readme_filter.enabled: true` in the pasted YAML when the live runtime
  dependency is unavailable

The endpoint should continue to report per-repository failures for:

- missing README
- README fetch exceptions
- README AI evaluation failures

No silent fallback to “all repositories passed” is allowed.

## Frontend behavior

The `/ops` UI will:

- replace the current date/query/prompt controls with one YAML textarea
- seed the textarea with a config-shaped template
- submit `{ github_config_yaml }` as JSON
- keep the current disabled-while-running behavior
- keep clearing stale results after failed reruns
- keep rendering the current summary/coarse/second-pass/error sections

## Testing

Add or update tests for:

1. `/ops` HTML shell contains the YAML editor instead of the old split fields
2. frontend JS posts `github_config_yaml`
3. invalid YAML returns a clear validation error
4. valid YAML with multiple queries reuses the existing README/AI pipeline
5. keyword README filtering and AI second pass both honor the pasted config
6. stale result clearing still works after failed reruns

## Scope

This is a focused follow-up change to the manual GitHub fetch feature only. It
does not change scheduled job semantics, report rendering, or persisted alert
behavior.
