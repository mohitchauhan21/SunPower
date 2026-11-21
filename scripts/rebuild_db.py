"""Recreate the SunPower database from scratch: India company (INR + GST chart),
install sunpower_solar (+ sunpower_website if present) and load demo data.

WARNING: drops the database first if it already exists.

Run with Odoo's own Python:
  Windows:  & "$env:ODOO_HOME\\venv\\Scripts\\python.exe" scripts\\rebuild_db.py [--no-demo]
  macOS:    ~/odoo18/venv/bin/python scripts/rebuild_db.py [--no-demo]

Settings (environment variables):
  ODOO_HOME    folder holding odoo/ (source) and odoo.conf; default ~/odoo18
  ODOO_CONF    config file; default $ODOO_HOME/odoo.conf
  SUNPOWER_DB  database name; default sunpower
"""
import os
import sys

ODOO_ROOT = os.path.expanduser(os.environ.get("ODOO_HOME") or os.path.join("~", "odoo18"))
CONF = os.environ.get("ODOO_CONF") or os.path.join(ODOO_ROOT, "odoo.conf")
DB = os.environ.get("SUNPOWER_DB") or "sunpower"
sys.path.insert(0, os.path.join(ODOO_ROOT, "odoo"))

import odoo  # noqa: E402
from odoo.service import db as dbservice  # noqa: E402

odoo.tools.config.parse_config(["-c", CONF])

if DB in dbservice.list_dbs(force=True):
    print("Dropping", DB)
    dbservice.exp_drop(DB)

print("Creating", DB, "(country India, admin/admin)")
dbservice.exp_create_database(DB, False, "en_US", "admin", "admin", "in", None)

registry = odoo.modules.registry.Registry(DB)
modules = ["sunpower_solar"]
addons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "addons")
for extra in ("sunpower_website", "sunpower_ai"):
    if os.path.isdir(os.path.join(addons_dir, extra)):
        modules.append(extra)

with registry.cursor() as cr:
    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
    env["ir.module.module"].update_list()
    mods = env["ir.module.module"].search([("name", "in", modules)])
    print("Installing", mods.mapped("name"))
    mods.button_immediate_install()

if "--no-demo" not in sys.argv:
    registry = odoo.modules.registry.Registry.new(DB)
    with registry.cursor() as cr:
        env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
        print("Loading demo data (takes a few minutes)...")
        env["solar.demo.data"].load()
        company = env.company
        print("Done:", company.name, company.currency_id.name, company.chart_template,
              "jobs:", env["sale.order"].search_count([("is_solar_job", "=", True)]))
