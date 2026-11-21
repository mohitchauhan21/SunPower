#!/usr/bin/env bash
# SunPower back end (macOS/Linux). Creates .venv on first run, installs packages,
# then serves the API on http://localhost:8001. The SQLite database lives in
# backend/data/sunpower.db and is filled with demo data on first start.
#   ./backend/run.sh [--port 8001] [--reset]
set -euo pipefail
cd "$(dirname "$0")"

PORT=8001
while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    --reset) rm -f data/sunpower.db data/sunpower.db-wal data/sunpower.db-shm
             echo "Database reset: demo data will be loaded again."; shift ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

if [ ! -x .venv/bin/python ]; then
  PY=""
  for v in python3.12 python3.13 python3.11 python3; do command -v "$v" >/dev/null && { PY="$v"; break; }; done
  [ -n "$PY" ] || { echo "Python 3.11+ not found (brew install python@3.12)." >&2; exit 1; }
  "$PY" -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
fi

echo "SunPower back end on http://localhost:$PORT  (API docs: /api/docs)"
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
