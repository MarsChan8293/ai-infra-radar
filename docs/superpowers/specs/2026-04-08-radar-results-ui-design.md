# AI Infra Radar Results UI Design

## 1. Goal

Replace the current operations-console-first frontend with a **radar results
browser** that makes monitoring output the default product surface.

The first version should:

- open the radar results page at `/`
- remove the old `/ui` entrypoint
- move operational controls to `/ops`
- let readers browse radar output by **date first**, then **source/topic**
- show a **report-style summary** plus a **scannable event list**
- support publishing the same result archive to **GitHub Pages**

This work keeps the product lightweight and does not introduce a separate SPA,
frontend build pipeline, auth layer, or a new reporting service.

## 2. Scope

### In scope

- a FastAPI-served results browser as the default homepage
- a dedicated `/ops` route for the existing operational console
- grouped report APIs for date-based browsing
- deterministic rule-based summaries derived from stored alerts
- static export of dated report snapshots for GitHub Pages
- tests and documentation for the new route model and export flow

### Out of scope

- LLM-generated summaries in v1
- live push updates or websocket subscriptions
- user accounts, auth, or role-based access
- in-browser config editing
- a separate Node/Vite/React frontend stack
- preserving backward compatibility for the old `/ui` URL

## 3. Product Decisions

### 3.1 Primary entrypoints

The route model for v1 is:

- `/` → radar results browser
- `/ops` → operational console
- `/ui` → removed

The radar page is the default homepage for both local usage and GitHub Pages.
The operational console remains part of the application, but it is no longer
the main product surface.

### 3.2 Primary reading model

The reading flow is:

1. choose a **date**
2. narrow by **source/topic**
3. read the **summary**
4. inspect the underlying **events**

This keeps the experience close to `agents-radar`: the user enters through a
dated archive, not through operational controls or a flat alert table.

### 3.3 Summary strategy

The first version uses **rule-based summaries only**.

The summary is derived from persisted alerts and grouped report data. It should
highlight:

- total alerts for the selected day
- top sources by count
- highest-scoring signals
- simple topic counts

The summary must be deterministic and must not depend on an external model call.

## 4. Chosen Approach

Build one shared results model that serves both:

- the live FastAPI UI at `/`
- the static GitHub Pages export

The backend should expose grouped report data by day. The frontend should stay
thin and only render the returned structure. The static exporter should write
the same shape to dated JSON files and a manifest so the Pages site behaves
like the live UI with a different fetch source.

This is the recommended approach because it keeps one data contract, one visual
shell, and one archive structure instead of creating separate live and static
products.

## 5. Information Architecture

## 5.1 Homepage layout

The default homepage should have two main regions:

1. **Left navigation**
   - date list as the primary index
   - topic/source list scoped to the selected date
2. **Right content pane**
   - report title and context
   - summary block
   - event list

The left side should support quick archive browsing. The right side should read
like a lightweight daily report rather than an admin dashboard.

## 5.2 Navigation behavior

When the user opens `/`:

1. load the available report dates
2. select the newest date by default
3. show that day’s summary and events
4. let the user filter the visible event list by topic/source

The source/topic filter is subordinate to the selected date. The UI should not
mix events from multiple days in one report view.

## 5.3 Event presentation

Each event card should show the smallest useful set of fields for scanning:

- display name
- source
- alert type
- score
- created time
- a short reason/detail snippet
- destination URL when available

The event list is evidence for the summary. It should stay readable without
requiring the user to open a separate detail drawer for every item.

## 6. Backend Design

### 6.1 Report read APIs

Add report-oriented read APIs instead of reusing the flat alerts API directly.

Recommended endpoints:

- `GET /reports/manifest`
  - returns available dates
  - includes per-date counts and topics
- `GET /reports/{date}`
  - returns one day’s summary and grouped events

These APIs should read from existing persisted alerts/entities rather than
introducing a new report table for v1.

