# WhatIf Mobility – Implementation Plan

> **Read this file at the start of every session.**
> Update the checklists and the "Current status" section at the end of
> every session. Project rules and conventions are in `CLAUDE.md`.

## Current status

- **Last completed:** Day 10, part 1b (scenario type "change frequency", backend + AI);
  168 backend + 76 Vitest + 5 Playwright tests
- **Next up:** Day 10, part 1c: "Frequency" tab in the form, map/legend feedback, e2e
- **Repository:** https://github.com/soniabecz/whatif-mobility (private, branch `main`)

## Timeline

Total: **9 working days done** (MVP in Days 1–5, Days 6–9 added afterwards);
Days 8–14 hold all later extensions (≈ 9–10 sessions; Days 10, 11 and 14 run long). A "day" is one
working session. Every day must end with something working and committed,
so the project is usable even if a later day is cut short.

| Day | Focus                     | Status  |
| --- | ------------------------- | ------- |
| 1   | Setup and skeletons       | ✅ Done |
| 2   | Data model and graph      | ✅ Done |
| 3   | Simulation engine         | ✅ Done |
| 4   | Map and results UI        | ✅ Done |
| 5   | AI layer and wrap-up      | ✅ Done |
| 6   | UI redesign               | ✅ Done |
| 7   | Quality and explainability | ✅ Done |
| 8   | Safety nets               | ✅ Done |
| 9   | Quick product wins        | ✅ Done |
| 10  | More realistic simulation | 🟡 In progress |
| 11  | New scenario types        | ⬜ Todo |
| 12  | AI features               | ⬜ Todo |
| 13  | Saving and comparing      | ⬜ Todo |
| 14  | Deployment and real data  | ⬜ Todo |

---

## Scope

### In scope (MVP)

- A small **invented** city bus network: ~15–20 stops, 3–4 routes
- Network displayed on a map
- **Three scenario types:**
  1. Close a stop
  2. Remove a connection between two stops
  3. Change the travel time of a connection
- Deterministic before/after metrics on passenger journeys
- Scenarios built with a form **and** from natural language (AI)

### Out of scope (cut to fit 4 days)

- Real city data (GTFS import)
- Adding new routes as a scenario type
- Saving scenarios to the database (simulations are run, shown, discarded)
- ~~UI polish~~ moved into scope as Day 6 (redesign); dark mode stays out of scope

---

## Technical decisions

