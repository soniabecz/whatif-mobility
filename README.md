# WhatIf Mobility

[![CI](https://github.com/soniabecz/whatif-mobility/actions/workflows/ci.yml/badge.svg)](https://github.com/soniabecz/whatif-mobility/actions/workflows/ci.yml)

An AI-powered urban public transport simulator. Users describe hypothetical
changes to a city bus network in natural language ("close stop X",
"add a route between A and B"), and the system simulates their impact on
passenger journeys.

> **Status:** MVP complete. The backend serves an invented sample bus network
> and simulates scenarios (close a stop, remove a connection, change a travel
> time, change how often a route runs) with deterministic before/after metrics. The web UI shows the network
> on a map, builds scenarios with a form or from plain language (AI via Groq),
> and displays the results.

## Tech stack

| Part     | Technologies                                                        |
| -------- | ------------------------------------------------------------------- |
| Backend  | Python, FastAPI, SQLAlchemy, Pydantic, SQLite, NetworkX, Pytest     |
| Frontend | React, TypeScript, Vite, Tailwind CSS, Axios, React Leaflet, Recharts |

## Prerequisites

- **Python** 3.11 or newer
- **Node.js** 20 or newer (developed with Node 24)
- **Git**

## Project structure

```
whatif-mobility/
├── backend/           FastAPI REST API (port 8000)
│   ├── app/           application code
│   ├── tests/         pytest tests
│   └── requirements.txt
├── frontend/          React single-page app (port 5173)
│   └── src/
│       ├── api/         HTTP calls to the backend and error messages
│       ├── components/  map, legend, scenario form, results, chart
│       ├── lib/         pure helpers (network lookups, impact colours)
│       └── types/       TypeScript types generated from the backend's OpenAPI schema
├── dev.sh             one-command start (setup + both servers)
└── CLAUDE.md          project rules and conventions
```

## Quick start

```bash
./dev.sh
```

One command does everything (macOS and Linux; on Windows use WSL): on the first
run it creates `backend/.venv`, installs the backend and frontend packages,
creates `backend/.env` from the example and seeds the sample network. Later
runs only reinstall what changed and **never reset the database**. Then it starts
both servers with hot reload and prints the address,
http://localhost:5173. **Ctrl+C** stops both.

To enable the AI input, put your Groq API key in `backend/.env` (see
[Configuration](#configuration)) and restart.

The sections below do the same steps by hand.

## Setup (first time only)

### Backend

```bash
cd backend
python3 -m venv .venv            # create an isolated Python environment
source .venv/bin/activate        # activate it (prompt shows "(.venv)")
pip install -r requirements.txt
python -m app.seed               # create backend/whatif.db with the sample network
cp .env.example .env             # then add your Groq API key (optional, see below)
```

Re-run `python -m app.seed` at any time to reset the database to the sample
network (`python -m app.seed --if-empty` seeds only a fresh database). The database file is git-ignored.

### Frontend

```bash
cd frontend
npm install
```

## Running the app

The backend and frontend run as two separate processes, so use two terminals.

**Terminal 1 – backend**

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Interactive API docs: http://localhost:8000/docs

| Endpoint            | Returns                                      |
| ------------------- | -------------------------------------------- |
| `GET /api/health`   | `{"status": "ok"}`                           |
| `GET /api/stops`    | all stops (id, name, lat, lon)               |
| `GET /api/routes`   | all routes (id, name, color)                 |
| `GET /api/network`  | stops, routes and directed connections       |
| `POST /api/simulations` | before/after metrics for a scenario (nothing is stored) |
| `POST /api/journeys` | one journey before/after a scenario, split into legs (journey explorer) |
| `POST /api/ai/interpret` | plain-language text → scenario changes for review (needs `GROQ_API_KEY`) |

Example scenario (changes are applied in order; `both_directions` defaults to `true`):

```json
{
  "changes": [
    { "type": "close_stop", "stop_id": "CEN" },
    { "type": "remove_connection", "from_stop_id": "MKT", "to_stop_id": "UNI" },
    { "type": "change_travel_time", "from_stop_id": "RIV", "to_stop_id": "EST",
      "travel_time_min": 9, "both_directions": false },
    { "type": "change_frequency", "route_id": "R3", "headway_min": 7.5 }
  ]
}
```

`change_frequency` sets a route's headway (a bus every 1–120 minutes). It only
changes waiting times, so it has no effect when `INCLUDE_WAITING=false`.

**Terminal 2 – frontend**

```bash
cd frontend
npm run dev
```

Open http://localhost:5173. The header shows **● Live** and the bus
network appears on the map. Build a scenario in the sidebar, click
**Run simulation**, and the results appear below the form and on the map.

Instead of the dropdowns you can click the map: a stop (to close it), a line
(to select that link, or on the **Frequency** tab its whole route), or two
neighbouring stops one after the other (From, then To). The current selection
is ringed in indigo on the map; changed frequencies appear in the legend.

**Sharing a scenario:** the address bar always holds a link to the current list
of changes (**Copy link** next to *Clear* copies it). Opening the link restores
the changes; the recipient presses *Run* and gets the same results, because
the simulation is deterministic. The format is readable and can be edited by hand:

```
http://localhost:5173/?s=close:CEN~remove:MKT-UNI~time:RIV-EST:9:oneway
```

Changes are separated by `~`; `:oneway` limits a link change to one direction;
`freq:R3:7.5` sets route R3 to a bus every 7.5 minutes.
A link with any invalid change (unknown stop, no such link, time out of range,
more than 20 changes) loads nothing and says why.

**CSV export:** the **CSV** button in the results header downloads all changed
journeys (`origin_id, origin_name, destination_id, destination_name, status,
time_before_min, time_after_min, change_min`), exactly as the backend computed
them; times are empty for impossible journeys. The file is comma-separated
UTF-8 with `.` as the decimal point; in Excel with a locale that uses `;`,
open it via *Data → From Text/CSV*.

If the page says the network is empty, run `python -m app.seed` in `backend/`.

Map tiles come from the public OpenStreetMap tile server, which is fine for
local development. A public deployment needs its own tile provider.

## Tests and checks

```bash
# Backend (with .venv activated)
cd backend
pytest -v

# Frontend
cd frontend
npm run lint     # static code checks (oxlint)
npm test         # unit tests for the pure helpers in src/lib (Vitest)
npm run test:e2e # end-to-end test in a real browser (Playwright, see below)
npm run build    # type-check with TypeScript and build for production
```

### End-to-end test

`npm run test:e2e` opens the app in Chromium and runs two tests: close a stop
with the form, run the simulation and check that the results show exactly the
numbers the backend computes; fill in the form by clicking stops and lines on
the map; open, update and copy shareable links (including an invalid one); and
download the CSV export and compare every row with the backend; and make a
route run more often with the Frequency tab. It uses the real backend and the seeded sample network
(`python -m app.seed`); nothing is written to the database.

Playwright starts the backend (from `backend/.venv`) and the Vite dev server
itself, or reuses them if they are already running. Download the browser once:

```bash
cd frontend
npx playwright install chromium
```

## Continuous integration

Every push to `main` and every pull request runs
[`.github/workflows/ci.yml`](.github/workflows/ci.yml) on GitHub Actions:
backend `pytest`; frontend `npm ci`, lint, unit tests, type check and build; a check
that the generated API types are up to date; and the end-to-end test. No secrets are needed: the tests
use a fake AI model and an in-memory database.

## API types

The frontend's TypeScript types are generated from the backend's Pydantic
schemas, so the two cannot drift apart. After changing anything in
`backend/app/schemas/` (or an endpoint's request/response model), run:

```bash
cd backend && python -m app.export_openapi   # writes frontend/openapi.json
cd ../frontend && npm run gen:types          # writes src/types/api.gen.ts
```

and commit both files; CI fails otherwise. The files in `src/types/*.ts` give
the generated types short names (`Scenario`, `Stop`, …); never edit
`api.gen.ts` by hand.

The generator ([openapi-typescript](https://openapi-ts.dev)) lives in its own
small package, `frontend/tools/openapi/`, because it needs the TypeScript 5
compiler API, which TypeScript 7 (used by the app) no longer ships. Install it
once with `npm ci --prefix tools/openapi` (from `frontend/`).

## Configuration

Configuration is read from environment variables. Real values go in local
`.env` files, which are **git-ignored and must never be committed**. Each
`.env.example` file documents the available variables.

| Variable            | Where                 | Default                 | Purpose                    |
| ------------------- | --------------------- | ----------------------- | -------------------------- |
| `VITE_API_BASE_URL` | `frontend/.env.local` | `http://localhost:8000` | Address of the backend API |
| `GROQ_API_KEY`      | `backend/.env`        | *(none)*                | Enables the AI input; without it the form still works |
| `AI_MODEL`          | `backend/.env`        | `openai/gpt-oss-120b`   | Groq model used by the AI input |
| `AI_TIMEOUT_SECONDS`| `backend/.env`        | `30`                    | How long to wait for the AI |
| `TRANSFER_PENALTY_MIN` | `backend/.env`     | `2`                     | Minutes added per change of bus, on top of waiting (0–60) |
| `INCLUDE_WAITING`   | `backend/.env`        | `true`                  | Wait half the route's headway at every boarding |

Restart the backend after changing `backend/.env`.

## How journeys are calculated

The simulation uses a route-aware graph: for every stop it knows which bus you
are on. A journey's time is

```
time on the bus + waiting at every boarding + 2 min per change of bus
```

- **Waiting:** every route has a headway (a bus every N minutes:
  R1 and R2 every 10, R3 every 15, R4 every 20). These are **invented**, like
  the whole sample network. Passengers arrive at random, so they wait half
  the headway on average, at the first boarding too (`INCLUDE_WAITING`).
- **Changing bus** adds `TRANSFER_PENALTY_MIN` (2 min) for the inconvenience
  of changing, on top of the wait for the next bus.
- `INCLUDE_WAITING=false` with `TRANSFER_PENALTY_MIN=5` reproduces the model
  used before waiting was added (checked over 3,374 results, 0 differences).
- Known simplification: where two routes share a street, a real passenger
  takes whichever bus comes first; the model waits for one specific route.

Journeys are all ordered pairs of stops, weighted equally. A closed stop is
driven through by buses, but nobody can board, alight or change bus there.

After pulling a change that adds database columns, `./dev.sh` (or
`python -m app.seed`) rebuilds the tables automatically; the database only
holds generated sample data.

## How the AI is used

The AI (a Groq-hosted model) only **translates** text such as *"roadworks make
Riverside – East Gate twice as slow"* into the scenario format. Its answer is
forced into a strict JSON schema, validated with the same rules as the form, and
dry-run against the network before it is shown. The changes then appear in the
normal list, where the user checks them before running the simulation. The AI
never sees or produces simulation results: every number comes from the
deterministic simulation engine. Requests it cannot map (ambiguous, unsupported
such as new routes, or unrelated) come back as "unclear" with an explanation.

The frontend dev server must run on port 5173. That address is in the backend's
CORS allow-list (`ALLOWED_ORIGINS` in `backend/app/main.py`).
