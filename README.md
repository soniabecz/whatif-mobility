# WhatIf Mobility

[![CI](https://github.com/soniabecz/whatif-mobility/actions/workflows/ci.yml/badge.svg)](https://github.com/soniabecz/whatif-mobility/actions/workflows/ci.yml)

An AI-powered urban public transport simulator. Users describe hypothetical
changes to a city bus network in natural language ("close stop X",
"add a route between A and B"), and the system simulates their impact on
passenger journeys.

> **Status:** MVP complete. The backend serves an invented sample bus network
> and simulates scenarios (close a stop, remove a connection, change a travel
> time) with deterministic before/after metrics. The web UI shows the network
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
│       └── types/       TypeScript types mirroring backend schemas
└── CLAUDE.md          project rules and conventions
```

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
network. The database file is git-ignored.

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
| `POST /api/ai/interpret` | plain-language text → scenario changes for review (needs `GROQ_API_KEY`) |

Example scenario (changes are applied in order; `both_directions` defaults to `true`):

```json
{
  "changes": [
    { "type": "close_stop", "stop_id": "CEN" },
    { "type": "remove_connection", "from_stop_id": "MKT", "to_stop_id": "UNI" },
    { "type": "change_travel_time", "from_stop_id": "RIV", "to_stop_id": "EST",
      "travel_time_min": 9, "both_directions": false }
  ]
}
```

**Terminal 2 – frontend**

```bash
cd frontend
npm run dev
```

Open http://localhost:5173. The header shows **● Connected** and the bus
network appears on the map. Build a scenario in the sidebar, click
**Run simulation**, and the results appear below the form and on the map.

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
npm run build    # type-check with TypeScript and build for production
```

## Continuous integration

Every push to `main` and every pull request runs
[`.github/workflows/ci.yml`](.github/workflows/ci.yml) on GitHub Actions:
backend `pytest`, and frontend `npm ci`, lint, type check and build. No secrets
are needed: the tests use a fake AI model and an in-memory database.

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

Restart the backend after changing `backend/.env`.

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