| Decision | Reason |
| --- | --- |
| Separate `backend/` (FastAPI, port 8000) and `frontend/` (Vite, port 5173) | Required by `CLAUDE.md`; clear responsibilities |
| Python virtual environment in `backend/.venv` | Isolates project packages from the global Anaconda Python |
| Pinned versions in `backend/requirements.txt`; `package-lock.json` committed | Reproducible installs |
| CORS allows only `localhost:5173` / `127.0.0.1:5173`; Vite uses `strictPort` | Safer than `*`; avoids silent port changes breaking CORS |
| Frontend calls the backend through one Axios instance (`src/api/client.ts`) with `VITE_API_BASE_URL` | Base URL and timeout configured in one place |
| Network calls live in `src/api/`, shared types in `src/types/` | Components stay simple; types mirror backend Pydantic schemas |
| Thin API route handlers; logic in `app/services/` | Business logic is testable without a web server |
| SQLAlchemy models (`app/models/`) separate from Pydantic schemas (`app/schemas/`) | Database storage and API shape can change independently |
| Simulation runs on `graph.copy()` of the baseline graph | Baseline data is never modified (`CLAUDE.md` rule) |
| **AI only translates text → structured scenario JSON; the simulation computes all numbers** | AI must never invent simulation results |
| Simulation built and tested **before** the AI layer | AI is just another way to create a scenario; the app works without it |
| Invented sample network instead of real GTFS data | Easier to understand and test; no data cleaning |
| Tailwind CSS v4 via `@tailwindcss/vite` (no config file) | Current standard setup |
| Template uses `oxlint` (not ESLint) for `npm run lint` | Default in the current Vite template |
| Secrets only in git-ignored `.env` files; never in `VITE_` variables | `VITE_` variables are public in the browser |
| Stop and route ids are short readable codes (`CEN`, `R1`) | Scenarios, tests and AI output can name stops directly |
| Connections are directed, one row per route per direction | Matches the directed-graph rule; one-way changes are possible |
| `nx.DiGraph`; parallel connections from several routes merge into one edge (weight = fastest, `routes` = all) | "Remove/change connection A→B" has one clear meaning |
| ~~No transfer penalty in the MVP; a journey = fastest path~~ | Superseded Day 7 (penalty) and Day 10 (waiting) |
| Graph/journey functions take plain data, not a DB session | Testable without a DB; reusable by the simulation |
| SQLite file `backend/whatif.db` (git-ignored), rebuilt by `python -m app.seed` | Reproducible data; nothing generated is committed |
| Tables created on app startup; data only via the seed script | Fresh checkout gives empty lists, not a 500 error |
| Invented stops placed on a real map via `CITY_CENTER` in `seed/sample_network.py` | Realistic map tiles; city moved by changing one constant |
| Tests use an in-memory SQLite DB (`tests/conftest.py`) | Tests never touch the real database file |
| AI provider: Groq, model `openai/gpt-oss-120b` (configurable via `AI_MODEL`) | Production model with strict structured outputs; < 0.1 cent per request |
| AI flow: interpret → user reviews changes → run | AI never touches results; user sees what it understood |
| Separate strict AI output schema (`AIInterpretation`), converted to `Scenario` | Groq strict mode needs all fields required, no defaults/limits |
| AI answer checked 3×: strict JSON schema, `Scenario` validation, dry-run `apply_scenario` | Invalid stops/links never reach the user |
| Content problems → `status: "unclear"` + message; provider problems → 503, bad JSON → 502 | User gets an explanation instead of a generic error |
| Relative requests ("twice as slow") converted by the AI to absolute minutes from the times in the prompt | No new change types; result is visible before running |
| `ChatModel` protocol; tests use a fake, Groq errors mapped with locally built exceptions | No network calls or API key needed in tests |
| Settings via `pydantic-settings` from `backend/.env`; key held as `SecretStr` | Key never hardcoded, logged or committed |
| Without `GROQ_API_KEY` the AI endpoint returns 503; the rest works | AI is optional, the app works without it |
| UI: full-screen map with floating panels; bottom sheet below 1024 px | Map-first, modern; results stay next to the map |
| Design tokens in `index.css` via Tailwind v4 `@theme` (indigo accent, surfaces, radii, shadows) | One place for the look; consistent components |
| Shared UI building blocks in `components/ui/` | Consistent styling; reused by the Day 7 journey explorer |
| Muted basemap = OSM tiles + CSS filter (not CARTO) | CARTO now needs an API key, which would be public in the frontend |
| Inter font self-hosted via `@fontsource-variable/inter`; icons from `lucide-react` | No external font requests; one consistent icon set |
| `ScenarioForm` split into builder, `ChangeList` and `RunBar` | Run button pinned to the panel bottom; no behaviour change |
| API types generated by `openapi-typescript` from the exported OpenAPI file; `src/types/*.ts` are aliases | Backend schemas are the single source of truth; importers keep short names |
| Generator isolated in `frontend/tools/openapi/` with its own lockfile and TypeScript 5 | TypeScript 7 (native port) has no JS compiler API; npm cannot nest a peer dependency |
| Generated `openapi.json` and `api.gen.ts` committed; CI fails if they are stale | Reviewable diffs; frontend builds without the backend |
| Limits (`MAX_CHANGES`, 600 min, 500 chars) stay hand-written constants | OpenAPI generates types, not values |
| CI: GitHub Actions, 2 parallel jobs, Python 3.11 + Node 24, no secrets, read-only permissions | Matches local versions; proves the app works without the AI key |
| Actions pinned to major versions (`@v7`) | Bug fixes automatically, no breaking changes |
| No branch protection | User pushes directly to `main`; add if pull requests are used |
| Journey explorer: stateless `POST /api/journeys` with the scenario in the body | Same pattern as simulations; avoids paths for all 240 journeys in every response |
| Legs = fastest route per stretch; stay on the current bus when equally fast | Deterministic; honest about the missing transfer penalty (fixed in part 3) |
| Bypass edges store `route_via` (closed stops passed) | Journeys are drawn along the real street, not straight across the map |
| Explorer statuses checked against the simulation for every journey | Two views of one model can never disagree |
| Transfer penalty 5 min, setting `TRANSFER_PENALTY_MIN`, counted in times and shown separately | Stands in for waiting; transparent assumption |
| Route-aware graph: stop + platform nodes; journey = path − one penalty (first boarding free) | Changing bus becomes a real choice; legs come from the path |
| Closing a stop removes only the stop node | Buses drive through naturally; replaces the bypass special case |
| Services take the penalty as a parameter (default 0); the API passes the setting | Tests choose the value; API tests run isolated settings |
| ~~Legs = fastest route per stretch~~ (Day 7 part 2) | Superseded: legs now come straight from the path |
| Results collapsed by default (key figures), details on demand | Keeps the map visible after a run |
| Scenario = ordered list of 1–20 changes, discriminated by `type`; unknown fields rejected | One input format for form and AI; typos fail loudly |
| `both_directions` defaults to `true` for link changes | People think in streets, not one-way links |
| Link changes act on the merged edge (all routes on it) | Consistent with the merged-edge graph rule |
| `change_travel_time` sets an absolute time (0 < t ≤ 600 min) | Simple and unambiguous |
| **Close stop = buses drive through (option B):** node removed, per-route bypass edges P→N added with that route's own times | Realistic: no boarding/alighting/transfers, but the road stays |
| Graph edges keep `route_times` per route | Needed for correct bypass times (MKT–CEN is 3 min on R1, 2 on R4) |
| Simulation works on `copy.deepcopy(baseline)`; edge attributes replaced, never mutated | Baseline can never be modified (tested) |
| Passenger journeys = all ordered stop pairs (240), equal weight | No demand data; inventing it would be fake metrics |
| Journeys to/from a closed stop counted separately, excluded from other metrics | They are not "slower", they cannot exist |
| Response lists only changed journeys + summary + per-stop impact + top-5 stops | Small payload; per-stop data drives map highlighting |
| Times rounded to 0.1 min in responses; comparisons use a 1e-9 tolerance | Readable output; no false "changes" from float noise |
| Scenario errors → HTTP 422 with message "Change N (type): …" | Tells the user (and later the AI layer) exactly what is wrong |
| UI layout: sidebar (form + results) left, map right; stacked on narrow screens | Map stays visible next to the results |
| Form builds a list of changes; "to" stop limited to real neighbours | Matches the backend format; prevents most invalid scenarios |
| Editing the changes clears results; stale responses ignored (request id) | Results always match the listed scenario |
| UI loads `/api/network` instead of calling `/api/health` | Loading the network already proves the backend works |
| Stops drawn as `CircleMarker`, not `Marker` | Avoids Leaflet's broken default icon under Vite; easy to colour |
| Stop impact colours from the fixed status palette, always with icon + label | Colour is never the only signal (colour-blind safe) |
| Chart: grouped horizontal bars, before/after time of the 10 biggest changes | Counts are already in tiles; palette validated (CVD/contrast) |
| ~~No frontend test runner~~ (superseded Day 8) | Vitest for pure `lib/` helpers, one Playwright end-to-end test |
| Playwright e2e against the real backend + seeded data, not a mocked API | Only test that proves frontend and backend work together; simulations are read-only |
| E2E checks UI numbers against `POST /api/simulations`, not hardcoded values | Survives model changes (Day 10) while still catching display bugs |
| CSV: commas and `.` decimals, UTF-8 BOM, values exactly as computed | Standard for tools; BOM keeps accents in Excel; no numbers made in the browser |
| Waiting = half the headway at every boarding; board edge = penalty + wait | Random arrivals; first boarding too, so frequency changes matter for direct journeys |
| Headways invented (10/10/15/20 min) and labelled as such | No timetable data; must not look like real data |
| Transfer penalty default 5 → 2 min once waiting is modelled | 5 min stood in for waiting; keeping it would count waiting twice |
| No migrations: outdated tables are dropped and re-seeded | The database only holds generated sample data (until Day 13) |
| One route per boarding, even where routes share a street | Simple and deterministic; combined frequency documented as a limitation |
| Frequency change = new headway (absolute), never "+N buses" | One unambiguous number; the AI converts relative requests, as for travel times |
| Frontend `ScenarioChange` derived from the generated `Scenario` type | A new backend change type shows up in TypeScript (and its exhaustive switches) automatically |
| Shared link: readable `?s=` text, not base64 JSON; `:oneway` instead of `>` | Visible and hand-editable; browsers percent-encode `>` in URLs |
| Shared links are all or nothing, never auto-run | No silently incomplete scenarios; same "review, then run" step as the AI |
| Address bar synced on every list edit via `replaceState` | Always shareable, survives reload, no back-button spam |
| Form draft lifted to `App`; click rules as pure functions in `lib/changeDraft.ts` | Map and form edit one state; rules unit-tested without React |
| Map selection in its own Leaflet pane (z-index 390, below lines) | Leaflet stacks shapes by insertion order; a later selection would cover the lines |
| E2E clicks lines at their midpoint with the mouse | Vertical/horizontal SVG lines have a 0-px bounding box, which Playwright treats as invisible |
| One-command start: plain `dev.sh` (bash 3.2 compatible), not Docker Compose | No new dependency; hot reload and the existing `.venv`/DB/`.env` keep working |
| `dev.sh` never resets data: `app.seed --if-empty` | Running the app must not silently discard a database |
| Vitest in `node` environment, tests next to the code (`*.test.ts`) | Helpers have no DOM; no jsdom dependency; `tsc -b` type-checks the tests |

