#!/usr/bin/env bash
# Starts Odoo 18 with the SunPower addons on macOS/Linux (counterpart of run_odoo.ps1).
# Expects the layout made by scripts/setup_mac.sh: $ODOO_HOME/{odoo,venv,odoo.conf}.
#
#   ./run_odoo.sh                 -> http://localhost:8069
#   ./run_odoo.sh --update        -> upgrade the SunPower modules first
#   ./run_odoo.sh --db mydb       -> use another database (default: sunpower)
set -euo pipefail

ODOO_HOME="${ODOO_HOME:-$HOME/odoo18}"
PG_FORMULA="${PG_FORMULA:-postgresql@16}"
DB="${SUNPOWER_DB:-sunpower}"
UPDATE=""

while [ $# -gt 0 ]; do
  case "$1" in
    -u|--update) UPDATE="sunpower_solar,sunpower_website,sunpower_ai"; shift ;;
    -d|--db) DB="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

for f in "$ODOO_HOME/venv/bin/python" "$ODOO_HOME/odoo/odoo-bin" "$ODOO_HOME/odoo.conf"; do
  [ -e "$f" ] || { echo "Missing $f. Run scripts/setup_mac.sh first (or set ODOO_HOME)." >&2; exit 1; }
done

# Start PostgreSQL if it is not running (Homebrew service; the formula is keg-only).
command -v brew >/dev/null && export PATH="$(brew --prefix "$PG_FORMULA")/bin:$PATH"
if command -v brew >/dev/null && ! pg_isready -q -h localhost 2>/dev/null; then
  brew services start "$PG_FORMULA" >/dev/null || true
  for _ in $(seq 1 20); do pg_isready -q -h localhost 2>/dev/null && break; sleep 1; done
fi

ARGS=("$ODOO_HOME/odoo/odoo-bin" -c "$ODOO_HOME/odoo.conf" -d "$DB")
[ -n "$UPDATE" ] && ARGS+=(-u "$UPDATE")
exec "$ODOO_HOME/venv/bin/python" "${ARGS[@]}"
