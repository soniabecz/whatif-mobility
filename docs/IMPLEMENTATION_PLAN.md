# WhatIf Mobility – Implementation Plan

> **Read this file at the start of every session.**
> Update the checklists and the "Current status" section at the end of
> every session. Project rules and conventions are in `CLAUDE.md`.

## Current status

- **Last completed:** Day 14.2 step B4 (map and UI at scale: legend scroll + filter,
  small stops when zoomed out; no canvas needed); 377 backend + 131 Vitest + 20 e2e tests.
  Step B (full network) is complete and committed
- **Last completed:** Day 14.3 walking between stops (steps A and B committed): walking
  is part of the route graph and on between open stops by default; 386 backend +
  135 Vitest + 20 e2e tests
- **Next up:** open choices: direction-aware platforms (fixes the known limit of a bus
  turning round without a change), simulation speed on the full network (2 s), or
  Day 14.1 deployment The full network is in backend/gdansk-all.db
  (re-import: `WHATIF_DATABASE=gdansk-all.db python -m app.import_gtfs --modes all`)
- **Local e2e:** Playwright reuses a running app on port 8000; if it serves Gdańsk the run
  stops with a message: stop that app (or run it on whatif.db) before `npm run test:e2e`
- **Real city:** `WHATIF_DATABASE=gdansk.db python -m app.import_gtfs`, then
  `WHATIF_DATABASE=gdansk.db ./dev.sh` (see README "Real city data")