### Target backend structure

```
backend/app/
├── main.py                 FastAPI app, CORS, router registration
├── config.py               settings from environment variables (added when needed)
├── database.py             SQLAlchemy engine and session
├── models/                 SQLAlchemy tables
├── schemas/                Pydantic request/response models
├── api/                    route handlers (thin)
├── services/
│   ├── network_service.py      build NetworkX graph from DB
│   ├── simulation_service.py   copy graph, apply scenario, compute metrics
│   └── ai_service.py           text → structured scenario (separate!)
└── seed/                   sample network data
```

---

## Day 1 – Setup and skeletons ✅

**Outcome:** backend and frontend run and talk to each other; code on GitHub.

- [x] Check environment (Python 3.11, Node upgraded to v24, Git)
- [x] Backend: `.venv`, `requirements.txt`, FastAPI app
- [x] Backend: `GET /api/health` with Pydantic response model
- [x] Backend: CORS restricted to the Vite dev server
- [x] Backend: pytest tests for health endpoint and CORS (3 passing)
- [x] Frontend: Vite + React + TypeScript scaffold
- [x] Frontend: Tailwind CSS v4 and Axios
- [x] Frontend: typed API client and home page showing backend status
- [x] Root `README.md` and `frontend/.env.example`
- [x] Commit `e6a598b` and push to private GitHub repo

