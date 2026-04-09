# Results Reader Upgrade Design

## 1. Goal

Upgrade the current results homepage from a simple alert browser into a
report-first reader that is closer to the referenced `agents-radar` experience.

The upgraded product should support:

- date-based daily report reading
- full-text search in the browser
- coarse filtering of report entries
- bilingual reading with Chinese descriptions for individual entries
- RSS/feed export
- the same capabilities in both the live FastAPI app and the GitHub Pages
  static export

This work should preserve the existing monitoring and persistence model while
adding a richer report archive layer on top.

## 2. Scope

### In scope

- enrich daily report data beyond the current `summary + grouped events` shape
- support local search and coarse filters on each daily report
- add bilingual presentation controls in the results UI
- generate Chinese descriptions for individual report entries
- generate a daily Chinese briefing for each report
- expose a feed entrypoint for archive readers
- keep live UI and static export on the same report contract

### Out of scope

- replicating every single section and layout detail from the reference site
- real-time model calls from the browser
- user accounts or personalized saved filters
- adding a separate SPA build system
- rewriting raw alert ingestion or persistence semantics

## 3. Product Decisions

### 3.1 Archive-first reader

The product should be built around an enriched daily report archive, not around
the flat alert list.

The current homepage already uses day-based report APIs. This design extends
that model so the report payload becomes the source of truth for:

- summary content
- entry rendering
- search
- coarse filtering
- bilingual display
- feed generation
- static export

### 3.2 Shared live/static contract

The live FastAPI homepage and GitHub Pages export must consume the same report
shape.

The current exporter already writes `manifest.json` plus per-day report JSON.
That pattern should remain, but the JSON documents should become richer so the
browser can offer reference-style reading features without needing a separate
rendering pipeline for static hosting.

### 3.3 Model-generated Chinese descriptions

Chinese descriptions for individual entries and the daily Chinese briefing
should be generated during report enrichment, not during page rendering.

This ensures:

- GitHub Pages can display the same enhanced content
- browser performance stays predictable
- missing model configuration does not break page rendering
- the enriched archive remains inspectable and testable as data

### 3.4 Graceful degradation

The reader must remain usable without model output.

If the summarization model is unavailable or disabled:

- search still works
- coarse filters still work
- daily reports still load
- entries fall back to existing source text / structured fields
- bilingual toggles may show Chinese labels plus original-language content where
  no generated Chinese summary is available

## 4. Chosen Approach

Add a new **report enrichment layer** between persisted alerts and the results
reader UI.

The system becomes three layers:

1. **Raw monitoring layer**
   - existing entities, observations, alerts
   - existing deduplication and source-specific alert generation
2. **Report enrichment layer**
   - normalize alert rows into reader-friendly entries
   - derive filter metadata and search text
   - generate bilingual summary fields
   - compose daily briefing content
3. **Reader UI layer**
   - date navigation
   - local search
   - coarse filters
   - language toggle
   - RSS/feed entrypoints

This approach adds the requested reader capabilities without turning the
frontend into a second business-logic implementation.

## 5. Data Model Design

### 5.1 Manifest shape

The manifest should continue to index dates, but include richer metadata needed
for navigation and discovery.

Recommended fields:

- `generated_at`
- `dates[]`
  - `date`
  - `count`
  - `topics`
  - `filter_counts`
  - `briefing_available`

The existing `count` remains the deduplicated report-entry count for that day.

### 5.2 Daily report shape

Each daily report document should grow from the current minimal shape to a
reader-ready structure:

```json
{
  "date": "2026-04-09",
  "summary": {
    "total_alerts": 6,
    "top_sources": [{"source": "github", "count": 4}],
    "max_score": 0.9,
    "briefing_zh": "今日重点是……",
    "briefing_en": "Today's highlights are ..."
  },
  "filters": {
    "sources": [{"value": "github", "count": 4}],
    "alert_types": [{"value": "github_burst", "count": 4}],
    "score_bands": [{"value": "high", "count": 2}],
    "topic_tags": [{"value": "ai-trending", "count": 3}]
  },
  "topics": [
    {
      "topic": "github",
      "count": 4,
      "events": [
        {
          "id": 123,
          "source": "github",
          "alert_type": "github_burst",
          "display_name": "owner/repo",
          "url": "https://github.com/owner/repo",
          "score": 0.9,
          "created_at": "2026-04-09T08:00:00+00:00",
          "reason": {"full_name": "owner/repo", "stars": 25},
          "reason_text_en": "Repository owner/repo saw burst activity ...",
          "reason_text_zh": "仓库 owner/repo 出现明显热度增长……",
          "title_zh": "可选中文标题",
          "search_text": "owner repo github burst stars 25 ...",
          "filter_tags": {
            "source": "github",
            "alert_type": "github_burst",
            "score_band": "high",
            "topic_tags": ["ai-trending"]
          }
        }
      ]
    }
  ]
}
```

The document does not need every field to be mandatory for every source, but it
must keep one consistent top-level contract so the UI can render all sources
with the same code path.

### 5.3 Entry normalization

Each source should map into a common reader entry shape:

