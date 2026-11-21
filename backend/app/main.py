"""SunPower back end (FastAPI). Run:  uvicorn app.main:app --port 8001

WHAT THIS FILE DOES
  This is the entry point. `uvicorn` (the web server program) imports this module
  and serves the `app` object defined below. It:
    1. loads optional settings from backend/.env (e.g. Google sign-in keys),
    2. creates the FastAPI application,
    3. adds a security check that runs before every request (csrf_guard),
    4. turns business-rule errors into friendly 400 responses,
    5. plugs in all the routers (each router = a group of URLs, see app/routers/),
    6. on start-up: creates the database tables, fills the catalogue and, the first
       time, the demo data, then starts the background email sender.

FastAPI in one sentence: a Python library where you write a normal function and
put @app.get("/path") above it; FastAPI then calls that function when a browser
requests that path, and turns the returned dict into JSON.
"""
import logging                      # prints INFO / WARNING messages to the console
import os                           # environment variables
from pathlib import Path


def _load_env_file():
    """KEY=value lines from backend/.env (e.g. GOOGLE_CLIENT_ID). Real environment variables win."""
    env = Path(__file__).resolve().parent.parent / ".env"        # backend/.env
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            # skip empty lines and "# comments"; a setting line must contain "="
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)                  # split only at the first "="
                # setdefault: only set it if it isn't already set by the real environment.
                # .strip('"').strip("'") removes optional quotes around the value.
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# Runs at import time, before the other modules read os.environ.
_load_env_file()

from fastapi import FastAPI, Request             # noqa: E402  (imported after loading .env on purpose)
from fastapi.responses import JSONResponse

from . import mailer                             # background email sender
from .catalog import seed_catalog, seed_settings # products/packages and default settings
from .db import init_db, session                 # create tables; open a DB block
from .rules import RuleError                     # the error type business rules raise
from .routers import account, auth, printing, public, staff_admin, staff_ops, staff_sales

# Show log lines like "2026-11-21 10:00:00 INFO sunpower.mail: ..." in the console.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# The application object. docs_url: interactive API documentation at /api/docs.
app = FastAPI(title="SunPower", docs_url="/api/docs", openapi_url="/api/openapi.json")


# A *middleware* wraps every request: it runs before the endpoint and can stop it.
# `async def` = an asynchronous function (FastAPI can run many of these at once);
# `await call_next(request)` = "now let the request continue to its endpoint".
@app.middleware("http")
async def csrf_guard(request: Request, call_next):
    """State-changing API calls must carry X-SunPower: 1 (a cross-site form can't).

    CSRF ("cross-site request forgery") = another website tricking your browser into
    sending a request to SunPower with your cookie. A plain HTML form on another site
    cannot add custom headers, so requiring this header blocks that attack.
    Our own website adds it to every call (frontend/src/api.js).
    """
    if (request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api/")
            and request.headers.get("x-sunpower") != "1"):
        return JSONResponse({"detail": "Missing request header."}, status_code=403)
    return await call_next(request)


# When any code raises RuleError("message") (rules.py), answer with HTTP 400 and
# {"detail": "message"} so the website can show the message in a toast.
@app.exception_handler(RuleError)
async def rule_error(_request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=400)


# Plug in every group of URLs. Each module has a `router` with its own prefix
# (/api/sunpower, /api/auth, /api/my, /api/staff, /print).
for r in (public, auth, account, staff_sales, staff_ops, staff_admin, printing):
    app.include_router(r.router)


@app.get("/api/health")
def health():
    """Quick "is the server up?" check."""
    return {"ok": True, "service": "SunPower"}


def bootstrap(seed_demo=None):
    """Prepare the database: tables, default settings, catalogue and (first run) demo data.
    seed_demo=None means "decide from the SUNPOWER_DEMO environment variable" (default on)."""
    init_db()
    with session() as db:                       # one transaction for all of it
        seed_settings(db)                       # default company settings (only missing ones)
        seed_catalog(db)                        # components and packages (only the first time)
        if seed_demo is None:
            seed_demo = os.environ.get("SUNPOWER_DEMO", "1") == "1"
        # Demo data only goes into an empty database (no users yet).
        if seed_demo and not db.val("SELECT COUNT(*) FROM users"):
            from .seed import load_demo         # imported here so it only loads when needed
            load_demo(db)


# Runs once when uvicorn starts the app.
@app.on_event("startup")
def _startup():
    bootstrap()
    # The email worker is a background thread; tests switch it off with SUNPOWER_MAIL_WORKER=0.
    if os.environ.get("SUNPOWER_MAIL_WORKER", "1") == "1":
        mailer.start_worker()