## Day 2 – Data model and graph ✅

**Outcome:** a sample network stored in SQLite, served by the API and
turned into a NetworkX graph that can calculate shortest journeys.

- [x] Explain data model design and get approval
- [x] `database.py`: SQLAlchemy engine/session for SQLite
- [x] SQLAlchemy models: Stop, Route, Connection (directed, with travel time)
- [x] Pydantic schemas for the network API responses
- [x] Seed script with the invented sample network (~15–20 stops, 3–4 routes)
- [x] `network_service.py`: build a directed NetworkX graph from the DB
      (stops = nodes, connections = edges, weight = travel time)
- [x] Shortest-journey calculation between two stops
- [x] API endpoints: list stops, list routes, get network
- [x] Tests: graph building, shortest path, endpoints
- [x] Run tests, explain changes, commit

## Day 3 – Simulation engine ✅

**Outcome:** a tested engine that applies a scenario to a copy of the
baseline graph and returns deterministic before/after metrics.

- [x] Explain scenario format and metrics; get approval
- [x] Pydantic scenario schema for the three types
      (close stop, remove connection, change travel time)
- [x] Validation errors for unknown stops/connections
- [x] `simulation_service.py`: copy graph → apply changes → compute metrics
- [x] Metrics (deterministic), e.g. journey times before/after,
      journeys that become impossible, most affected stops
- [x] Test that the baseline graph is never modified
- [x] Tests for each scenario type and for edge cases
- [x] `POST /api/simulations` endpoint
- [x] Run tests, explain changes, commit

## Day 4 – Map and results UI ✅

**Outcome:** user sees the network on a map, builds a scenario with a
form, and sees before/after results.

- [x] Install React Leaflet and Recharts
- [x] TypeScript types mirroring network and simulation schemas
- [x] Map component showing stops and routes
- [x] Scenario form (choose type, stop/connection, value)
- [x] Call `POST /api/simulations` and show loading / error states
- [x] Before/after comparison chart (Recharts)
- [x] Highlight affected stops on the map
- [x] Lint, build
- [x] Manual browser check (done by the user) and commit

**Risk:** fullest day. Fallback: show results as a table instead of charts.

## Day 5 – AI layer and wrap-up ✅

**Outcome:** user types a change in plain language; the AI turns it into
a structured scenario; the existing simulation computes the results.

- [x] Choose AI provider (Groq, `openai/gpt-oss-120b`); API key in `backend/.env`
- [x] `config.py` reading settings from environment; `backend/.env.example`
- [x] `ai_service.py`: text → scenario JSON (no metrics from AI)
- [x] Validate AI output with the Pydantic scenario schema
- [x] Clear error when the request cannot be understood
- [x] Tests for AI service with a mocked AI client
- [x] Natural-language input in the UI, reusing the Day 4 results view
- [x] Update README (setup incl. API key), final checks, live API demo run
- [x] Browser check of the AI input (done by the user) and commit