- common identity: `id`, `canonical_name`, `source`, `alert_type`
- common display: `display_name`, `url`, `created_at`, `score`
- common search/filter: `search_text`, `filter_tags`
- common bilingual fields: `reason_text_en`, `reason_text_zh`, optional
  `title_zh`

Source-specific data can remain inside `reason` or `normalized_payload`, but the
reader should not need source-specific rendering logic just to support search,
filters, or bilingual descriptions.

## 6. Summarization Design

### 6.1 External model integration

Add a report summarization configuration section using an OpenAI-compatible API
contract.

Recommended config shape:

```yaml
summarization:
  enabled: true
  base_url: https://api.openai.com/v1
  api_key: sk-...
  model: gpt-4.1-mini
  timeout_seconds: 20
  max_input_chars: 4000
```

The implementation should not hardcode one provider. An OpenAI-compatible HTTP
client keeps the contract flexible enough for OpenAI-compatible gateways and
hosted models.

### 6.2 Enrichment flow

For each report entry:

1. build a compact source-aware prompt from the title, source, score, and
   structured reason fields
2. request a Chinese explanation for the entry
3. optionally request a concise Chinese title when the original title is not
   already user-friendly

For each daily report:

1. assemble the top entries and source distribution
2. request a short daily Chinese briefing
3. optionally request an English briefing if the UI exposes full bilingual
   summary switching

### 6.3 Failure handling

If a model request fails:

- log or surface the failure in the same style as the rest of the application
- omit only the affected generated fields
- continue building the rest of the report

Do not let one failed summary call drop the entire daily report.

## 7. Filtering and Search Design

### 7.1 Search

Search should run client-side against the already-loaded daily report JSON.

It should match at least:

- display name / title
- generated Chinese description
- original reason text / derived English text
- source name
- alert type
- topic tags

This keeps both live and static behavior identical and avoids adding a new
search service.

### 7.2 Coarse filters

The first version should support filters that are visible and stable across
sources:

- source
- alert type
- score band
- topic / category tag

The reader should expose these filters as quick-toggle controls rather than a
complex faceted search UI.

### 7.3 URL persistence

The results reader should use URL hash state so views are shareable, similar to
the reference site.

Recommended state dimensions:

- date
- topic
- language
- search query
- selected filters

This allows deep links into a specific report slice on both the live site and
GitHub Pages.

## 8. Feed Design

Add a feed export that is derived from the enriched archive rather than from raw
alerts.

Recommended first version:

- one global feed for the most recent enriched entries
- each item includes title, source, link, created time, and a compact Chinese
  or fallback description

This is enough to add a reader-facing RSS entrypoint similar to the reference
site without introducing a full feed-per-topic matrix in the first iteration.

## 9. UI Design

### 9.1 Information architecture

The upgraded reader should keep the current split layout but add a richer top
toolbar.

Recommended structure:

- **Header**
  - title
  - RSS link
  - theme toggle
  - global language toggle
  - search box
- **Left sidebar**
  - date archive
  - topic/source navigation
  - coarse filters
- **Main content**
  - daily Chinese briefing / summary card
  - secondary summary metrics
  - result entry list
  - per-entry `ZH / EN` toggle or inherited global language mode

### 9.2 Reader behavior

The UI should load one day at a time:

1. fetch manifest
2. choose active date
3. fetch enriched daily report
4. apply local search/filter/language state
5. render summary plus filtered entries

Language switching should not require another server round trip once the daily
report JSON is loaded.

### 9.3 Static export compatibility

The current static export injects a different fetch base path. That pattern
should remain unchanged.

The UI must keep all new interactions client-side so the same JavaScript bundle
works for:

- `GET /reports/*` in live mode
- `./manifest.json` + `./reports/*.json` in static mode

## 10. Backend Surface Changes

The existing `build_report_manifest()` and `build_report_payload()` helpers
should evolve into enriched report builders.

Likely additions:

- reusable entry-normalization helpers
- reusable filter-derivation helpers
- reusable summarization client / service
- feed route(s)

The existing raw repository queries can stay mostly intact; the primary change
is the report-building layer above them.

## 11. Testing Strategy

Add tests at four levels:

### 11.1 Report builder tests

Verify:

- enriched entry fields are present
- filter metadata is correct
- search text includes expected tokens
- per-day summary includes the generated briefing when available
- fallback behavior works when summarization is disabled or fails

### 11.2 API tests

Verify:

- manifest exposes richer navigation/filter metadata
- daily report payload includes bilingual and search/filter fields
- feed route renders valid items

### 11.3 UI tests

Verify:

- search box is wired
- filters affect the visible entry list
- language toggle switches rendered content
- hash state restores the expected view

### 11.4 Export tests

Verify:

- static export writes the enriched manifest/report documents
- static shell includes the new controls
- exported pages can use search/filter/language switching without server APIs

## 12. Implementation Notes

To keep scope reasonable, the first implementation should prioritize:

1. enriched report contract
2. client-side search
3. coarse filters
4. bilingual entry descriptions
5. daily Chinese briefing
6. RSS export

This ordering delivers the most visible product improvement first while keeping
the frontend and export paths aligned.
