# WhatIf Mobility

[![CI](https://github.com/soniabecz/whatif-mobility/actions/workflows/ci.yml/badge.svg)](https://github.com/soniabecz/whatif-mobility/actions/workflows/ci.yml)

An AI-powered urban public transport simulator for **Gdańsk**. Users describe
hypothetical changes to the city's tram and bus network in natural language
("close stop X", "add a route between A and B"), and the system simulates their
impact on passenger journeys.

> **Status:** the app runs on the real ZTM Gdańsk network (trams and buses,
> 714 stations, 93 lines, imported from the public GTFS timetable) and simulates
> scenarios (close a stop, remove a connection, change a travel time, change how
> often a route runs, add a link, a stop or a whole route) with deterministic
> before/after metrics. The web UI shows the network on a map, builds scenarios
> with a form or from plain language (AI via Groq), and displays the results.
> A small invented sample city exists only as test data.

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
creates `backend/.env` from the example and imports the Gdańsk network into
`backend/gdansk.db` (a one-time download of about 25 MB, see
[The network: Gdańsk](#the-network-gdańsk)). Later runs only reinstall what
changed and **never touch the network**. Then it starts
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
python -m app.import_gtfs        # import Gdańsk (trams and buses) into backend/gdansk.db
cp .env.example .env             # then add your Groq API key (optional, see below)
```

Re-run `python -m app.import_gtfs` to refresh the network from the latest
timetable (saved scenarios are kept). The database file is git-ignored.

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
    { "type": "close_stop", "stop_id": "S1028" },
    { "type": "remove_connection", "from_stop_id": "S1025", "to_stop_id": "S1013" },
    { "type": "change_travel_time", "from_stop_id": "S1025", "to_stop_id": "S1832",
      "travel_time_min": 6, "both_directions": false },
    { "type": "change_frequency", "route_id": "B199", "headway_min": 10 }
  ]
}
```

(Brama Wyżynna closed; Hucisko – Dworzec Główny removed; Hucisko → Targ Drzewny
takes 6 minutes; bus 199 every 10 minutes. Station ids and names are in
`GET /api/network`.)

`add_connection` lets an existing route also run directly between two stops
(an extension or a shortcut). At least one of the stops must already be on the
route, and the route must not already run between them; the travel time is
always given by the user. A stop that no route reached before can become
reachable; such journeys are counted as `newly_possible`.

`add_stop` inserts a new stop into one route between two consecutive stops:
the route's buses then run from → new stop → to (and back, if the route runs
both ways); other routes on that street are unchanged. The user gives both
travel times. Journeys to or from new stops have no "before", so they are
reported separately (`summary.new_stops`: how many, how many possible, average
time) and kept out of every other figure. The AI does not add stops (it would
have to invent coordinates); it points to the form instead.

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
(to select that link, or on the **Frequency** and **Add link** tabs its route),
or two stops one after the other (From, then To; on **Add link** any two
stops, otherwise neighbours). The current selection
is ringed in indigo on the map; changed frequencies appear in the legend. On
the **Add stop** tab, a click on the map places the new stop; a click on a
line places it there and also chooses that route and link.

**Sharing a scenario:** the address bar always holds a link to the current list
of changes (**Copy link** next to *Clear* copies it). Opening the link restores
the changes; the recipient presses *Run* and gets the same results, because
the simulation is deterministic. The format is readable and can be edited by hand:

```
http://localhost:5173/?s=close:S1028~remove:S1025-S1013~time:S1025-S1832:6:oneway
```

Changes are separated by `~`; `:oneway` limits a link change to one direction;
`freq:B199:10` sets bus 199 to a bus every 10 minutes; `add:<route>:<from>-<to>:<minutes>`
adds a link to a route.
A link with any invalid change (unknown stop, no such link, time out of range,
more than 20 changes) loads nothing and says why.

**CSV export:** the **CSV** button in the results header downloads all changed
journeys (`origin_id, origin_name, destination_id, destination_name, status,
time_before_min, time_after_min, change_min`), exactly as the backend computed
them; times are empty for impossible journeys. The file is comma-separated
UTF-8 with `.` as the decimal point; in Excel with a locale that uses `;`,
open it via *Data → From Text/CSV*.

If the page says the network is empty, run `python -m app.import_gtfs` in `backend/`
(or `./dev.sh`).

Map tiles come from the public OpenStreetMap tile server, which is fine for
local development. A public deployment needs its own tile provider.

## The network: Gdańsk

The app runs on the real network of **ZTM Gdańsk**, trams and buses, imported from
its GTFS timetable feed ([open data](https://ckan.multimediagdansk.pl/dataset/tristar)).
`./dev.sh` imports it on the first run; to refresh it by hand:

```bash
cd backend && source .venv/bin/activate
python -m app.import_gtfs            # trams and buses into backend/gdansk.db
```

- The database is `backend/gdansk.db`; `WHATIF_DATABASE` (a file name in `backend/`)
  picks another one. Set it in the shell, not in `backend/.env`. A database holding
  the invented sample city is refused: the sample is test data only (see
  [Tests and checks](#tests-and-checks)).
- `python -m app.import_gtfs [zip or URL] [--modes tram|bus|all] [--date YYYY-MM-DD] [--if-empty]`
  (default: all modes; `--if-empty` does nothing when a network is already imported);
  other feeds: add `--attribution-url` and `--licence`. Downloads go to
  `backend/data/gtfs/` (git-ignored). Saved scenarios are kept; those that no longer
  fit the network are flagged.
- How the timetable becomes the app's network (stations = stop posts grouped by
  name; each line's most frequent stop sequence on one weekday; median link times;
  peak headways; no demand data) is in `backend/app/services/gtfs_import.py` and in
  the app's legend ("How the network was built").
- **Terms of the data**: the app names the publisher (Zarząd Transportu Miejskiego w
  Gdańsku, http://www.ztm.gda.pl/otwarty_ztm) and the data's creation and download
  dates on the map and in the legend. Keeping the data current is the user's duty:
  re-run the import now and then (the feed covers about two weeks ahead).
- Size: 714 stations, about 510,000 journeys; a simulation takes about 1.5 seconds,
  and the AI gets only the part of the network a request is about.
- Each line's stop sequences ("patterns", one per direction) are stored too:
  passengers stay on a vehicle only where a trip really goes (on the full network
  this corrects 20 % of journeys, e.g. staying on through a terminus). A database
  imported before they existed (Day 14 part 4) keeps the earlier, more optimistic
  rule; re-run the import to add them.
- On the free Groq tier (8,000 tokens per minute), one AI request on Gdańsk uses
  most of a minute's allowance: wait about a minute between AI requests.

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
route run more often with the Frequency tab; add a link with the Add link tab
(and see the form refuse one the route cannot get); add whole and decimal
minutes on the Travel time tab; and place a new stop by clicking the map, run
it and check the new-stop figures and an explorer journey from it. It uses the real backend on the
**invented sample city**, test data with stable, hand-checkable numbers: Playwright seeds it into
its own test database, `backend/e2e-sample.db`, on every run (`python -m app.seed` writes only
into databases named `e2e-*.db`, never into the app's `gdansk.db`). The backend tests use the
same sample in memory.

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
| `WALKING_ENABLED`   | `backend/.env`        | `true`                  | Passengers may walk (off: journeys to/from closed stops are left out) |
| `WALK_SPEED_KMH`    | `backend/.env`        | `5`                     | Walking speed (1–10) |
| `MAX_WALK_M`        | `backend/.env`        | `1000`                  | Longest walk at the start or end, in metres (100–3000) |
| `MAX_TRANSFER_WALK_M` | `backend/.env`      | `500`                   | Longest walk between two buses, in metres (0–3000, at most `MAX_WALK_M`) |
| `WALK_BETWEEN_OPEN_STOPS` | `backend/.env`  | `true`                  | `false`: walk only from or to a closed stop (the model before Day 14 part 3) |

Restart the backend after changing `backend/.env`.

## How journeys are calculated

The simulation uses a route-aware graph: for every stop it knows which bus you
are on. A journey's time is

```
time on the bus + waiting at every boarding + 2 min per change of bus
```

- **Waiting:** every route has a headway (a bus every N minutes), taken from the
  timetable's morning peak. Passengers arrive at random, so they wait half
  the headway on average, at the first boarding too (`INCLUDE_WAITING`).
- **Changing bus** adds `TRANSFER_PENALTY_MIN` (2 min) for the inconvenience
  of changing, on top of the wait for the next bus.
- `INCLUDE_WAITING=false` with `TRANSFER_PENALTY_MIN=5` reproduces the model
  used before waiting was added (checked over 3,374 results, 0 differences).
- Known simplification: where two routes share a street, a real passenger
  takes whichever bus comes first; the model waits for one specific route.

Journeys are all ordered pairs of stations (about 510,000). The counts (slower,
faster, impossible) weigh every journey the same. There is no passenger data, so
**"% of trips"** weighs every station the same too: it equals the share of
journeys. (The engine can weigh stations by an activity level; only the test
sample city uses that, with invented levels.)

A closed stop is driven through by buses, but nobody can board, alight or
change bus there. **Walking** is part of the route graph, so one search finds
the fastest journey: passengers may walk at the start and at the end (at most
1,000 m), between two buses (at most 500 m; it counts as a change of bus), or
the whole way, but never twice in a row. A closed stop is left or reached on
foot. Walking distance = straight line × 1.3, at 5 km/h (invented assumptions).
Today's network and the scenario walk alike.
With `WALK_BETWEEN_OPEN_STOPS=false` passengers walk only from or to a closed
stop (Day 10 to Day 14 part 3 step A); with `WALKING_ENABLED=false` journeys to
or from a closed stop are excluded, as before Day 10 part 3.

**Staying on the vehicle:** each line's stop sequences ("patterns": the
timetable's main sequence per direction) decide where passengers may stay on:
only to the next stop of the same sequence. Turning round, switching direction at a terminus or between
directions that use different stops, or skipping a loop the vehicle drives is
a change of bus (wait + penalty). A link added by a scenario joins its line at
both ends; a line without stored patterns (an older imported database) keeps
the earlier rule (stay on along any of the line's links).

After pulling a change that adds database columns, `./dev.sh` rebuilds the
network tables and imports Gdańsk again (saved scenarios are kept).

## How the AI is used

The AI (a Groq-hosted model) only **translates** text such as *"roadworks make
Hucisko – Targ Drzewny twice as slow"* into the scenario format. Its answer is
forced into a strict JSON schema, validated with the same rules as the form, and
dry-run against the network before it is shown. The changes then appear in the
normal list, where the user checks them before running the simulation. The AI
never sees or produces simulation results: every number comes from the
deterministic simulation engine. Requests it cannot map (ambiguous, unsupported
such as new routes, or unrelated) come back as "unclear" with an explanation.

The frontend dev server must run on port 5173. That address is in the backend's
CORS allow-list (`ALLOWED_ORIGINS` in `backend/app/main.py`).