**Fallback:** if Day 5 runs short, the app is still complete with the form.

## Day 6 – UI redesign ✅

**Outcome:** a modern, map-first interface: full-screen muted map with
floating panels. Light theme only. Frontend only; no behaviour changes.

- [x] Agree on direction (floating panels, light only, before the old Day 6)
- [x] Install `lucide-react` (icons) and `@fontsource-variable/inter` (font)
- [x] Design tokens in `index.css` (`@theme`): indigo accent, surfaces,
      radii, shadows; muted OpenStreetMap tiles via CSS filter (no new
      tile provider: CARTO now needs an API key, which would be public)
- [x] Shared building blocks in `components/ui/` (Card, Button,
      SegmentedControl, IconButton, Badge)
- [x] Layout: full-screen map, floating left panel (bottom sheet on phones),
      collapsible results card, collapsible legend
- [x] Restyle AI input, scenario form (type as icon tabs), change list,
      results (KPI row + expandable details), chart, map lines and stops
- [x] Keep status colours with icon + label and the validated chart palette
- [x] Type-check, lint, build
- [x] Browser check by the user (desktop and phone width), commit

## Day 7 – Quality and explainability ✅

**Outcome:** every push is checked automatically, users can see *why* a
journey changed, and journey times include the cost of changing buses.

Ordered by risk: each part is committed on its own, so the day can stop
after any of them with a working app.

**1. CI on GitHub Actions** (small)
- [x] Explain the workflow and get approval
- [x] Workflow on push and pull request: backend `pytest`; frontend `npm ci`,
      `tsc`, `oxlint`, `npm run build`
- [x] No secrets needed (AI tests use a fake model)
- [x] Simulated both jobs on a clean checkout locally (95 tests, lint, build)
- [x] Add a status badge to the README; commit
- [x] Push and confirm the first run on GitHub passes (run 43022437316: both jobs green)

**2. Journey explorer** (small–medium)
- [x] Explain the API and UI design and get approval
- [x] Backend: `POST /api/journeys` returns the journey before and after a
      scenario, split into legs (reuses `shortest_journey`)
- [x] Bypass edges remember the closed stops they pass (`route_via`);
      no simulation numbers change (all 95 earlier tests unchanged)
- [x] Tests (23 new, 118 total): legs, closed stops, reasons, unknown stops,
      baseline untouched, and agreement with the simulation for all 240 journeys
- [x] UI: Summary/Journey tabs in the results card, clickable table rows,
      From/To pickers, leg timeline; map draws both paths, A/B pins, zooms in
- [x] Lint, build, live API check
- [x] Browser check by the user, commit

**3. Transfer penalty** (medium; largest change to the engine)
- [x] Agree on the value: 5 min per change, counted in journey times, shown
      separately; backend setting `TRANSFER_PENALTY_MIN` (default 5, 0–60)
- [x] Explain the graph design and get approval
- [x] Route-aware graph (`services/route_graph.py`): stop nodes + one platform
      node per route and stop; board edge = penalty, alight 0, ride = route time
- [x] Closed stops: only the stop node is removed, buses drive through its
      platforms; bypass edges and `route_via` deleted
- [x] Safety net: new engine at penalty 0 reproduced the old engine's full
      output (6 scenarios, 1,440 journey comparisons, 0 differences)
- [x] Tests: 5 structural bypass tests replaced by journey-level equivalents,
      2 journey tests adapted, 13 new penalty tests (131 total)
- [x] Explorer legs read directly from the path; time breakdown shown in the UI
- [x] AI prompt unchanged (it describes physical links)
- [x] Browser check by the user, commit

**Fallback:** the transfer penalty is last because it is the riskiest. If it
runs short, CI and the journey explorer are still complete.

## Days 8–14 – Extensions (all former "maybes")

All ideas collected after the MVP, one phase per day, in a safe order: safety
nets first, then quick wins, then model changes (each with an equivalence
check like the transfer penalty at 0), then new scenario types, AI features
and saving, and the largest, most open-ended items last.

Rules as on Day 7: every part is its own commit and ends with a working app,
so a day can stop after any part. Substantial parts start with "explain the
design and get approval" (CLAUDE.md). Sizes: S ≈ under 1 h, M ≈ half a
session, L ≈ a full session or more. **Total ≈ 9–10 sessions**: Days 10, 11
and 14 are larger than one session and are marked as such.

