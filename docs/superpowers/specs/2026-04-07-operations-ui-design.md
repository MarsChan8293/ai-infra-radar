# AI Infra Radar Operations UI Design

## 1. Goal

Add the first frontend UI for AI Infra Radar as an **internal operations console**
that runs inside the existing FastAPI service.

The first version should let an operator:

- inspect recent alerts
- inspect one alert in detail
- manually trigger existing jobs
- reload runtime config and see the outcome

This UI extends the current service; it does not introduce a separate frontend
deployment, auth system, or new backend business workflows.

## 2. Scope

### In scope

- one browser-accessible UI entrypoint served by FastAPI
- a single-page internal operations console
- alert list and alert detail views backed by existing alert APIs
- job trigger controls backed by existing manual trigger APIs
- config reload control backed by the existing config reload API
- lightweight layout, styling, and interaction states for operational use
- tests proving the UI entrypoint and static assets are wired correctly

### Out of scope

- public-facing product UI
- user authentication / RBAC
- dashboard analytics beyond existing alert data
- live push updates / websockets
- editing config values from the browser
- full design system / component library
- separate SPA build pipeline (React/Vue/Vite)

## 3. Chosen Approach

Build the UI as a **FastAPI-served static single-page console**.

The backend will expose:

- `GET /ui` for the HTML shell
- static assets for CSS and JavaScript

The browser will then call the existing APIs:

- `GET /alerts`
- `GET /alerts/{id}`
- `POST /jobs/run/{job_name}`
- `POST /config/reload`

This is the recommended approach because the repository currently has no
frontend toolchain, no Node-based build system, and already has the backend
APIs needed for a useful internal console. It keeps deployment as one process,
adds minimal moving parts, and stays aligned with the current modular-monolith
architecture.

## 4. User and Operating Assumptions

The first UI is designed for:

- developers
- operators
- maintainers of the radar service

It is assumed to be used in trusted environments such as local development,
internal servers, or protected networks. Because the current system has no auth
layer, the UI should be treated as an internal tool, not a public product
surface.

## 5. Information Architecture

The UI should be a single page with three primary sections:

1. **Alerts**
   - default primary view
   - shows recent alerts
   - supports selecting an alert to inspect details
2. **Jobs**
   - exposes manual job triggers for:
     - `official_pages`
     - `github_burst`
     - `huggingface_models`
     - `daily_digest`
3. **Runtime / Config**
   - exposes config reload
   - shows the returned runtime summary such as timezone and registered jobs

Alerts should be the visually dominant section because it represents the main
product output. Jobs and runtime controls should be clearly available but
secondary.

## 6. Page Structure and Components

### 6.1 Shell

The page shell should include:

- app title
- short environment/usage hint
- primary navigation via tabs or a compact side navigation

This shell is layout-only and must not contain business logic.

### 6.2 Alerts panel

The alerts panel should include:

- a refresh action
- a list of alerts sorted by backend order
- key summary fields per row:
  - alert type
  - source
  - score
  - created time
- a detail pane or detail card for the selected alert

The detail view should surface:

- alert id
- type
- source
- score
- status
- reason payload
- created time

### 6.3 Jobs panel

The jobs panel should render one action card per known job.

Each card should show:

- job name
- short description
- trigger button
- last action feedback on this page session

For the first version, job execution history does not need to persist in the UI.

### 6.4 Runtime / Config panel

This section should include:

- a reload config button
- the latest reload result
- returned timezone
- returned job list

If reload fails, the error detail from the API should be shown directly to the
operator.

### 6.5 Shared status feedback

Use one shared status/toast/banner mechanism for:

- loading states
- successful actions
- failed actions

This avoids scattering inconsistent feedback logic across panels.

## 7. Data Flow

The UI should stay thin and treat the backend as the source of truth.

### 7.1 Alerts flow

1. Page loads
2. UI fetches `GET /alerts`
3. User selects one alert
4. UI fetches `GET /alerts/{id}`
5. UI renders the detail pane

### 7.2 Job trigger flow

1. User clicks a job trigger button
2. UI calls `POST /jobs/run/{job_name}`
3. UI shows accepted / failure feedback

### 7.3 Config reload flow

1. User clicks reload
2. UI calls `POST /config/reload`
3. UI renders success data or explicit failure detail

The frontend must not re-implement alerting rules, scoring rules, or source
logic. It only orchestrates API calls and renders results.

## 8. Technical Design

### 8.1 Backend additions

Add a minimal UI surface to the FastAPI app:

- `radar/api/routes/ui.py` for the `/ui` entry route
- a static asset directory for CSS and JavaScript

FastAPI should serve both the HTML entrypoint and the static files directly.

### 8.2 Frontend implementation style

The UI should use:

- plain HTML
- plain CSS
- small, focused browser JavaScript modules

This avoids introducing a separate frontend build system before the product
actually needs one.

### 8.3 File organization

Suggested first-version layout:

```text
radar/
  api/routes/ui.py
  ui/
    index.html
    styles.css
    app.js
```

If the browser code grows, it can later split into focused modules such as:

- `alerts.js`
- `jobs.js`
- `runtime.js`
- `api.js`

The first version should not over-modularize prematurely.

## 9. Error Handling

- Alert list failure:
  - keep the page shell visible
  - show an inline error state
  - offer retry
- Alert detail failure:
  - preserve the selected row
  - show detail load failure in the detail pane only
- Job trigger failure:
  - show the failure near the relevant job card
- Config reload failure:
  - surface backend detail verbatim in the runtime section
- Any loading state:
  - use button disabled states and inline loading text instead of blocking the
    entire page

No silent failures.

## 10. Testing Strategy

The first implementation should include:

1. **route wiring tests**
   - `/ui` returns success
   - static assets are served
2. **content smoke tests**
   - page contains the expected console sections
   - primary action labels are present
3. **non-regression backend tests**
   - existing API behavior remains unchanged after UI routing is added

Browser end-to-end automation is not required for the first slice.

## 11. Success Criteria

This design is successful when:

- an operator can open `/ui` in the browser
- recent alerts are visible without using curl
- one alert can be inspected in detail
- jobs can be manually triggered from the page
- config reload can be triggered from the page
- all action outcomes are visible in the UI
- the service remains deployable as one FastAPI process

## 12. Future Evolution

If the UI proves useful and grows beyond an internal control console, the next
phase can revisit:

- auth and access control
- richer filtering and search
- persistent job run history views
- charts and trend visualization
- migration to a dedicated SPA frontend