- **How to start:** `./dev.sh` (app on http://localhost:5173); after pulling, it
  rebuilds outdated database tables automatically
- **Working pattern used so far:** each part = design proposal → approval → build
  with tests and screenshots → user says "commit and push" → CI watched; model
  changes get an equivalence check against the previous commit (git worktree)
- **Repository:** https://github.com/soniabecz/whatif-mobility (private, branch `main`)

## Timeline

Total: **13 working days done** (MVP in Days 1–5, Days 6–10 added afterwards);
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
| 10  | More realistic simulation | ✅ Done |
| 11  | New scenario types        | ✅ Done |
| 12  | AI features               | ✅ Done |
| 13  | Saving and comparing      | ✅ Done |
| 14  | Deployment and real data  | 🟡 In progress |

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
| Added connections belong to an existing route that already serves one of the stops | Extensions and shortcuts only; new lines come with "add a route" (Day 11.3) |
| Travel time of an added link always entered by the user (form and AI) | A suggested time would be an invented number |
| New stop = inserted into one route between consecutive stops; user gives both times | Expresses "the line stops here now"; nothing guessed |
| Journeys to/from new stops reported separately (`new_stops`), not compared | They have no "before"; keeps the 240-journey comparison clean |
| The AI does not add stops | It would have to invent coordinates |
| Journeys impossible in the baseline but possible after: `newly_possible`, not "changed" | No "before" time to compare; kept out of averages, counted and weighted separately |
| Walking only to/from closed stops, computed on top of the graph (not walk edges) | Graph and penalty rule untouched; walk-only paths would break "path − one penalty" |
| Walking distance = straight line × 1.3, 5 km/h, max 1,000 m (settings) | Invented but common planning values; reaches grid neighbours, not diagonals |
| Journeys to/from closed stops compared when walking is on | They are real trips that get slower, not trips that vanish |
| Demand = invented stop activity 1–3, journey weight = origin × destination | Simple gravity model without distance (times change with the scenario); clearly labelled |
| Weighted figures only as shares (%) and averages, next to the unweighted counts | Absolute passenger numbers from invented demand would be fake metrics |
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
- [x] Part 1c: "Frequency" form tab (route + minutes, current headway filled in);
      clicking a line on that tab selects its route (whole route haloed); legend shows
      "every ~~15~~ 7.5 min"; 6 Vitest (82), Playwright `e2e/frequency.spec.ts` (6 e2e)
- [x] Commit (approved by the user; no separate browser check reported)

**2. Passenger demand weighting** (M)
- [x] Decided: invented stop activity 1–3 (major: CEN, MKT, UNI; quiet: NTH, WST,
      LIB, RIV, EST, MUS; others medium); journey weight = origin × destination,
      no distance decay; only shares (%) and averages, never passenger numbers
- [x] `stops.activity` (model, seed, API; outdated table rebuilt); `summary.demand_weighted`
      (unchanged/slower/faster/impossible/closed %, weighted averages)
- [x] Equal levels reproduce the unweighted figures (4 scenarios × 2 models, tested);
      hand-calculated cases; shares add up to 100
- [x] UI: "11.8% of trips" under each count, weighted average and closed-stop share in
      Details with an "invented, not real passenger data" note; stop tooltip shows activity
- [x] Tests: 19 backend (187), 1 Vitest (83); e2e checks one share per tile against the API
- [x] Commit (approved by the user; no separate browser check reported)

**3. Walking to a nearby stop** (M)
- [x] Decided: scope A (only journeys to/from a CLOSED stop walk; no walk edges in the
      graph); 5 km/h, straight line × 1.3, max 1,000 m; such journeys are compared
      (slower/impossible) instead of excluded; `WALKING_ENABLED` on by default
- [x] `services/walking.py`: distances, nearby open stops, `best_walk_option` (shared by
      simulation and explorer, deterministic tie-break); summary `walked_to_or_from_closed_stop`
- [x] Equivalence: walking off vs the previous engine (worktree), 3 model settings ×
      6 scenarios: 4,338 results, **0 differences**; walking on: 549 differ, none in the
      scenario without a closed stop
- [x] Explorer: `walk_start`/`walk_end`, `walk_min`; UI walking rows and breakdown, dashed
      walking line on the map, legend entry, Details row
- [x] Tests: 16 backend (203), Playwright `e2e/walking.spec.ts` (7 e2e)
- [x] Commit (approved by the user; no separate browser check reported)

**Fallback:** parts 2 and 3 are independent of each other; either can move to a later day.

## Day 11 – New scenario types ✅

**Outcome:** users can add connections, stops and routes, not only remove or slow them.
**Size:** ≈ 2 sessions – will overrun.

**1. Add a connection** (M)
- [x] Design approved: link on an EXISTING route; one stop must already be on it;
      the user always gives the travel time (no invented speed)
- [x] Part 1a: `add_connection` schema (different stops), engine (`add_ride`/`add_platform`
      refactor; new platform waits with the route's headway), validation before any
      change (unknown/closed stop, unknown route, neither stop on the route, link exists);
      AI schema + prompt (routes list their stops; "never guess the time")
- [x] Found and fixed: a baseline-impossible journey can now become possible →
      `newly_possible` count and share, explorer status "new" (was silently "unchanged")
- [x] Refactor check: previous engine vs new, full model, 4,338 results, 0 differences
- [x] Frontend display support (icon, text, share code `add:R2:EST-TEC:5`, shared rule
      `addedConnectionProblem`); 18 backend tests (221), 4 Vitest (87)
- [x] Part 1b: "Add link" tab (route, any two stops, required time with straight-line
      distance hint, both directions; reasons from the shared rule); clicks: two stops,
      a line picks the route; dashed indigo preview; added links dashed in the route
      colour (own pane below stops); legend entry; 5 Vitest (92), 3 Playwright (10 e2e)
- [x] Bug found by the new e2e test (present since Day 4): number inputs with
      `min 0.1, step 0.5` made the browser silently refuse whole minutes on the
      Travel time tab (3, 5, 7.5 were not added). Fixed with `step="any"` (also the
      headway input); regression test `e2e/travel-time.spec.ts`
- [x] Commit (approved by the user; no separate browser check reported)

**2. Add a stop** (M)
- [x] Design approved: insert into ONE route between two consecutive stops; user gives
      both times; AI does not add stops (points to the form); new-stop journeys reported
      separately; no demand level for new stops
- [x] Part 2a: `add_stop` schema + engine (direct links replaced via the new stop, both
      directions where the route runs them; validated first: id/name unused, direct link,
      route); `summary.new_stops`; explorer accepts new stops (status "new"); walking from
      closed stops may use new stops (`stop_places`); AI prompt rule
- [x] Existing scenarios unchanged: previous engine vs new, 4,338 results, 0 differences
- [x] Frontend display support: text, icon, Details row, share code `stop:N1:…`; shared
      links may refer to an earlier new stop (`withAddedStop`); 19 backend (240), 5 Vitest (97)
- [x] Part 2b: "Add stop" tab (map click places it, a line click also picks route and
      link; name with automatic id N1…; route + its links; both times with today's time
      as a hint); preview marker; new stops drawn with a route-coloured ring and dashed
      links; legend; the form, list and explorer use the network with added stops
- [x] Fixed while testing: one click on a line fired two handlers that both started from
      the same stale draft (the second overwrote the first): functional state updates;
      switching to "Add stop" now snaps to a real link; >4 tabs shown in two rows
- [x] Tests: 6 Vitest (103), Playwright `e2e/add-stop.spec.ts` (11 e2e)
- [x] Commit (approved by the user; no separate browser check reported)

**3. Add a route** (L)
- [x] Design approved: `add_route` = id, name, colour (display only, fixed palette of 6),
      headway (required, never guessed), 2–30 different stops in order with one time per
      stretch (a loop has one more, back to the first stop), `is_loop`, `both_directions`
      (default true); may use stops added earlier; later changes may refer to the new route;
      no "must touch the network" rule (every stop is already in the network);
      AI allowed only when stops, every time and the headway are given (it picks id/colour)
- [x] Part 3a: schema (`AddRoute`, `stretches()`, `MAX_ROUTE_STOPS`, `NEW_ROUTE_COLORS`),
      engine `_add_route` (validated first: id/name unused, stops open; headway registered
      before the rides so waits are right; route names kept in the route graph); network
      graph keeps `route_colors`; AI schema + prompt (next free id, free palette colours,
      ask only for missing stops/times/headway); 28 backend tests (268)
- [x] Existing scenarios unchanged: previous engine vs new, 186 simulations (62 scenarios ×
      3 settings), 5,738 changed journeys, byte-identical
- [x] Frontend display support: text, icon, share code `route:R5:Name:7c3aed:12:OLD-MKT-RIV:3-4`
      (`:loop`, `:oneway`), shared rule `addedRouteProblem`, `withAddedRoute`,
      `applyAddedStops` → `applyAddedChanges` (form, list, explorer know new routes);
      8 Vitest (111); 11 e2e still pass
- [x] Live AI check (Groq): route built from an English and a Polish (loop) request;
      a request without times is refused (its message still asks for a name, which the
      AI could choose itself: harmless)
- [x] Commit 3a (approved by the user; CI green)
- [x] Part 3b: "Add route" tab (7th tab): name with automatic id R5…, palette swatches
      (colours in use disabled; automatic = first free), required headway, stops in order
      by map clicks or "Add a stop…", a time per stretch with the straight-line hint,
      "Remove last", loop switch (also: click the first stop again with 3+ stops), both
      directions; the next route starts empty after adding. Dashed preview in the chosen
      colour; new routes drawn dashed in their colour and clickable (Frequency, Add link,
      Add stop can pick them); the map's route lookup includes new routes (journey legs
      coloured); legend lists the scenario's routes with a "new" tag (legend 16 px wider)
- [x] Small refactors: `ui/Switch` (shared by the toggles), `inputBaseClass` in `ui/Field`;
      `draftSelection` takes the network (for the automatic colour)
- [x] Tests: 9 Vitest (120), Playwright `e2e/add-route.spec.ts` (2 tests, 13 e2e);
      screenshots checked (desktop drawing, loop preview, legend, explorer leg on R5; phone)
- [x] Commit 3b (approved by the user; CI green)

**Fallback:** "add a route" (part 3) is the largest; parts 1–2 stand on their own.

## Day 12 – AI features ✅

**Outcome:** the AI knows the current changes and can summarise results without inventing numbers.
**Size:** ≈ 1 session.

**1. AI aware of the current change list** (S)
- [x] Design approved: the request sends `current_changes`; the AI answers with
      operations, never a rewritten list: `remove_numbers`, `replace` ({number, change},
      in place: later changes may depend on it), `changes` (appended). The backend checks
      the current list (422 if it does not fit), the numbers (exist, used once), ≤ 20 and
      dry-runs the complete new list; the response is the full new list plus
      removed / replaced / added. Applied directly, with a one-level Undo
- [x] Prompt: numbered CURRENT CHANGES in plain words (new stops and routes with their
      stops), next free route id and colours count routes in the list, relative requests
      start from a value already in the list and replace that change
- [x] Frontend: sends the list; feedback "Removed 1 · changed 1 · added 2" + AI message;
      Undo while the list is still exactly the AI's result; an answer for a list edited
      meanwhile is not applied (`lib/aiEdit.ts`)
- [x] Tests: 20 backend (288) incl. a dependency broken by a removal, 3 Vitest (123),
      e2e `ai-edit.spec.ts` with the AI endpoint answered by the test (16 e2e)
- [x] Live AI check (Groq): undo last, and also, replace in place, "3 min slower still"
      from the listed 9 min → 12, new route's headway edited in place, unknown number refused
- [x] Commit (approved by the user)

**2. AI summary of results** (M)
- [x] Safeguard approved (stronger than first planned): the AI never writes a number.
      It gets a fact sheet (computed values with placeholder names) and writes
      "{slower} journeys get slower"; the backend rejects any digit (outside ids like
      R5/N1), unknown placeholder, number word ("two") or ratio word ("twice", "half"),
      retries once with the problems named, then withholds the summary; accepted text
      gets the values inserted by the backend. Limit (shown in the UI caption): it
      proves every number comes from the results, not that each is used correctly
- [x] `POST /api/ai/summary {changes}`: the backend simulates itself (never trusts
      browser results); `services/summary_service.py` (facts, prompt, check, fill);
      on-demand "Summarise with AI" in the Summary tab; a summary belongs to one result
- [x] Tests: 19 backend (307) incl. fake models that invent a number / use "twice",
      retry then ok, withheld after two; e2e `ai-summary.spec.ts` (18 e2e)
- [x] Live AI check (Groq), 5 scenarios: all accepted on the first attempt; every
      stop figure verified against the result. Prompt tightened after the first run
      (no "about" before exact values, no bracketed repeats, at most 3 stops). Remaining:
      wording can still link figures loosely ("which means"); one transient provider
      error in a burst of calls (not reproduced; the UI offers "Try again")
- [x] Commit (approved by the user)

## Day 13 – Saving and comparing ✅

**Outcome:** scenarios can be saved and compared side by side.
**Size:** ≈ 1 session.

**1. Save and compare scenarios** (L)
- [x] Data model approved: one table `saved_scenarios` (id, unique name, `changes_json`
      in the scenario format, created/updated in UTC); only changes are stored, never
      results; validated on write and checked against the CURRENT network on every read
      (`fits` / `problem`; not loadable if it no longer fits). No owners yet (Day 14)
- [x] Part 13a backend: `models/scenario.py`, `schemas/saved_scenario.py`,
      `services/scenario_store.py`, `services/comparison_service.py`, `api/scenarios.py`
      (list / save 201 / get / put / delete 204; 409 name taken, 422 does not fit, 404),
      `api/comparisons.py` (both simulated here; journey counts A vs B, top 10 differences,
      only-in-one first). `simulate` core extracted to `scenario_state` (shared with the
      comparison): 186 simulations / 5,738 journeys byte-identical to the previous commit
- [x] Saved data protected: `python -m app.seed` now rebuilds only outdated NETWORK tables
      and stops (instead of dropping) if `saved_scenarios` is outdated
- [x] Tests: 20 backend (327) incl. the network changing after saving, an unreadable
      stored list, comparison times = each scenario's own simulation, seed keeps saves
- [x] Part 13b UI: "Save" next to Copy link (inline name; a taken name offers
      Overwrite), "Saved scenarios" section (load → notice, two-step delete, rows that no
      longer fit show why and cannot be loaded), A/B pickers with "Current list",
      comparison card in the results card's place (phone: top of the sheet, scrolled
      into view). Columns A | B with each side's own "was" average instead of a shared
      Baseline column (each side's average covers different journeys); better side
      highlighted (`lib/comparison.ts`); journey-by-journey counts; largest differences
      (A − B, positive = longer in A). A comparison using the current list closes when
      the list is edited
- [x] Tests: 5 Vitest (128), e2e `saved-scenarios.spec.ts` (2 tests, 20 e2e; they delete
      what they save); screenshots checked (desktop, card, phone)
- [x] Commit 13a (approved by the user)
- [x] Commit 13b (approved by the user)

## Day 14 – Deployment and real data

**Outcome:** the app is ready to be public, and it can simulate a real city.
**Size:** ≥ 2 sessions – open-ended.

**1. Deployment hardening** (M) – only if the app will be public
- [ ] Skipped for now (user, 2026-11-13); decide the hosting target when it is needed
- [ ] Rate-limit the AI endpoint, production map tiles, authentication
- [ ] Commit

**2. Real city data (GTFS import)** (L, possibly several sessions)
- [x] City and feed: ZTM Gdańsk GTFS (ckan.multimediagdansk.pl, republished daily).
      Licence: Creative Commons Attribution + "Regulamin" (terms): free reuse; name the
      publisher (Zarząd Transportu Miejskiego w Gdańsku, http://www.ztm.gda.pl/otwarty_ztm)
      and the creation and download dates; keeping the data current is the user's duty.
      (Mobility Database lists CC0; the publisher's own statement wins.)
- [x] Measured: 1,624 stop posts → 760 stations; 93 lines (83 bus, 10 tram). Trams:
      ~125 stations, 15,000 journeys, 0.4 s per simulation. All: ~740 stations,
      550,000 journeys, ~16 s+ per simulation (too slow; huge results; AI prompt too big)
- [x] Approved: step A = trams (importer also supports buses/all); step B (full network
      performance) later, only if wanted. Stations = posts grouped by name (≥ 500 m apart
      → separate); equal demand (no invented proxy); separate database file
      (`WHATIF_DATABASE`, e.g. gdansk.db), the sample stays in whatif.db for tests
- [x] Step A: `services/gtfs_import.py` + `python -m app.import_gtfs` (download to
      backend/data/gtfs, git-ignored): reference weekday (next Wednesday), main station
      sequence per line and direction, median link times (≥ 0.5 min), peak headways,
      calls without boarding/alighting driven through (depot gates; found on the real
      feed), distinct line colours; `network_source` table (attribution, dates, method),
      `GET /api/network` → `source`; seed/rebuild keep saved scenarios
- [x] UI: credit on the map's attribution line and in the legend (dates, licence, "How
      the network was built"); texts no longer say "invented" for a real feed; natural
      line order (T2 before T10); AI example from a real link
- [x] AI: compact line-by-line network description above 8,000 chars (Gdańsk prompt
      19k → 11.8k chars; Groq free tier: 8,000 tokens per minute, was HTTP 413); summary
      facts say "no passenger data" instead of "invented demand" for equal levels
- [x] Tests: 19 backend (346) on a hand-made feed; 3 Vitest (131); 20 e2e unchanged.
      Live: import 122 stations / 10 lines / 635 links; closing Politechnika SKM in the
      app; AI in English and Polish (close stop, tram 8 every 5 min), AI summary
- [ ] Known limits: a relative change of a link whose directions differ ("A -2/3- B")
      still becomes one both-ways time (prompt rule not followed); ~20 % of T2/T3/T8 trips
      use alternative routings that are left out; one AI request per minute on the free tier
- [x] Commit step A (approved by the user)
- [x] Step B approved (2026-11-13): SciPy dependency; cap returned changed journeys at
      1,000 with the full list as a backend CSV; AI pre-selects stations/lines for big networks
- [x] Measured full network (714 stations, 93 lines, 4,141 links, 509,082 journeys):
      15–18 s per simulation (90 % NetworkX Dijkstra, pure Python), compare 56 s, results
      5–7 MB (40–53k changed journeys), AI prompt 55k chars
- [x] B1 engine: `travel_time_matrix` (SciPy compiled Dijkstra, checked identical to
      NetworkX; zero weights kept); vectorised `simulate_state` with order-preserving sums
      (`_ordered_sum`, so results are byte-identical, not just close); baseline times cached
      per network + settings; comparison reuses its states; nearby walks computed once per
      closed stop. Equivalence vs previous commit: sample 186 simulations, Gdańsk trams 376
      simulations (220,717 changed journeys), 36 comparisons: all 0 differences.
      Full network: ~1.0 s per simulation (was 15–18 s), compare 2.2 s (was 56 s).
      7 tests (353). Committed (approved by the user)
- [x] B2 response size: `changed_journeys` = the 1,000 largest in table order (impossible
      first, then largest change) + the chart's 10 largest still possible, listed by
      (origin, destination); `changed_journeys_total`; all figures still use every journey.
      CSV written by the backend (`POST /api/simulations/csv`, every journey, same format;
      the browser adds the BOM and file name). Table shows the first 1,000 with "the CSV
      has all N". Full network: response 5.1 MB → 205 kB (1.1 s); CSV 39,534 rows in 1.5 s.
      5 backend tests (358; the 5 CSV-writer Vitest tests moved there, 126 Vitest)
- [x] e2e guard (`e2e/global-setup.ts`): locally Playwright reuses a running app; if it
      serves another network (WHATIF_DATABASE=gdansk.db) the run stops with one clear message
- [x] Commit B2 (approved by the user; e2e not run locally: the dev server served Gdańsk)
- [x] B3 AI on big networks: above 12,000 chars of line text the prompt gets an EXCERPT
      (`services/network_excerpt.py`, also home of the line chains): stations named in the
      request (no diacritics, "ł" → "l"; word stems: ≥ 4 letters shared, ≤ 3 differing at
      the end: Bramie/Brama, Dworca/Dworzec; request words like przystanek/stop/linia
      ignored), lines named by number (not "10 minut"), stops and lines of the change list;
      lines through those stations ±3 stops ("..." = continues), named lines in full; all
      routes with headways in one line. Too many matches → AI asks. Full network prompt
      55k → 6–11k chars; trams prompt byte-identical. 19 tests (377)
- [x] Live (Groq, full network): "przy Bramie Wyżynnej" → close S1028; "autobus 199 co 10
      minut" → B199 every 10; "close the stop" → asks which; "3 minutes slower" on a 2/1-min
      link → two one-way changes 5 and 4 (the step-A limit did not recur here); AI summary OK
- [x] Commit B3 (approved by the user)
- [x] B4 measured (headless Chromium, full network vs trams): 5,781 SVG shapes vs 803; load
      2.1 s vs 0.84 s (one ~1 s task at start); zoom ~200 ms and stop click ~80 ms on both;
      panning no worse. **No canvas renderer**: speed was fine, the problems were visual
- [x] Legend: line list scrolls inside a height-capped card (credit and explanations stay
      visible); above 20 lines a "Filter N lines" box (id or name, `filterRoutes`)
- [x] Stops: on networks with > 200 stops, below zoom 14 plain stops are radius 3 and
      coloured result stops radius 5 (a run colours nearly every stop); closed stops stay 9
      (`compactStops`, `stopMarkerSize`). The zoom watcher reports only threshold crossings
      (setting unchanged state re-rendered all 5,781 shapes: zoom 56 → 190 ms, fixed)
- [x] Live (full network): run 2.9 s in the browser, journey explorer, save + compare
      (3.7 s), AI request; no console errors. 5 Vitest (131); e2e 20 on the sample
- [x] Commit B4 (approved by the user)

**3. Walking between stops** (L, ≈ 1 session) – the former open issue
- [x] Measured: walking (5 km/h, ×1.3) beats the bus for 93 % of stop pairs within 1 km on
      the full network; allowing a walk at the start or end makes 62 % of journeys faster
      (average 74.6 → 67.3 min; trams 35 %, sample 44 %)
- [x] Design approved (2026-11-14): walking becomes part of the route graph (one search);
      walks at the start, between buses (≤ 500 m, a change of bus) and at the end (≤ 1 km),
      never two in a row; walking the whole way counts; default on, setting to switch off
- [x] Step A: `walking.add_walking_layer` adds per stop start / walked / off / end /
      transfer nodes; `journey_time_matrix` and `fastest_journey` replace the closed-stop
      search (`best_walk_option`, `nearby_open_stops` removed); the explorer reads walks from
      the path; baseline cache keyed by the walking model. `between_open_stops` off =
      the Day 10 rule. Found and fixed during the check: boarding and getting off at once
      chained two walks (walks after a bus now start from "off" nodes, reached only by riding)
- [x] Equivalence vs previous commit (walking on, between open stops off): trams 61
      simulations and full network 13 (53,628 changed journeys, 192 explorer journeys):
      0 differences. Sample 28 simulations: 1 journey pair differs (SCH↔STH with both
      closed: 35.3 → 33.4 min), see the known limit below. Full network: simulation
      0.94 → 1.11 s, compare 2.11 → 2.38 s. 3 new tests (380); e2e 20 unchanged
- [ ] Known limit: a two-way line shares its platforms in both directions, so a ride can
      go out and back to the stop where it started (no change of bus), which joins two
      walks. The old search forbade it; the graph cannot without a copy per boarding stop.
      Measured: 0 fastest journeys in the step-A setting on trams and the full network; with
      walking between open stops 39 of 509,082 (0.008 %) on the full network. Proper fix
      later: direction-aware platforms (a turn-round = a change of bus)
- [x] Commit step A (approved by the user)
- [x] Step B: settings `WALK_BETWEEN_OPEN_STOPS` (default true) and `MAX_TRANSFER_WALK_M`
      (500); `JourneyPlan.walks` (ordered, `before_leg`) replaces `walk_start`/`walk_end`;
      `SimulationSummary.walking` (the settings used). UI: explorer shows walks between
      buses in order (`lib/journeyPlan.ts`), the time-model text names the walking rule
      (results and explorer, which now uses the result's settings instead of guessing),
      legend "Walking", map draws every walk. README and .env.example updated
- [x] Effect (baseline): journeys faster with walking: sample 44 % (avg 21.6 → 20.4 min),
      trams 33 % (34.5 → 32.4; 829 newly possible), full network 70.8 % (74.6 → 66.2; 713
      newly possible). Closing a stop no longer makes journeys "faster": CEN 6 → 0,
      Politechnika SKM (trams) 68 → 0, Brama Wyżynna (full) 301 → 0
- [x] Tests: 6 new step-B tests (open-stop walk, walk between buses = a change, the 500 m
      limit, never two walks in a row, baseline and scenario walk alike, a new stop as a
      place to walk to); tests about the Day 10 rule now say `between_open_stops=False`;
      4 Vitest (135); e2e walking test reads `walks`. 386 backend, 20 e2e
- [x] Live (full network): close Brama Wyżynna → 71,235 slower, 0 faster; explorer
      Pruszcz Gdański Nałkowskiej → Urząd Miejski: B507, walk 330 m, change, BM32, walk
      990 m; no console errors. Warm API: simulation 1.1 → 2.0 s (bigger graph, and 71k
      instead of 39k changed journeys to list), compare 2.2 → 3.4 s, journey 0.7 s
- [x] Commit step B (approved by the user)

**Fallback:** all parts are optional; part 1 is only needed if the app goes public,
part 2 can stop after a small extract of the city works, and part 3 can stop after step A.

---

## Open issues

- [ ] Walking only to/from CLOSED stops: on a real city two open stops 300 m apart can
      need a 36-min bus detour, so closing one makes nearby journeys "faster" (walk 3 min).
      → being solved in Day 14 part 3 (walking between stops)

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
      (10.2 ✅ activity 1–3), walking speed/distance (10.3 ✅ 5 km/h, ×1.3, 1 km), hosting target (14.1), GTFS city
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
| 2026-11-12 | 10  | "Frequency" form tab, route halo, legend headways; 82 Vitest, 6 e2e; Day 10 part 1 done |
| 2026-11-12 | 10  | Demand weighting (invented activity 1–3, shares only; equal levels = unweighted); 187 backend, 83 Vitest |
| 2026-11-12 | 10  | Walking to/from closed stops (5 km/h, ×1.3, ≤1 km); walking-off equivalence 0 diffs (4,338); 203 backend, 7 e2e; Day 10 done |
| 2026-11-12 | 11  | Scenario type `add_connection` (backend, AI, share link); `newly_possible` fix; refactor 0 diffs; 221 backend, 87 Vitest |
| 2026-11-12 | 11  | "Add link" tab, map preview and dashed added links; fixed Day 4 bug (Travel time input refused whole minutes); 92 Vitest, 10 e2e |
| 2026-11-12 | 11  | Scenario type `add_stop` (insert into a route; new-stop journeys reported separately; 0 diffs); 240 backend, 97 Vitest |
| 2026-11-12 | 11  | "Add stop" tab (place by map click), new-stop markers, explorer with new stops; fixed stale-draft click race; 103 Vitest, 11 e2e; parts 1–2 done |
| 2026-11-13 | 11  | Scenario type `add_route` (engine, AI, share link, display support); 0 diffs (5,738 journeys); 268 backend, 111 Vitest; live AI checked |
| 2026-11-13 | 11  | "Add route" tab (click stops in order, loop by clicking the first again), new routes on the map and in the legend; 120 Vitest, 13 e2e; screenshots checked |
| 2026-11-13 | 12  | AI edits the current change list (remove / replace / add operations, validated full list, Undo, stale guard); 288 backend, 123 Vitest, 16 e2e; live AI checked |
| 2026-11-13 | 12  | AI summary of results: placeholders filled by the backend, digits/number words rejected, one retry; 307 backend, 18 e2e; live AI checked (5 scenarios) |
| 2026-11-13 | 13  | Saved scenarios (changes only, checked on read) + comparison API; `scenario_state` extracted (0 diffs); seed keeps saved data; 327 backend |
| 2026-11-13 | 13  | Save / load / delete UI and comparison card (A vs B, better highlighted, largest differences); 128 Vitest, 20 e2e; screenshots checked |
| 2026-11-13 | 14  | GTFS import: Gdańsk trams (122 stations, 10 lines; CC BY + terms; attribution shown); compact AI prompt; 346 backend, 131 Vitest; live app + AI checked |
| 2026-11-13 | 14  | Fast engine (SciPy all-pairs, vectorised, cached baseline): full Gdańsk 15–18 s → ~1 s, compare 56 s → 2.2 s; 0 differences (598 simulations); 353 backend |
| 2026-11-13 | 14  | Results list the 1,000 largest changes (5.1 MB → 205 kB), CSV from the backend; e2e guard against a non-sample backend; 358 backend, 126 Vitest |
| 2026-11-13 | 14  | AI excerpts for big networks (stem matching for Polish names): full Gdańsk prompt 55k → 6–11k chars; 377 backend; live AI checked (4 requests + summary) |
| 2026-11-13 | 14  | Session end: step B1–B3 committed, CI green; next B4 (map/UI at scale) |
| 2026-11-14 | 14  | B4: measured (no canvas needed); legend scroll + line filter; small stops when zoomed out on big networks; live check of the full app; 131 Vitest, 20 e2e |
| 2026-11-14 | 14  | Walking between stops, step A: walking layer in the route graph (Day 10 rules); trams + full network 0 differences, sample 1 pair (known limit); 380 backend |
| 2026-11-14 | 14  | Walking between stops, step B: on by default (start/end ≤ 1 km, between buses ≤ 500 m); explorer walks list; closing a stop no longer makes journeys faster; 386 backend, 135 Vitest, 20 e2e |
