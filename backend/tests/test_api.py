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
from .survey_helper import PNG, fill_survey, payments_on  # noqa: E402,F401


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
    # put the demo password back so later tests (and other test files) can sign in
    reset_rate_limits()
    back = {"email": "warehouse@sunpower.demo", "code": DEMO_CODE, "password": DEMO_PASSWORD, "confirm": DEMO_PASSWORD}
    assert client.post("/api/auth/recover", json=back, headers=H).json()["ok"]


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
    svg = client.post("/api/staff/jobs/%s/photos" % jid, headers=H,
                      files={"file": ("roof.png", b"<svg onload=alert(1)>", "image/png")})
    assert svg.status_code == 400                      # not a real image: refused whatever the label says
    up = client.post("/api/staff/jobs/%s/photos" % jid, headers=H,
                     files={"file": ("roof.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64, "image/png")})
    assert up.status_code == 200 and up.json()["ok"]


def test_dispatch_blocked_without_advance(client, payments_on):
    login(client, "sales@sunpower.demo")
    draft = client.get("/api/staff/orders?state=draft").json()["rows"][0]
    assert client.post("/api/staff/orders/%s/confirm" % draft["id"], headers=H).json()["ok"]
    login(client, "warehouse@sunpower.demo")
    d = next(x for x in client.get("/api/staff/deliveries?state=waiting").json()["rows"])
    r = client.post("/api/staff/deliveries/%s/validate" % d["id"], json={"serials": {}}, headers=H)
    assert r.status_code == 400 and "advance" in r.json()["detail"]


def test_customer_sees_own_account_and_quote_pdf(client):
    login(client, "customer@sunpower.demo")
    o = client.get("/api/my/overview").json()
    assert o["orders"] and o["warranties"]
    assert client.get(o["orders"][0]["pdf_url"]).status_code == 200
    assert client.get("/api/staff/leads").status_code == 403


def test_state_wise_subsidy_and_custom_price(client):
    est = lambda **b: client.post("/api/sunpower/estimate", json=b, headers=H).json()
    assert est(units=360, state="Gujarat")["subsidy"] == 78000          # general state, 3 kW
    assert est(units=360, state="Assam")["subsidy"] == 85800            # special category (+10%)
    assam = est(units=360, state="Assam", topup=True)                   # reported top-up only when asked
    assert (assam["subsidy_central"], assam["subsidy_topup"], assam["subsidy"]) == (85800, 45000, 130800)
    assert est(units=840, state="Gujarat")["subsidy"] == 78000          # central subsidy capped at 3 kW
    custom = est(units=360, state="Uttar Pradesh", topup=True, kw=4, cost_per_kw=55000, tariff=9)
    assert (custom["cost"], custom["subsidy"], custom["net_cost"], custom["custom"]) == (220000, 108000, 112000, True)
    table = client.get("/api/sunpower/subsidy-states").json()
    assert len(table["states"]) == 36 and table["average"]["3"] == 81033


def test_enquiry_checks_phone_state_and_duplicates(client):
    send = lambda **b: client.post("/api/sunpower/enquiry", json=b, headers=H).json()
    assert send(name="Asha Rao", phone="12345")["field"] == "phone"
    assert send(name="Asha Rao", phone="98765 11111", state="Atlantis")["field"] == "state"
    first = send(name="Asha Rao", phone="+91 98765-11111", state="kerala", system_type="off_grid", monthly_bill=3000,
                 estimate={"kw": 3, "cost": 279000, "subsidy": 0, "net_cost": 279000})
    assert first["ok"] and not first.get("duplicate")
    again = send(name="Asha Rao", phone="9876511111")            # same phone pressed twice
    assert again["ok"] and again["duplicate"] and again["id"] == first["id"]
    login(client, "director@sunpower.demo")
    lead = client.get("/api/staff/leads/%s" % first["id"]).json()
    assert lead["phone"] == "+919876511111" and lead["state"] == "Kerala" and "estimated total" in lead["notes"]


def test_off_grid_estimate_has_no_subsidy(client):
    e = client.post("/api/sunpower/estimate", json={"units": 360, "system_type": "off_grid"}, headers=H).json()
    assert e["subsidy"] == 0 and e["cost"] == 3 * (65000 + 28000) and e["system_type"] == "off_grid"


def test_enquiry_progress_is_truthful():
    from app.rules import enquiry_progress
    lead = {"stage": "new", "created_at": "2026-11-22 10:00:00"}
    p = enquiry_progress(lead, None)
    assert p["status"] == "Awaiting confirmation call" and [s["done"] for s in p["steps"]] == [True, False, False, False, False]
    p = enquiry_progress(dict(lead, stage="survey"), {"state": "scheduled", "survey_date": "2026-11-25 10:00:00"})
    assert p["status"].startswith("Survey booked") and [s["done"] for s in p["steps"]][:4] == [True, True, True, False]


# ---------------------------------------------------------------- audit fixes
def test_portal_choice_must_match_the_account(client):
    reset_rate_limits()
    client.cookies.clear()
    r = client.post("/api/auth/login", json={"login": "customer@sunpower.demo", "password": DEMO_PASSWORD, "portal": "team"},
                    headers=H).json()
    assert not r["ok"] and r["field"] == "portal" and "customer account" in r["error"]
    assert not client.get("/api/auth/me").json()["authenticated"]      # no session on a mismatch
    r = client.post("/api/auth/login", json={"login": "sales@sunpower.demo", "password": DEMO_PASSWORD, "portal": "customer"},
                    headers=H).json()
    assert not r["ok"] and "team account" in r["error"]
    r = client.post("/api/auth/login", json={"login": "sales@sunpower.demo", "password": DEMO_PASSWORD, "portal": "team"},
                    headers=H).json()
    assert r["ok"] and r["role"] == "sales"


def test_google_token_is_verified_on_the_server(client):
    providers = client.get("/api/auth/providers").json()
    assert providers[0]["id"] == "google" and "client_secret" not in str(providers)
    r = client.post("/api/auth/google/token", json={"credential": "not-a-real-token"}, headers=H).json()
    assert not r["ok"]


def test_technician_cannot_note_other_peoples_work(client):
    login(client, "director@sunpower.demo")
    others = [j for j in client.get("/api/staff/jobs").json()["rows"] if "Ramesh" not in (j["crew"] or "")]
    login(client, "tech01@sunpower.demo")
    r = client.post("/api/staff/notes", json={"model": "job", "res_id": others[0]["id"], "body": "sneaky"}, headers=H)
    assert r.status_code == 404
    r = client.post("/api/staff/notes", json={"model": "job", "res_id": 999999, "body": "x"}, headers=H)
    assert r.status_code == 404


def test_payments_cannot_exceed_the_balance_or_repeat(client):
    login(client, "sales@sunpower.demo")
    order = next(o for o in client.get("/api/staff/orders", params={"state": "sale"}).json()["rows"]
                 if o["amount_total"] - o["paid"] > 1000)
    left = order["amount_total"] - order["paid"]
    r = client.post("/api/staff/orders/%s/payment" % order["id"], json={"amount": left + 5000, "method": "cash"}, headers=H)
    assert r.status_code == 400 and "owed" in r.json()["detail"]
    ok1 = client.post("/api/staff/orders/%s/payment" % order["id"], json={"amount": 500, "method": "upi"}, headers=H)
    ok2 = client.post("/api/staff/orders/%s/payment" % order["id"], json={"amount": 500, "method": "upi"}, headers=H)
    assert ok1.status_code == 200 and ok2.status_code == 400          # double click: recorded once


def test_online_payment_completes_only_once(client):
    from app.db import session
    from app import rules
    with session() as db:
        o = next(x for x in db.q("SELECT * FROM orders WHERE state = 'sale' ORDER BY id")
                 if x["amount_total"] - rules.order_paid(db, x["id"]) > 200)
        info = rules.start_online_payment(db, o, 100, "balance", None)
        p = db.get("payments", info["payment_id"])
        before = rules.order_paid(db, o["id"])
        rules.complete_online_payment(db, p)
        try:
            rules.complete_online_payment(db, p)      # the same confirmation arriving twice
            raised = False
        except rules.RuleError:
            raised = True
        assert raised and rules.order_paid(db, o["id"]) == before + 100
        db.rollback()


def test_ticket_moves_only_forward(client):
    login(client, "support@sunpower.demo")
    closed = client.get("/api/staff/tickets", params={"stage": "closed"}).json()["rows"]
    if closed:
        r = client.post("/api/staff/tickets/%s/diagnose" % closed[0]["id"], headers=H)
        assert r.status_code == 400
    new = client.post("/api/staff/tickets", json={"customer_id": 1, "description": "Inverter beeping every night",
                                                   "technician_id": 1}, headers=H)
    assert new.status_code == 400                     # user 1 is not a technician


def test_service_invoices_stay_out_of_order_money(client):
    from app.db import session
    from app import rules
    with session() as db:
        o = db.one("SELECT * FROM orders WHERE state = 'sale' ORDER BY id LIMIT 1")
        db.insert("invoices", {"ref": "INV-T", "order_id": o["id"], "customer_id": o["customer_id"], "kind": "service",
                               "amount_untaxed": 1000, "amount_tax": 180, "amount_total": 1180, "date": rules.today()})
        rules.allocate_payments(db, o["id"])
        svc = db.one("SELECT * FROM invoices WHERE ref = 'INV-T'")
        assert svc["amount_paid"] == 0 and svc["state"] == "posted"   # order money never pays a repair invoice
        db.rollback()


def test_emails_escape_names():
    from app import mailer

    class FakeDB:
        def setting(self, k, d=None):
            return d
    html = mailer.branded(FakeDB(), "T", ["Hi <a href='x'>Bob</a>,"])
    assert "<a href" not in html and "&lt;a href" in html


def test_cancelling_a_quote_keeps_the_enquiry(client):
    from app.db import session
    from app import rules
    with session() as db:
        o = db.one("SELECT * FROM orders WHERE state IN ('draft','sent') AND lead_id IS NOT NULL ORDER BY id LIMIT 1")
        if o:
            db.update("leads", o["lead_id"], {"stage": "quoted"})
            rules.cancel_order(db, o, None)
            assert db.val("SELECT stage FROM leads WHERE id = ?", o["lead_id"]) != "lost"
        db.rollback()


def test_refused_dispatch_changes_nothing(client):
    login(client, "director@sunpower.demo")
    waiting = client.get("/api/staff/deliveries", params={"state": "waiting"}).json()["rows"]
    if not waiting:
        return
    d = client.get("/api/staff/deliveries/%s" % waiting[0]["id"]).json()
    stock = {l["product_id"]: l["qty_on_hand"] for l in d["lines"]}
    login(client, "warehouse@sunpower.demo")
    r = client.post("/api/staff/deliveries/%s/validate" % d["id"], json={"serials": {}}, headers=H)
    assert r.status_code == 400
    login(client, "director@sunpower.demo")
    after = client.get("/api/staff/deliveries/%s" % d["id"]).json()
    assert after["state"] == "waiting" and {l["product_id"]: l["qty_on_hand"] for l in after["lines"]} == stock


def test_money_taken_online_is_never_refused():
    from app.db import session
    from app import rules
    with session() as db:
        o = next(x for x in db.q("SELECT * FROM orders WHERE state = 'sale' ORDER BY id")
                 if x["amount_total"] - rules.order_paid(db, x["id"]) > 200)
        due = o["amount_total"] - rules.order_paid(db, o["id"])
        info = rules.start_online_payment(db, o, due, "balance", None)
        db.update("payments", info["payment_id"], {"amount": due + 50})      # bank took a little more
        rules.complete_online_payment(db, db.get("payments", info["payment_id"]))
        assert rules.order_paid(db, o["id"]) >= o["amount_total"]
        db.rollback()


def test_login_error_never_reveals_which_emails_exist(client):
    reset_rate_limits()
    client.cookies.clear()
    a = client.post("/api/auth/login", json={"login": "nobody@nowhere.test", "password": "Wrong@1234"}, headers=H).json()
    b = client.post("/api/auth/login", json={"login": "sales@sunpower.demo", "password": "Wrong@1234"}, headers=H).json()
    assert a["error"] == b["error"]


def test_booking_needs_slot_and_suggests_area_technicians(client):
    login(client, "sales@sunpower.demo")
    lead = client.get("/api/staff/leads", params={"stage": "new"}).json()["rows"][0]
    assert lead["project_ref"].startswith("SP-")
    sug = client.get("/api/staff/leads/%s/technicians" % lead["id"]).json()["rows"]
    assert sug and (not any(t["in_area"] for t in sug) or sug[0]["in_area"])     # area matches come first
    r = client.post("/api/staff/leads/%s/survey" % lead["id"], json={"technician_id": sug[0]["id"], "survey_date": "2020-01-01",
                                                                      "slot": "morning"}, headers=H)
    assert r.status_code == 400                                                  # not in the past
    from datetime import date, timedelta
    day = (date.today() + timedelta(days=3)).isoformat()
    r = client.post("/api/staff/leads/%s/survey" % lead["id"], json={"technician_id": sug[0]["id"], "survey_date": day,
                                                                      "slot": "evening"}, headers=H)
    assert r.status_code == 200
    survey = client.get("/api/staff/surveys/%s" % r.json()["id"]).json()
    assert survey["survey_date"] == day + " 16:00:00"
    detail = client.get("/api/staff/leads/%s" % lead["id"]).json()
    assert detail["booking_confirmed_at"] and detail["stage"] == "survey"
    busy = client.get("/api/staff/leads/%s/technicians" % lead["id"], params={"day": day, "slot": "evening"}).json()["rows"]
    assert "survey" in next(t for t in busy if t["id"] == sug[0]["id"])["busy"]


def _book_and_visit(client, fill=True):
    """Sales books a survey for a new enquiry with tech01; tech01 records the visit. Returns (survey_id, lead_id)."""
    from datetime import date, timedelta
    login(client, "sales@sunpower.demo")
    lid = client.post("/api/staff/leads", json={"contact_name": "Plan Test", "phone": "9811122233", "city": "Pune",
                                                "monthly_bill": 3000, "requested_kw": 3}, headers=H).json()["id"]
    tech = next(t for t in client.get("/api/staff/people", params={"role": "technician"}).json() if "Ramesh" in t["name"])
    day = (date.today() + timedelta(days=4)).isoformat()
    sid = client.post("/api/staff/leads/%s/survey" % lid, json={"technician_id": tech["id"], "survey_date": day, "slot": "morning"},
                      headers=H).json()["id"]
    login(client, "tech01@sunpower.demo")
    if fill:
        fill_survey(client, sid, 3, area=320)
    return sid, lid


def test_technician_builds_quote_and_big_discount_needs_approval(client):
    sid, lid = _book_and_visit(client)
    r = client.post("/api/staff/surveys/%s/quote" % sid, headers=H)
    assert r.status_code == 200, r.text
    oid = r.json()["id"]
    o = client.get("/api/staff/orders/%s" % oid).json()
    assert o["state"] == "sent" and "financials" not in o and not o["can_confirm"]   # goes straight to the customer
    assert "cost" not in str(o["lines"][0].keys())
    line = o["lines"][0]
    assert client.put("/api/staff/orders/%s/lines" % oid, json={"lines": [{"id": line["id"], "qty": 1, "discount": 8}]},
                      headers=H).json()["ok"]
    r = client.post("/api/staff/orders/%s/send" % oid, headers=H)
    assert r.status_code == 400 and "approve" in r.json()["detail"]
    assert client.post("/api/staff/orders/%s/confirm" % oid, headers=H).status_code == 403   # Sales confirms, not technicians
    login(client, "sales@sunpower.demo")
    assert client.get("/api/staff/orders/%s" % oid).json()["can_approve"]
    assert client.post("/api/staff/orders/%s/approve-discount" % oid, headers=H).json()["ok"]
    login(client, "tech01@sunpower.demo")
    assert client.post("/api/staff/orders/%s/send" % oid, headers=H).json()["ok"]
    # another technician can't see this quote
    login(client, "tech02@sunpower.demo")
    assert client.get("/api/staff/orders/%s" % oid).status_code == 404
    assert all(x["id"] != oid for x in client.get("/api/staff/orders").json()["rows"])


def test_customer_pays_in_full_upfront_with_discount():
    from app.db import session
    from app import rules
    with session() as db:
        o = db.one("SELECT * FROM orders WHERE state = 'sent' ORDER BY id LIMIT 1") or db.one(
            "SELECT * FROM orders WHERE state = 'draft' ORDER BY id LIMIT 1")
        if o["state"] == "draft":
            db.update("orders", o["id"], {"state": "sent"})
            o = db.get("orders", o["id"])
        if rules.order_paid(db, o["id"]) > 0:
            db.rollback()
            return
        total = o["amount_total"]
        pay = rules.full_upfront_amount(db, o)
        assert abs(pay - total * 0.98) < 1
        info = rules.start_online_payment(db, o, pay, "full", None)
        rules.complete_online_payment(db, db.get("payments", info["payment_id"]))
        o2 = db.get("orders", o["id"])
        assert o2["state"] == "sale" and abs(o2["amount_total"] - pay) < 1          # discount line makes the total match
        assert rules.advance_due(db, o2) == 0 and rules.order_paid(db, o["id"]) + 1 >= o2["amount_total"]
        db.rollback()


def test_survey_submit_needs_required_fields_and_photos(client):
    sid, _lid = _book_and_visit(client, fill=False)
    client.patch("/api/staff/surveys/%s" % sid, json={"roof_direction": "S", "usable_area_sqft": 300}, headers=H)
    r = client.post("/api/staff/surveys/%s/done" % sid, headers=H)
    assert r.status_code == 400 and "Supply" in r.json()["detail"]
    s = client.get("/api/staff/surveys/%s" % sid).json()
    assert any(m["label"] == "Photo: Meter + nameplate" for m in s["missing"])
    bad = client.patch("/api/staff/surveys/%s" % sid, json={"details": {"phase": "four"}}, headers=H)
    assert bad.status_code == 400
    bad = client.post("/api/staff/surveys/%s/photos" % sid, headers=H, data={"category": "selfie"},
                      files={"file": ("a.png", PNG, "image/png")})
    assert bad.status_code == 400
    fill_survey(client, sid, 3)
    assert client.get("/api/staff/surveys/%s" % sid).json()["missing"] == []
    assert client.post("/api/staff/surveys/%s/done" % sid, headers=H).json()["ok"]


def test_quote_parts_follow_the_survey(client):
    sid, _lid = _book_and_visit(client, fill=False)
    fill_survey(client, sid, 3, dc_cable_m=40, ac_cable_m=30, earth_cable_m=20, conduit_needed=True,
                mounting_type="elevated", structure_height_m=2.5)
    preview = {p["code"]: p["qty"] for p in client.get("/api/staff/surveys/%s" % sid).json()["parts"]}
    # 3 kW kit carries 35 m DC and 21 m AC cable; the site needs 40x2x1.1 = 88 m and 30x1.1 = 33 m
    assert preview == {"CBL-DC4": 53, "CBL-AC4": 12, "ERT-CBL": 22, "CND-25": 77, "STR-ELV": 3}
    oid = client.post("/api/staff/surveys/%s/quote" % sid, headers=H).json()["id"]
    lines = client.get("/api/staff/orders/%s" % oid).json()["lines"]
    extra = {l["description"].split(" (site")[0]: l["qty"] for l in lines if "(site:" in l["description"]}
    assert len(extra) == 5 and 53 in extra.values()


def test_not_feasible_survey_cannot_be_quoted(client):
    sid, _lid = _book_and_visit(client, fill=False)
    fill_survey(client, sid, 3, result="not_feasible", issues=[{"type": "weak_structure", "severity": "critical",
                                                                 "note": "Cracked slab"}])
    r = client.post("/api/staff/surveys/%s/quote" % sid, headers=H)
    assert r.status_code == 400 and "not feasible" in r.json()["detail"]
    assert client.post("/api/staff/surveys/%s/done" % sid, headers=H).json()["ok"]
    s = client.get("/api/staff/surveys/%s" % sid).json()
    assert s["state"] == "done" and s["details"]["issues"][0]["type"] == "weak_structure"


def test_survey_demand_reaches_the_warehouse(client):
    sid, _lid = _book_and_visit(client, fill=False)
    fill_survey(client, sid, 3, dc_cable_m=40, mounting_type="elevated")
    assert client.post("/api/staff/surveys/%s/done" % sid, headers=H).json()["ok"]
    login(client, "warehouse@sunpower.demo")
    d = client.get("/api/staff/demand").json()
    mine = next(x for x in d["surveys"] if x["survey_id"] == sid)
    codes = {i["code"]: i["qty"] for i in mine["items"]}
    assert codes["PNL-540"] > 0 and codes["STR-ELV"] == 3 and codes["CBL-DC4"] == 35 + 53   # package cable + extra the survey measured
    row = next(i for i in d["items"] if i["code"] == "STR-ELV")
    assert row["survey_demand"] >= 3 and "shortfall" in row
    login(client, "tech01@sunpower.demo")   # read-only stock users see totals, never customer names
    assert "surveys" not in client.get("/api/staff/demand").json()


def test_survey_size_must_be_sold_and_fit_the_roof(client):
    sid, _lid = _book_and_visit(client, fill=False)
    fill_survey(client, sid, 45, area=300)
    r = client.post("/api/staff/surveys/%s/done" % sid, headers=H)
    assert r.status_code == 400 and "fits about 3" in r.json()["detail"]   # but the roof must hold it
    r = client.patch("/api/staff/surveys/%s" % sid, json={"recommended_kw": 145}, headers=H)
    assert r.status_code == 400 and "1 and 100 kW" in r.json()["detail"]
    fill_survey(client, sid, 45, area=4500, photos=False)
    r = client.post("/api/staff/surveys/%s/done" % sid, headers=H)
    assert r.status_code == 200, r.text                                # 45 kW gets its own package now
    fill_survey(client, sid, 4, area=300, photos=False)   # 4 kW needs ~400 sq ft
    r = client.post("/api/staff/surveys/%s/quote" % sid, headers=H)
    assert r.status_code == 400 and "fits about 3" in r.json()["detail"]
    assert client.patch("/api/staff/surveys/%s" % sid, json={"recommended_kw": 4545}, headers=H).status_code == 400
    fill_survey(client, sid, 1, area=39, photos=False)   # roof too small for any package
    r = client.post("/api/staff/surveys/%s/quote" % sid, headers=H)
    assert r.status_code == 400 and "too small" in r.json()["detail"]
    fill_survey(client, sid, 3, area=300, photos=False)
    oid = client.post("/api/staff/surveys/%s/quote" % sid, headers=H).json()["id"]
    lines = client.get("/api/staff/orders/%s" % oid).json()["lines"]
    kit = next(l for l in lines if "Solar System" in l["description"])
    assert kit["tax_rate"] == 5                                        # GST on solar equipment since 22 Sep 2025


def test_package_parts_cant_be_retired_and_install_needs_the_kit(client):
    login(client, "warehouse@sunpower.demo")
    pnl = next(p for p in client.get("/api/staff/products").json()["rows"] if p["code"] == "PNL-540")
    r = client.delete("/api/staff/products/%s" % pnl["id"], headers=H)
    assert r.status_code == 400 and "package" in r.json()["detail"]
    login(client, "director@sunpower.demo")
    from datetime import date
    job = next(j for j in client.get("/api/staff/jobs").json()["rows"] if j["state"] == "planned")
    det = client.get("/api/staff/jobs/%s" % job["id"]).json()
    client.patch("/api/staff/jobs/%s" % job["id"], json={"scheduled_at": date.today().isoformat() + "T09:00"}, headers=H)
    r = client.post("/api/staff/jobs/%s/start" % job["id"], headers=H)
    if not det.get("dispatched"):
        assert r.status_code == 400 and "shipped" in r.json()["detail"]


def test_large_system_gets_its_own_package(client):
    sid, _lid = _book_and_visit(client, fill=False)
    fill_survey(client, sid, 35, area=3600)
    preview = client.get("/api/staff/surveys/%s" % sid).json()
    assert preview["missing"] == []
    oid = client.post("/api/staff/surveys/%s/quote" % sid, headers=H).json()["id"]
    o = client.get("/api/staff/orders/%s" % oid).json()
    kit_line = next(l for l in o["lines"] if "Solar System 35 kW" in l["description"])
    login(client, "warehouse@sunpower.demo")
    rows = client.get("/api/staff/products").json()["rows"]
    kit = next(p for p in rows if p["is_kit"] and p["kw"] == 35 and p["system_type"] == "on_grid")
    parts = {l["code"]: l["qty"] for l in client.get("/api/staff/kits/%s" % kit["id"]).json()["lines"]}
    assert parts["PNL-540"] == 65 and parts["INV-35KW"] == 1 and parts["STR-1KW"] == 35   # 35 kW / 540 W panels
    assert kit_line["price_unit"] > 0
