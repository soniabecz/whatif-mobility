# WhatIf Mobility – Implementation Plan

> **Read this file at the start of every session.**
> Update the checklists and the "Current status" section at the end of
> every session. Project rules and conventions are in `CLAUDE.md`.

## Current status

- **Last completed:** Day 5 (AI layer via Groq): 95 backend tests, lint and
  build pass, live API check with the real model and browser check passed
- **Next up:** MVP complete. Possible follow-ups are listed under Open issues
- **Repository:** https://github.com/soniabecz/whatif-mobility (private, branch `main`)

## Timeline

Total: **5 working days** (Day 1 done + 4 remaining). A "day" is one
working session. Every day must end with something working and committed,
so the project is usable even if a later day is cut short.

| Day | Focus                     | Status  |
| --- | ------------------------- | ------- |
| 1   | Setup and skeletons       | ✅ Done |
| 2   | Data model and graph      | ✅ Done |
| 3   | Simulation engine         | ✅ Done |
| 4   | Map and results UI        | ✅ Done |
| 5   | AI layer and wrap-up      | ✅ Done |

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
- UI polish beyond clear error messages (no dark mode, animations, etc.)

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
| No transfer penalty in the MVP; a journey = fastest path | Keeps the graph simple; can be added later |
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
| No frontend test runner; logic kept in pure `lib/` functions | Not in the tech stack; all metrics are tested in the backend |

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

---

## Open issues

- [ ] Starlette deprecation warning in tests: `httpx` → `httpx2`
      (verify `httpx2` is the official successor before switching)
- [ ] Production bundle is ~836 kB (Leaflet + Recharts); Vite warns at 500 kB.
      Fine for the MVP; code-split the chart if it matters later
- [ ] Routes sharing a street (R1/R4 on MKT–CEN) draw on top of each other;
      the tooltip names the route under the cursor only
- [ ] `fsevents` install script not approved by npm (optional; only needed
      if hot reload stops working: `npm install-scripts approve fsevents`)

## Decisions still needed

- [x] **Day 5:** AI provider and API key: Groq, `openai/gpt-oss-120b`

## Session log

| Date       | Day | Summary                                                     |
| ---------- | --- | ----------------------------------------------------------- |
| 2026-11-10 | 1   | Environment checked, skeletons built, committed and pushed  |
| 2026-11-11 | 2   | DB models, seed (16 stops, 4 routes), graph + shortest journey, network API; 25 tests |
| 2026-11-11 | 3   | Scenario schema, simulation engine (bypass on stop closure), metrics, `POST /api/simulations`; 63 tests |
| 2026-11-11 | 4   | Map, legend, scenario form, results panel and chart; lint + build pass; browser-checked |
| 2026-11-11 | 5   | Groq AI layer (strict JSON, 3-step validation), AI input in UI; 95 tests; live API + browser check passed |
