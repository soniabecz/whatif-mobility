#!/usr/bin/env bash
# Start WhatIf Mobility for local development with one command:
#
#     ./dev.sh
#
# First run: creates backend/.venv, installs packages, creates backend/.env
# from the example and seeds the sample network. Later runs only install
# what changed and never reset the database (use `python -m app.seed` for that).
# Then starts the backend (port 8000) and frontend (port 5173) with hot
# reload. Ctrl+C stops both.
#
# Works with the bash 3.2 that ships with macOS, and on Linux.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV_PY="$BACKEND/.venv/bin/python"
API_URL="http://localhost:8000"
WEB_URL="http://localhost:5173"

step() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

# --- Requirements ------------------------------------------------------------

command -v python3 >/dev/null || fail "python3 not found (Python 3.11+ needed)."
command -v node >/dev/null || fail "node not found (Node.js 20+ needed)."
command -v npm >/dev/null || fail "npm not found."
command -v curl >/dev/null || fail "curl not found."

python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' \
  || fail "Python 3.11+ needed, found $(python3 --version 2>&1)."
node -e 'process.exit(Number(process.versions.node.split(".")[0]) < 20 ? 1 : 0)' \
  || fail "Node.js 20+ needed, found $(node --version)."

# The frontend port is fixed: it is the only origin the backend's CORS allows.
for port in 8000 5173; do
  if lsof -iTCP:"$port" -sTCP:LISTEN -n -P >/dev/null 2>&1; then
    fail "Port $port is already in use. Is the app already running? (lsof -iTCP:$port -sTCP:LISTEN)"
  fi
done

# --- Backend setup -----------------------------------------------------------

if [ ! -x "$VENV_PY" ]; then
  step "Creating backend/.venv"
  python3 -m venv "$BACKEND/.venv"
fi

# Reinstall only when requirements.txt changed since the last install.
STAMP="$BACKEND/.venv/.requirements-installed"
if [ ! -f "$STAMP" ] || [ "$BACKEND/requirements.txt" -nt "$STAMP" ]; then
  step "Installing backend packages"
  "$VENV_PY" -m pip install --quiet --upgrade pip
  "$VENV_PY" -m pip install --quiet -r "$BACKEND/requirements.txt"
  touch "$STAMP"
fi

if [ ! -f "$BACKEND/.env" ]; then
  step "Creating backend/.env from .env.example (add GROQ_API_KEY to enable the AI input)"
  cp "$BACKEND/.env.example" "$BACKEND/.env"
fi

step "Checking the database"
(cd "$BACKEND" && "$VENV_PY" -m app.seed --if-empty)

# --- Frontend setup ----------------------------------------------------------

# npm writes node_modules/.package-lock.json on every install.
if [ ! -f "$FRONTEND/node_modules/.package-lock.json" ] \
  || [ "$FRONTEND/package-lock.json" -nt "$FRONTEND/node_modules/.package-lock.json" ]; then
  step "Installing frontend packages"
  (cd "$FRONTEND" && npm ci --no-audit --no-fund)
fi

# --- Start both servers ------------------------------------------------------

BACKEND_PID=""
FRONTEND_PID=""

stop_servers() {
  trap - INT TERM EXIT
  echo
  step "Stopping servers"
  # uvicorn's reloader and npm forward the signal to their child processes.
  for pid in $FRONTEND_PID $BACKEND_PID; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap stop_servers EXIT                  # error or normal end
trap 'stop_servers; exit 130' INT TERM  # Ctrl+C: stop both, then quit

wait_for() { # url, name, pid
  local i
  for i in $(seq 1 60); do
    curl -fsS -o /dev/null "$1" 2>/dev/null && return 0
    kill -0 "$3" 2>/dev/null || fail "$2 stopped during startup (see the output above)."
    sleep 0.5
  done
  fail "$2 did not respond at $1 within 30 seconds."
}

step "Starting backend on $API_URL"
(cd "$BACKEND" && exec "$VENV_PY" -m uvicorn app.main:app --reload --port 8000) &
BACKEND_PID=$!
wait_for "$API_URL/api/health" "Backend" "$BACKEND_PID"

step "Starting frontend on $WEB_URL"
(cd "$FRONTEND" && exec npm run dev) &
FRONTEND_PID=$!
wait_for "$WEB_URL" "Frontend" "$FRONTEND_PID"

printf '\n\033[1;32m  WhatIf Mobility is running:\033[0m %s  (API docs: %s/docs)\n' "$WEB_URL" "$API_URL"
printf '  Press Ctrl+C to stop both servers.\n\n'

# Stop everything as soon as either server exits (e.g. a crash).
while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done
fail "A server stopped unexpectedly (see the output above)."
