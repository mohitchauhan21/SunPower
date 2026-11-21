#!/usr/bin/env bash
# One-time SunPower setup on macOS (Apple Silicon or Intel), using Homebrew.
#
#   ./scripts/setup_mac.sh            # Python 3.12 + Node, back-end venv, frontend packages
#   ./scripts/setup_mac.sh --with-ai  # also install the AI service (~3 GB with its models)
#
# Nothing else is needed: the back end keeps its data in one SQLite file
# (backend/data/sunpower.db) and prints documents as HTML (no wkhtmltopdf).
# Safe to run again: every step skips what is already there.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
WITH_AI=0
[ "${1:-}" = "--with-ai" ] && WITH_AI=1

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

if ! command -v brew >/dev/null; then
  echo "Homebrew is required. Install it from https://brew.sh and run this script again." >&2
  exit 1
fi
say "Installing Python 3.12 and Node with Homebrew"
brew install python@3.12 node

say "Back end: Python environment and packages"
if [ ! -x "$REPO/backend/.venv/bin/python" ]; then
  python3.12 -m venv "$REPO/backend/.venv"
fi
"$REPO/backend/.venv/bin/python" -m pip install --upgrade pip >/dev/null
"$REPO/backend/.venv/bin/python" -m pip install -r "$REPO/backend/requirements.txt"

say "Website: npm packages"
(cd "$REPO/frontend" && npm install --no-audit --no-fund)

if [ "$WITH_AI" = 1 ]; then
  say "AI service: Python environment and packages (large; takes a few minutes)"
  if [ ! -x "$REPO/ai_service/.venv/bin/python" ]; then
    python3.12 -m venv "$REPO/ai_service/.venv"
  fi
  "$REPO/ai_service/.venv/bin/python" -m pip install --upgrade pip >/dev/null
  "$REPO/ai_service/.venv/bin/python" -m pip install -r "$REPO/ai_service/requirements.txt"
fi

cat <<EOF

==> Done. Start it in two terminals:
    ./backend/run.sh                # API on http://localhost:8001 (demo data on first start)
    (cd frontend && npm run dev)    # website on http://localhost:5173
    ./ai_service/run.sh             # optional third terminal: AI helpers on :8000

    Demo sign-in (password for all: sunpower):
    director@sunpower.demo · sales@ · warehouse@ · support@ · tech01@ · customer@sunpower.demo
EOF
