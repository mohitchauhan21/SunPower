"""End-to-end API checks on a fresh demo database:  .venv/Scripts/python -m pytest -q"""
import os
import tempfile

import pytest

os.environ["SUNPOWER_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["SUNPOWER_MAIL_WORKER"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.seed import DEMO_CODE, DEMO_PASSWORD  # noqa: E402
from app.security import reset_rate_limits  # noqa: E402

H = {"X-SunPower": "1"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:   # startup seeds the demo data
        yield c


def login(client, email, password=DEMO_PASSWORD):
    reset_rate_limits()
    client.cookies.clear()
    r = client.post("/api/auth/login", json={"login": email, "password": password}, headers=H)
    assert r.json()["ok"], r.json()
    return r.json()


def test_state_changes_need_header(client):
    assert client.post("/api/auth/login", json={"login": "x", "password": "y"}).status_code == 403


def test_every_role_lands_on_its_home(client):
    homes = {"director": "/app", "sales": "/app", "warehouse": "/app", "support": "/app", "tech01": "/app",
             "customer": "/account"}
    for who, home in homes.items():
        me = login(client, "%s@sunpower.demo" % who)
        assert me["home"] == home
        assert me["onboarded"] is False and me["has_recovery_code"] is True


def test_today_feed_for_every_staff_role(client):
    for who in ("director", "sales", "warehouse", "support", "tech01"):
        login(client, "%s@sunpower.demo" % who)
        d = client.get("/api/staff/today").json()
        assert 1 <= len(d["groups"]) <= 5 and len(d["stats"]) <= 4, who
    login(client, "tech01@sunpower.demo")
    jobs = next(g for g in client.get("/api/staff/today").json()["groups"] if g["key"] == "jobs")
    assert jobs["count"] > 0


def test_onboarding_is_shown_once(client):
    login(client, "sales@sunpower.demo")
    assert client.post("/api/auth/onboarded", headers=H).json()["ok"]
    assert client.get("/api/auth/me").json()["onboarded"] is True


def test_signup_needs_strong_password_confirmation_and_code(client):
    client.cookies.clear()
    base = {"name": "New Person", "email": "new.person@example.com", "recovery_code": "4826"}
    weak = client.post("/api/auth/signup", json={**base, "password": "password", "confirm": "password"}, headers=H).json()
    assert not weak["ok"] and weak["field"] == "password"
    mismatch = client.post("/api/auth/signup", json={**base, "password": "Solar#2026x", "confirm": "Solar#2026y"}, headers=H).json()
    assert not mismatch["ok"] and mismatch["field"] == "confirm"
    easy = client.post("/api/auth/signup", json={**base, "recovery_code": "1234", "password": "Solar#2026x", "confirm": "Solar#2026x"}, headers=H).json()
    assert not easy["ok"] and easy["field"] == "recovery_code"
    good = client.post("/api/auth/signup", json={**base, "password": "Solar#2026x", "confirm": "Solar#2026x"}, headers=H).json()
    assert good["ok"] and good["status"] == "created"


def test_forgot_password_with_recovery_code(client):
    reset_rate_limits()
    client.cookies.clear()
    body = {"email": "warehouse@sunpower.demo", "password": "Fresh#Pass9", "confirm": "Fresh#Pass9"}
    wrong = client.post("/api/auth/recover", json={**body, "code": "9999"}, headers=H).json()
    assert not wrong["ok"]
    right = client.post("/api/auth/recover", json={**body, "code": DEMO_CODE}, headers=H).json()
    assert right["ok"], right
    login(client, "warehouse@sunpower.demo", "Fresh#Pass9")
    # brute force is stopped after 5 tries
    reset_rate_limits()
    for _ in range(5):
        client.post("/api/auth/recover", json={**body, "code": "1111"}, headers=H)
    blocked = client.post("/api/auth/recover", json={**body, "code": DEMO_CODE}, headers=H).json()
    assert not blocked["ok"] and "Too many" in blocked["error"]


def test_public_enquiry_and_estimate(client):
    client.cookies.clear()
    est = client.post("/api/sunpower/estimate", json={"units": 360}, headers=H).json()
    assert est["kw"] == 3 and est["subsidy"] == 78000
    r = client.post("/api/sunpower/enquiry", json={"name": "Test Person", "phone": "9000000001"}, headers=H).json()
    assert r["ok"] and r["ref"].startswith("ENQ-")
    assert not client.post("/api/sunpower/enquiry", json={"name": ""}, headers=H).json()["ok"]


def test_director_dashboard_and_report(client):
    login(client, "director@sunpower.demo")
    d = client.get("/api/staff/dashboard?period=year").json()
    assert d["kpi"]["orders_won"] > 0 and d["jobs"]
    assert client.get("/print/report?period=month").status_code == 200


def test_technician_sees_only_own_work(client):
    login(client, "tech01@sunpower.demo")
    jobs = client.get("/api/staff/jobs").json()["rows"]
    assert jobs and all("Ramesh" in (j["crew"] or "") for j in jobs)
    assert client.get("/api/staff/leads").status_code == 403
    assert client.get("/api/staff/dashboard").status_code == 403


def test_installation_needs_checklist_photo_kw_signature(client):
    login(client, "tech01@sunpower.demo")
    job = next(j for j in client.get("/api/staff/jobs").json()["rows"] if j["state"] == "planned")
    jid = job["id"]
    client.post("/api/staff/jobs/%s/start" % jid, headers=H)
    r = client.post("/api/staff/jobs/%s/finish" % jid, headers=H)
    assert r.status_code == 400 and "Checklist" in r.json()["detail"]
    up = client.post("/api/staff/jobs/%s/photos" % jid, headers=H, files={"file": ("roof.png", b"\x89PNG fake", "image/png")})
    assert up.status_code == 200 and up.json()["ok"]


def test_dispatch_blocked_without_advance(client):
    login(client, "sales@sunpower.demo")
    draft = client.get("/api/staff/orders?state=draft").json()["rows"][0]
    assert client.post("/api/staff/orders/%s/confirm" % draft["id"], headers=H).json()["ok"]
    login(client, "warehouse@sunpower.demo", "Fresh#Pass9")
    d = next(x for x in client.get("/api/staff/deliveries?state=waiting").json()["rows"])
    r = client.post("/api/staff/deliveries/%s/validate" % d["id"], json={"serials": {}}, headers=H)
    assert r.status_code == 400 and "advance" in r.json()["detail"]


def test_customer_sees_own_account_and_quote_pdf(client):
    login(client, "customer@sunpower.demo")
    o = client.get("/api/my/overview").json()
    assert o["orders"] and o["warranties"]
    assert client.get(o["orders"][0]["pdf_url"]).status_code == 200
    assert client.get("/api/staff/leads").status_code == 403