### 6.2 Repository query helpers

Add focused repository helpers that:

- list report days in reverse chronological order
- fetch all alerts for one UTC day
- join alert rows with entity metadata needed for rendering
- support summary aggregation without duplicating query logic in the API layer

The repository should return a clean report-view model or enough normalized data
for the route layer to build one deterministically.

### 6.3 Operations UI relocation

Keep the current operational console behavior, but move its entry route from
`/ui` to `/ops`.

The operational console may continue to use:

- `GET /alerts`
- `GET /alerts/{id}`
- `GET /jobs`
- `POST /jobs/run/{job_name}`
- `POST /config/reload`

This preserves operator workflows while clearly separating them from the reader
experience.

## 7. Frontend Design

### 7.1 Results browser shell

The results browser should remain a static HTML/CSS/JavaScript page served by
FastAPI. No new frontend toolchain is needed.

Suggested structure:

```text
radar/
  api/routes/
    home.py
    ops_ui.py
    reports.py
  ui/
    results/
      index.html
      styles.css
      app.js
    ops/
      index.html
      styles.css
      app.js
```

If shared browser helpers appear, add a small shared module instead of letting
the main script grow into one large file.

### 7.2 Browser data flow

The results browser should:

1. fetch `/reports/manifest`
2. select the newest date
3. fetch `/reports/{date}`
4. render summary and topic list
5. filter the visible event cards on the client for the selected topic

The browser must not compute business scores or invent summary facts that are
not present in the report payload.

### 7.3 Empty and failure states

The results browser should handle:

- no reports yet
- selected date not found
- report fetch failure
- manifest fetch failure

The page shell should remain visible with explicit inline failure text. No
silent fallback to empty content.

## 8. GitHub Pages Export

### 8.1 Export shape

The export should produce a static site rooted at the output directory with:

- `index.html`
- static assets for the results browser
- `manifest.json`
- dated report JSON files under a predictable archive path

Recommended archive shape:

```text
site/
  index.html
  manifest.json
  reports/
    2026-04-08.json
    2026-04-07.json
```

The manifest should list available dates, counts, and topics so the browser can
render the left navigation without server code.

### 8.2 Shared contract

The static export should reuse the same report payload shape as the live API.

That means:

- live mode fetches from `/reports/...`
- Pages mode fetches from local `manifest.json` and `reports/<date>.json`

The rendering logic should stay the same aside from the data source base path.

### 8.3 Deployment

Add a GitHub Actions workflow that:

1. checks out the repository
2. installs the Python project
3. runs a CLI export command
4. uploads the generated static directory as the Pages artifact
5. deploys to GitHub Pages

The exported Pages site must open directly into the radar results browser.

## 9. Migration and Compatibility

- `/` becomes the new default homepage
- `/ops` becomes the explicit operator entrypoint
- `/ui` is removed instead of redirected
- README examples should point to `/` for product browsing and `/ops` for
  operator controls

This is an intentional product-surface reset, not a compatibility-preserving
rename.

## 10. Testing Strategy

The implementation should include:

- API tests for report manifest and per-day report responses
- UI tests for the new homepage shell and `/ops` shell
- exporter tests for manifest and dated JSON output
- CLI tests for the Pages export command
- README/workflow checks covering the new default entrypoint
- full regression suite execution before completion

## 11. Risks and Constraints

- The existing persistence model is alert-centric, so the report layer must stay
  query-based and lightweight in v1
- The current operational UI assets should not be mixed into the new homepage
  script blindly; route separation should stay clear
- GitHub Pages is static, so the export format must not depend on runtime-only
  server features

## 12. Success Criteria

The work is successful when:

- opening `/` shows the radar results browser, not the operations console
- opening `/ops` shows the operational console
- `/ui` no longer serves the old console
- the results browser supports date-first archive browsing
- the right pane shows a deterministic summary and matching event list
- the same archive can be exported and published to GitHub Pages
