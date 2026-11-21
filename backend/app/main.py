"""SunPower back end (FastAPI). Run:  uvicorn app.main:app --port 8001"""
import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import mailer
from .catalog import seed_catalog, seed_settings
from .db import init_db, session
from .rules import RuleError
from .routers import account, auth, printing, public, staff_admin, staff_ops, staff_sales

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="SunPower", docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.middleware("http")
async def csrf_guard(request: Request, call_next):
    """State-changing API calls must carry X-SunPower: 1 (a cross-site form can't)."""
    if (request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api/")
            and request.headers.get("x-sunpower") != "1"):
        return JSONResponse({"detail": "Missing request header."}, status_code=403)
    return await call_next(request)


@app.exception_handler(RuleError)
async def rule_error(_request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=400)


for r in (public, auth, account, staff_sales, staff_ops, staff_admin, printing):
    app.include_router(r.router)


@app.get("/api/health")
def health():
    return {"ok": True, "service": "SunPower"}


def bootstrap(seed_demo=None):
    init_db()
    with session() as db:
        seed_settings(db)
        seed_catalog(db)
        if seed_demo is None:
            seed_demo = os.environ.get("SUNPOWER_DEMO", "1") == "1"
        if seed_demo and not db.val("SELECT COUNT(*) FROM users"):
            from .seed import load_demo
            load_demo(db)


@app.on_event("startup")
def _startup():
    bootstrap()
    if os.environ.get("SUNPOWER_MAIL_WORKER", "1") == "1":
        mailer.start_worker()
