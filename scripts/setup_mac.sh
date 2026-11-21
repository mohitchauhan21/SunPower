#!/usr/bin/env bash
# One-time SunPower setup on macOS (Apple Silicon or Intel), using Homebrew.
#
#   ./scripts/setup_mac.sh            # installs tools, Odoo 18 + venv, PostgreSQL, writes odoo.conf
#
# Layout (same as on Windows), override with ODOO_HOME:
#   $ODOO_HOME/odoo       Odoo 18 source (git clone)
#   $ODOO_HOME/venv       Odoo's Python environment
#   $ODOO_HOME/odoo.conf  config pointing at this repo's addons/
#   $ODOO_HOME/data       filestore
# Safe to run again: every step skips what is already there.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
ODOO_HOME="${ODOO_HOME:-$HOME/odoo18}"
PG_FORMULA="${PG_FORMULA:-postgresql@16}"
PY="python3.12"

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

# ---------------------------------------------------------------- tools
if ! command -v brew >/dev/null; then
  echo "Homebrew is required. Install it from https://brew.sh and run this script again." >&2
  exit 1
fi
say "Installing tools with Homebrew (python@3.12, $PG_FORMULA, node, git)"
brew install python@3.12 "$PG_FORMULA" node git
PG_BIN="$(brew --prefix "$PG_FORMULA")/bin"
export PATH="$PG_BIN:$PATH"   # pg_config is needed to build psycopg2

# ---------------------------------------------------------------- PostgreSQL
say "Starting PostgreSQL ($PG_FORMULA)"
brew services start "$PG_FORMULA" >/dev/null || true
for _ in $(seq 1 20); do "$PG_BIN/pg_isready" -q -h localhost && break; sleep 1; done
"$PG_BIN/pg_isready" -h localhost || { echo "PostgreSQL did not start." >&2; exit 1; }

# ---------------------------------------------------------------- Odoo 18
mkdir -p "$ODOO_HOME/data"
if [ ! -d "$ODOO_HOME/odoo/.git" ]; then
  say "Downloading Odoo 18 source (shallow clone, ~700 MB)"
  git clone --depth 1 --branch 18.0 https://github.com/odoo/odoo.git "$ODOO_HOME/odoo"
fi
if [ ! -x "$ODOO_HOME/venv/bin/python" ]; then
  say "Creating Odoo's Python environment"
  "$PY" -m venv "$ODOO_HOME/venv"
fi
say "Installing Odoo's Python packages"
# python-ldap needs OpenLDAP headers and SunPower does not use it, so it is skipped.
REQ="$(mktemp)"
grep -viE '^python-ldap' "$ODOO_HOME/odoo/requirements.txt" > "$REQ"
"$ODOO_HOME/venv/bin/pip" install --upgrade pip wheel >/dev/null
"$ODOO_HOME/venv/bin/pip" install -r "$REQ" requests
rm -f "$REQ"

# ---------------------------------------------------------------- odoo.conf
CONF="$ODOO_HOME/odoo.conf"
if [ ! -f "$CONF" ]; then
  say "Writing $CONF"
  cat > "$CONF" <<EOF
[options]
addons_path = $ODOO_HOME/odoo/addons,$ODOO_HOME/odoo/odoo/addons,$REPO/addons
data_dir = $ODOO_HOME/data
db_host = localhost
db_port = 5432
db_user = $USER
http_port = 8069
bin_path = /usr/local/bin
without_demo = all
EOF
else
  say "Keeping existing $CONF (make sure addons_path includes $REPO/addons)"
fi

# ---------------------------------------------------------------- frontend
say "Installing frontend packages"
(cd "$REPO/frontend" && npm install --no-audit --no-fund)

# ---------------------------------------------------------------- wkhtmltopdf
if command -v wkhtmltopdf >/dev/null || [ -x /usr/local/bin/wkhtmltopdf ]; then
  say "wkhtmltopdf found"
else
  cat <<'EOF'

==> One manual step left: wkhtmltopdf (Odoo needs it for every PDF)
    1. Download wkhtmltox-0.12.6-2.macos-cocoa.pkg from
       https://github.com/wkhtmltopdf/packaging/releases/tag/0.12.6-2
    2. Open it to install (it goes to /usr/local/bin/wkhtmltopdf).
    3. On Apple Silicon it also needs Rosetta:  softwareupdate --install-rosetta --agree-to-license
    Everything except PDF printing works without it.
EOF
fi

cat <<EOF

==> Done. Next:
    ODOO_HOME="$ODOO_HOME" $ODOO_HOME/venv/bin/python scripts/rebuild_db.py   # database + demo data
    ./run_odoo.sh                                                             # http://localhost:8069
    (cd frontend && npm run dev)                                              # http://localhost:5173
    ./ai_service/run.sh                                                       # optional AI service, :8000
EOF
