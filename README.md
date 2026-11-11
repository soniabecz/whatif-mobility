# WhatIf Mobility

An AI-powered urban public transport simulator. Users describe hypothetical
changes to a city bus network in natural language ("close stop X",
"add a route between A and B"), and the system simulates their impact on
passenger journeys.

> **Status:** early development. The backend serves an invented sample bus
> network and simulates scenarios (close a stop, remove a connection, change
> a travel time) with deterministic before/after metrics. The web UI shows
> the network on a map, builds scenarios with a form and displays the
> results. The AI (natural-language) layer is not implemented yet.

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

## Configuration

Configuration is read from environment variables. Real values go in local
`.env` files, which are **git-ignored and must never be committed**. Each
`.env.example` file documents the available variables.

| Variable            | Where                 | Default                 | Purpose                    |
| ------------------- | --------------------- | ----------------------- | -------------------------- |
| `VITE_API_BASE_URL` | `frontend/.env.local` | `http://localhost:8000` | Address of the backend API |

The frontend dev server must run on port 5173. That address is in the backend's
CORS allow-list (`ALLOWED_ORIGINS` in `backend/app/main.py`).