## Day 8 – Safety nets

**Outcome:** every later change is protected by generated types, frontend tests and an easy start.
**Size:** ≈ 1 session.

**1. Generate TypeScript types from OpenAPI** (S)
- [x] Explain the tool choice and get approval: `openapi-typescript` (types only, no runtime code)
- [x] `python -m app.export_openapi` writes `frontend/openapi.json` from the app object (no server)
- [x] `npm run gen:types` → `src/types/api.gen.ts`; the 5 type files are now aliases,
      no importer changed; type check, lint and build pass
- [x] Generator in its own package `frontend/tools/openapi/` (pins TypeScript 5:
      TypeScript 7 no longer ships the compiler API it needs)
- [x] CI job "API types up to date" (regenerate + `git diff --exit-code`);
      checked locally: deterministic, and a schema change makes it fail
- [x] 2 tests for the export (133 total); README section; commit
- [x] Pushed; first run on GitHub green (run 43248409499: all 3 jobs)

**2. Frontend tests** (M)
- [x] Explain the setup and get approval (Vitest; Playwright for one smoke test)
- [x] Vitest 5.1 (`environment: node`, config in `vite.config.ts`): 32 tests for
      `lib/network.ts` and `lib/impact.ts`; a deliberately broken helper is caught;
      `npm test` in the CI frontend job; commit
- [x] One Playwright end-to-end test (`e2e/close-stop.spec.ts`): load map, close CEN,
      run, compare the KPI tiles with the backend's own answer; a wrong number is caught
- [x] KPI tiles are named groups (`role="group"`), used by the test, no visual change
- [x] CI job "End-to-end (Playwright)": seed, Chromium, report uploaded on failure
- [x] README: test commands, e2e section, header badge text fixed ("Live"); commit
- [x] Pushed; CI green with Playwright starting both servers itself (run 43249884632: all 4 jobs)

**3. One-command start** (S)
- [x] Decide: plain script (no new dependency, hot reload as now; Docker revisited at Day 14)
- [x] `./dev.sh`: checks Python 3.11+/Node 20+ and free ports; creates `.venv`, installs
      packages only when changed, copies `.env.example`, seeds only an empty DB
      (`python -m app.seed --if-empty`, 1 new test), starts both, Ctrl+C stops both
- [x] Tested: normal start (2.5 s, no installs, DB untouched), first run on a fresh copy
      (28 s: venv, packages, `.env`, seed), Ctrl+C stops both, ports freed, no leftovers
- [x] README quick start; commit

## Day 9 – Quick product wins

**Outcome:** three small, visible improvements; the simulation is untouched.
**Size:** ≈ 1 session (light).

**1. Click a stop on the map to fill in the form** (S)
- [x] Design approved: form state lifted to `App` as a pure draft (`lib/changeDraft.ts`);
      line click on "Close stop" switches to "Remove link"
- [x] Stop click: sets Stop, or From then To (next click on a neighbour); line click
      selects the link and fills in its current time; ignored while running
- [x] Selection ringed in indigo in its own Leaflet pane below the lines (a later-added
      shape would otherwise cover them); hint text in the form; "Click to select" tooltips
- [x] Tests: 19 Vitest (51 total), Playwright `e2e/map-select.spec.ts` (2 e2e total)
- [x] Browser check by the user, commit

**2. Shareable link** (S)
- [x] Design approved: readable `?s=close:CEN~remove:MKT-UNI~time:RIV-EST:9:oneway`;
      no auto-run on open; address bar kept in sync (`replaceState`)
- [x] `lib/shareLink.ts`: encode/decode, stop ids escaped, all-or-nothing validation
      with the form's rules (stops, links, 0 < time ≤ 600, ≤ 20 changes)
- [x] Notice above the list (loaded / could not be opened); "Copy link" button
- [x] Tests: 14 Vitest (65 total), 2 Playwright (4 e2e total)
- [x] Browser check by the user, commit

**3. CSV export of changed journeys** (S)
- [x] Outline approved: all changed journeys, table order, 8 columns, commas (standard
      CSV), UTF-8 BOM, file named after the share code (timestamp if long)
- [x] `lib/exportCsv.ts` (RFC 4180 quoting, CRLF); "CSV" button in the results header;
      table sort order moved to `lib/impact.ts` so table and file agree
- [x] Tests: 8 Vitest (73 total), Playwright compares every row with the API (5 e2e total)
- [x] Commit (approved by the user; no separate browser check reported)

