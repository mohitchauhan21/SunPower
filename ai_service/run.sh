#!/usr/bin/env bash
# SunPower AI service launcher for macOS/Linux (counterpart of run.ps1).
# Creates .venv on first run, installs requirements, then starts uvicorn.
#
#   ./ai_service/run.sh [--port 8000] [--reinstall]
set -euo pipefail
cd "$(dirname "$0")"

PORT=8000
REINSTALL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    --reinstall) REINSTALL=1; shift ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

VENV_PY=".venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
  # Prefer 3.12/3.11 (widest wheel support), else 3.13 (works with TensorFlow 2.20).
  PY=""
  for v in python3.12 python3.11 python3.13; do
    command -v "$v" >/dev/null && { PY="$v"; break; }
  done
  [ -n "$PY" ] || { echo "Python 3.11-3.13 not found (brew install python@3.12)." >&2; exit 1; }
  echo "Creating venv with $PY ..."
  "$PY" -m venv .venv
  REINSTALL=1
fi

if [ "$REINSTALL" = 0 ] && ! "$VENV_PY" -c "import fastapi, uvicorn, huggingface_hub, dotenv, multipart, PIL, numpy, torch, transformers, soundfile, rapidocr" 2>/dev/null; then
  REINSTALL=1   # venv exists but packages are missing (e.g. an interrupted install)
fi

if [ "$REINSTALL" = 1 ]; then
  echo "Installing requirements (TensorFlow and PyTorch are large; the first install takes a few minutes) ..."
  "$VENV_PY" -m pip install --upgrade pip
  "$VENV_PY" -m pip install -r requirements.txt
fi

[ -f ../.env ] || echo "Note: ../.env not found. HF_TOKEN is optional; the local models are used without it."

echo "Starting SunPower AI service on http://localhost:$PORT ..."
exec "$VENV_PY" -m uvicorn main:app --host 127.0.0.1 --port "$PORT"
