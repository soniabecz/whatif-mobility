# WhatIf Mobility – Implementation Plan

> **Read this file at the start of every session.**
> Update the checklists and the "Current status" section at the end of
> every session. Project rules and conventions are in `CLAUDE.md`.

## Current status

- **Last completed:** Day 1 (setup), commit `e6a598b`, pushed to GitHub
- **Next up:** Day 2 – Data model and graph
- **First action next session:** explain the data model design and wait for
  approval before writing code
- **Repository:** https://github.com/soniabecz/whatif-mobility (private, branch `main`)

## Timeline

Total: **5 working days** (Day 1 done + 4 remaining). A "day" is one
working session. Every day must end with something working and committed,
so the project is usable even if a later day is cut short.

| Day | Focus                     | Status  |
| --- | ------------------------- | ------- |
| 1   | Setup and skeletons       | ✅ Done |
| 2   | Data model and graph      | ⬜ Todo |
| 3   | Simulation engine         | ⬜ Todo |
| 4   | Map and results UI        | ⬜ Todo |
| 5   | AI layer and wrap-up      | ⬜ Todo |

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

## Day 2 – Data model and graph

**Outcome:** a sample network stored in SQLite, served by the API and
turned into a NetworkX graph that can calculate shortest journeys.

- [ ] Explain data model design and get approval
- [ ] `database.py`: SQLAlchemy engine/session for SQLite
- [ ] SQLAlchemy models: Stop, Route, Connection (directed, with travel time)
- [ ] Pydantic schemas for the network API responses
- [ ] Seed script with the invented sample network (~15–20 stops, 3–4 routes)
- [ ] `network_service.py`: build a directed NetworkX graph from the DB
      (stops = nodes, connections = edges, weight = travel time)
- [ ] Shortest-journey calculation between two stops
- [ ] API endpoints: list stops, list routes, get network
- [ ] Tests: graph building, shortest path, endpoints
- [ ] Run tests, explain changes, commit

## Day 3 – Simulation engine

**Outcome:** a tested engine that applies a scenario to a copy of the
baseline graph and returns deterministic before/after metrics.

- [ ] Explain scenario format and metrics; get approval
- [ ] Pydantic scenario schema for the three types
      (close stop, remove connection, change travel time)
- [ ] Validation errors for unknown stops/connections
- [ ] `simulation_service.py`: copy graph → apply changes → compute metrics
- [ ] Metrics (deterministic), e.g. journey times before/after,
      journeys that become impossible, most affected stops
- [ ] Test that the baseline graph is never modified
- [ ] Tests for each scenario type and for edge cases
- [ ] `POST /api/simulations` endpoint
- [ ] Run tests, explain changes, commit

## Day 4 – Map and results UI

**Outcome:** user sees the network on a map, builds a scenario with a
form, and sees before/after results.

- [ ] Install React Leaflet and Recharts
- [ ] TypeScript types mirroring network and simulation schemas
- [ ] Map component showing stops and routes
- [ ] Scenario form (choose type, stop/connection, value)
- [ ] Call `POST /api/simulations` and show loading / error states
- [ ] Before/after comparison chart (Recharts)
- [ ] Highlight affected stops on the map
- [ ] Lint, build, manual browser check, commit

**Risk:** fullest day. Fallback: show results as a table instead of charts.

## Day 5 – AI layer and wrap-up

**Outcome:** user types a change in plain language; the AI turns it into
a structured scenario; the existing simulation computes the results.

- [ ] Choose AI provider; obtain API key (**do this before Day 5**)
- [ ] `config.py` reading settings from environment; `backend/.env.example`
- [ ] `ai_service.py`: text → scenario JSON (no metrics from AI)
- [ ] Validate AI output with the Pydantic scenario schema
- [ ] Clear error when the request cannot be understood
- [ ] Tests for AI service with a mocked AI client
- [ ] Natural-language input in the UI, reusing the Day 4 results view
- [ ] Update README (setup incl. API key), final checks, demo run, commit

**Fallback:** if Day 5 runs short, the app is still complete with the form.

---

## Open issues

- [ ] Starlette deprecation warning in tests: `httpx` → `httpx2`
      (verify `httpx2` is the official successor before switching)
- [ ] `fsevents` install script not approved by npm (optional; only needed
      if hot reload stops working: `npm install-scripts approve fsevents`)

## Decisions still needed

- [ ] **Day 5:** AI provider and API key

## Session log

| Date       | Day | Summary                                                     |
| ---------- | --- | ----------------------------------------------------------- |
| 2026-11-10 | 1   | Environment checked, skeletons built, committed and pushed  |