## Day 10 – More realistic simulation

**Outcome:** waiting from frequencies, demand weighting and walking, each with an equivalence check.
**Size:** ≈ 2 sessions – will overrun.

Each part keeps the earlier behaviour reproducible with a setting (like the
transfer penalty at 0) and checks equivalence before changing defaults.

**1. Waiting time from route frequencies** (L)
- [x] Decided: invented headways R1 10, R2 10, R3 15, R4 20 min; wait = half the
      headway at EVERY boarding; penalty default 5 → 2 min (inconvenience only);
      waiting on by default (`INCLUDE_WAITING`)
- [x] Model approved: board edge = penalty + wait; journey = path − one penalty
- [x] `routes.headway_min` (model, seed, API); outdated tables rebuilt by `app.seed`
      (also `--if-empty`); startup logs an error for an outdated database
- [x] Equivalence: waiting off vs the pre-Day-10 engine (git worktree), penalties 0
      and 5, 7 scenarios: 3,374 results (14 simulations, 3,360 explorer journeys),
      **0 differences**; with waiting on all 3,374 differ (the check can fail)
- [x] Explorer: `wait_min` per plan and per leg; UI shows "Wait about 5.0 min for R1
      (a bus every 10 min)"; results note describes the model; legend shows headways
- [x] Tests: 17 new backend (152 total), agreement test also runs with waiting; 1 Vitest
- [x] Part 1a commit (approved by the user; no separate browser check reported)
- [x] Part 1b: `change_frequency { route_id, headway_min 1–120 }`: schema, engine
      (`set_headway` updates the route's board edges in the scenario graph), unknown
      route → "Change N (change_frequency): unknown route", AI schema + prompt (routes
      with headways; "twice as often" / "12 buses an hour" → absolute headway);
      frontend keeps working: union derived from the generated `Scenario`, change text,
      icon, share-link code `freq:R3:7.5`; 16 backend tests (168), 3 Vitest (76)
- [ ] Part 1c: frontend for it (form tab, share link `freq:R1:5`, e2e), commit

**2. Passenger demand weighting** (M)
- [ ] Decide the demand model (e.g. invented stop weights, labelled as an
      assumption) and get approval; must not look like real data
- [ ] Weighted metrics next to the current unweighted ones (equal weights =
      today's numbers)
- [ ] Tests, UI labelling, commit

**3. Walking to a nearby stop** (M)
- [ ] Decide walking speed and maximum distance; get approval
- [ ] Walking edges between nearby stops (distance from coordinates); used
      only where it helps (e.g. when a stop is closed)
- [ ] Equivalence check with walking off, tests, explorer shows walking legs, commit

**Fallback:** parts 2 and 3 are independent of each other; either can move to a later day.

## Day 11 – New scenario types

**Outcome:** users can add connections, stops and routes, not only remove or slow them.
**Size:** ≈ 2 sessions – will overrun.

**1. Add a connection** (M)
- [ ] Schema, engine (new ride edges), validation, form, AI prompt, tests, commit

**2. Add a stop** (M)
- [ ] Position on the map (click), connect to a route; schema, engine, form,
      AI prompt, tests, commit

**3. Add a route** (L)
- [ ] Draw a sequence of stops with times; schema, engine, form/map editor,
      AI prompt, tests, commit

**Fallback:** "add a route" (part 3) is the largest; parts 1–2 stand on their own.

## Day 12 – AI features

**Outcome:** the AI knows the current changes and can summarise results without inventing numbers.
**Size:** ≈ 1 session.

**1. AI aware of the current change list** (S)
- [ ] Send the current list with the request; support "undo the last one",
      "and also …"; tests with the fake model; commit

**2. AI summary of results** (M)
- [ ] Explain the safeguard and get approval: the AI may only rephrase
      computed numbers; every number in its text is checked against the
      results, otherwise the summary is rejected
- [ ] Endpoint, tests (including a fake model that invents a number), UI, commit

## Day 13 – Saving and comparing

**Outcome:** scenarios can be saved and compared side by side.
**Size:** ≈ 1 session.

**1. Save and compare scenarios** (L)
- [ ] Explain the data model and get approval (SQLAlchemy tables for saved
      scenarios; results are recomputed, never stored as truth)
- [ ] Save, list, delete; compare two scenarios side by side
- [ ] Tests, UI, commit

## Day 14 – Deployment and real data

**Outcome:** the app is ready to be public, and it can simulate a real city.
**Size:** ≥ 2 sessions – open-ended.

**1. Deployment hardening** (M) – only if the app will be public
- [ ] Decide the hosting target
- [ ] Rate-limit the AI endpoint, production map tiles, authentication
- [ ] Commit

**2. Real city data (GTFS import)** (L, possibly several sessions)
- [ ] Choose a city and feed; check its licence
- [ ] Import stops, routes, travel times (and frequencies, if Day 10 part 1 is done)
- [ ] Performance: all-pairs journeys will not scale to thousands of stops
      (sampling, caching or limiting journeys); decide and get approval
- [ ] Tests on a small extract; commit

**Fallback:** both parts are optional; part 1 is only needed if the app goes public, and
part 2 can stop after a small extract of the city works.

---

## Open issues

- [ ] Starlette deprecation warning in tests: `httpx` → `httpx2`
      (verify `httpx2` is the official successor before switching)
- [ ] Production bundle is ~836 kB (Leaflet + Recharts); Vite warns at 500 kB.
      Fine for the MVP; code-split the chart if it matters later
- [ ] Routes sharing a street (R1/R4 on MKT–CEN) draw on top of each other;
      the tooltip names the route under the cursor only
- [x] Pushing workflow files needs the `workflow` scope on the GitHub token
      (fixed once with `gh auth refresh -h github.com -s workflow`)
- [ ] `fsevents` install script not approved by npm (optional; only needed
      if hot reload stops working: `npm install-scripts approve fsevents`)

## Possible future improvements

All former "maybes" are now scheduled as Days 8–14. New ideas go here.

## Decisions still needed

- [x] **Day 5:** AI provider and API key: Groq, `openai/gpt-oss-120b`
- [ ] **Days 8–14:** decisions asked when each part starts: type generator
      (Day 8.1 ✅ openapi-typescript), Docker vs script (8.3 ✅ script), bus frequencies (10.1 ✅), demand model
      (10.2), walking speed/distance (10.3), hosting target (14.1), GTFS city
      and licence (14.2)
- [x] **Day 7:** transfer penalty value: 5 min per change of bus, counted in journey
      times and shown separately; backend setting `TRANSFER_PENALTY_MIN` (default 5)

## Session log

| Date       | Day | Summary                                                     |
| ---------- | --- | ----------------------------------------------------------- |
| 2026-11-10 | 1   | Environment checked, skeletons built, committed and pushed  |
| 2026-11-11 | 2   | DB models, seed (16 stops, 4 routes), graph + shortest journey, network API; 25 tests |
| 2026-11-11 | 3   | Scenario schema, simulation engine (bypass on stop closure), metrics, `POST /api/simulations`; 63 tests |
| 2026-11-11 | 4   | Map, legend, scenario form, results panel and chart; lint + build pass; browser-checked |
| 2026-11-11 | 5   | Groq AI layer (strict JSON, 3-step validation), AI input in UI; 95 tests; live API + browser check passed |
| 2026-11-11 | 6   | UI redesign: floating panels over a muted full-screen map, design tokens, icon tabs, KPI results; browser-checked |
| 2026-11-11 | 7   | CI (green on GitHub); journey explorer API + UI, 118 tests; browser-checked |
| 2026-11-11 | 7   | Transfer penalty: route-aware graph, 5 min/change; penalty-0 equivalence (0 diffs); 131 tests; browser-checked |
| 2026-11-12 | 8   | Types generated from OpenAPI (openapi-typescript, isolated TS 5), CI drift check; 133 tests |
| 2026-11-12 | 8   | Frontend tests: Vitest (32, lib helpers), Playwright e2e vs real backend; both in CI |
| 2026-11-12 | 8   | `./dev.sh` one-command start, `app.seed --if-empty`; 134 tests; Day 8 done |
| 2026-11-12 | 9   | Map clicks fill in the form (draft lifted to `App`, selection pane); 51 Vitest, 2 e2e; browser-checked |
| 2026-11-12 | 9   | Shareable link (`?s=`, readable, all-or-nothing, synced URL, Copy link); 65 Vitest, 4 e2e; browser-checked |
| 2026-11-12 | 9   | CSV export of changed journeys (backend values, table order); 73 Vitest, 5 e2e; Day 9 done |
| 2026-11-12 | 10  | Waiting = half the headway at every boarding, penalty 5 → 2; waiting-off equivalence 0 diffs (3,374 results); 152 tests |
| 2026-11-12 | 10  | Scenario type `change_frequency` (engine, validation, AI prompt, share link); 168 backend, 76 Vitest |
