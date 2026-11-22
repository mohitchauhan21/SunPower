"""The whole customer journey through the API, one role at a time, on the shared test database:
enquiry -> screening -> survey -> quote -> online acceptance + advance -> pack -> dispatch -> delivered
-> installation -> certificate -> balance -> subsidy -> service request -> customer confirms the fix."""
import os
import tempfile
from datetime import date, timedelta

import pytest

os.environ.setdefault("SUNPOWER_DB", os.path.join(tempfile.mkdtemp(), "test.db"))
os.environ["SUNPOWER_MAIL_WORKER"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.seed import DEMO_PASSWORD  # noqa: E402
from app.security import reset_rate_limits  # noqa: E402

H = {"X-SunPower": "1"}
from .survey_helper import fill_survey, payments_on  # noqa: E402,F401
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
SIGNATURE = "data:image/png;base64,iVBORw0KGgo="


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def as_(client, who):
    reset_rate_limits()
    client.cookies.clear()
    r = client.post("/api/auth/login", json={"login": "%s@sunpower.demo" % who, "password": DEMO_PASSWORD}, headers=H)
    assert r.json()["ok"], r.json()


def ok(r):
    assert r.status_code == 200, r.text
    body = r.json()
    assert not (isinstance(body, dict) and body.get("ok") is False), body
    return body


def test_full_customer_journey(client, payments_on):
    global TECH01
    as_(client, "tech01")
    TECH01 = client.get("/api/auth/me").json()["id"]
    # 1. The signed-in customer books a survey on the website
    as_(client, "customer")
    day = (date.today() + timedelta(days=5)).isoformat()
    enq = ok(client.post("/api/sunpower/enquiry", json={
        "name": "Journey Customer", "phone": "9822001122", "state": "Gujarat", "city": "Ahmedabad", "system_kw": 3,
        "monthly_bill": 3000, "subsidy": True, "preferred_date": day, "preferred_slot": "morning"}, headers=H))
    lid = enq["id"]
    mine = ok(client.get("/api/my/overview"))
    assert any(e["id"] == lid for e in mine["enquiries"])

    # 2. Sales screens the enquiry and books the survey with a technician
    as_(client, "sales")
    ok(client.patch("/api/staff/leads/%s" % lid, json={"roof_area_sqft": 350, "grid_suitable": "yes"}, headers=H))
    tech = {"id": TECH01}
    sid = ok(client.post("/api/staff/leads/%s/survey" % lid, json={"technician_id": tech["id"], "survey_date": day,
                                                                    "slot": "morning"}, headers=H))["id"]
    lead = ok(client.get("/api/staff/leads/%s" % lid))
    assert lead["stage"] == "survey"

    # 3. Survey visited and approved, quote drafted, sent
    fill_survey(client, sid, 3, area=340)
    ok(client.post("/api/staff/surveys/%s/done" % sid, headers=H))
    ok(client.post("/api/staff/surveys/%s/approve" % sid, headers=H))
    oid = ok(client.post("/api/staff/leads/%s/quote" % lid, headers=H))["id"]
    order = ok(client.get("/api/staff/orders/%s" % oid))
    assert order["state"] == "draft" and order["lines"]
    ok(client.post("/api/staff/orders/%s/send" % oid, headers=H))
    assert ok(client.get("/api/staff/leads/%s" % lid))["stage"] == "quoted"

    # 4. The customer accepts online and pays the advance (test payment)
    as_(client, "customer")
    q = ok(client.get("/api/my/quote/%s" % oid))
    assert q["quote_pending"]
    pay = ok(client.post("/api/my/quote/%s/accept" % oid, json={"name": "Journey Customer", "plan": "advance"}, headers=H))
    assert pay["mode"] == "test" and pay["amount"] > 0
    ok(client.post("/api/my/payment/test/confirm", json={"payment_id": pay["payment_id"], "card": "4111111111111111"},
                   headers=H))
    q = ok(client.get("/api/my/quote/%s" % oid))
    assert q["paid"] >= pay["amount"] - 0.5 and q["advance_due"] == 0

    # 5. Sales sees the confirmed order; the director assigns the crew
    as_(client, "sales")
    order = ok(client.get("/api/staff/orders/%s" % oid))
    assert order["state"] == "sale"
    as_(client, "director")
    job = next(j for j in ok(client.get("/api/staff/jobs"))["rows"] if j["order_ref"] == order["ref"])
    ok(client.patch("/api/staff/jobs/%s" % job["id"], json={"techs": [tech["id"]]}, headers=H))

    # 6. Warehouse packs, dispatches (serials), marks delivered
    as_(client, "warehouse")
    d = next(x for x in ok(client.get("/api/staff/deliveries"))["rows"] if x["order_ref"] == order["ref"])
    assert d["state"] == "ready"
    ok(client.post("/api/staff/deliveries/%s/pack" % d["id"], headers=H))
    det = ok(client.get("/api/staff/deliveries/%s" % d["id"]))
    assert det["state"] == "packed"
    serials = {}
    for l in det["lines"]:
        if l["tracking"] == "serial":
            serials[str(l["id"])] = l["available"][:int(l["qty"])] or ["WF-%s-%d" % (l["id"], i) for i in range(int(l["qty"]))]
        elif l["tracking"] == "lot":
            serials[str(l["id"])] = (l["available"] or ["LOT-WF"])[:1]
    r = ok(client.post("/api/staff/deliveries/%s/validate" % d["id"], json={"serials": serials}, headers=H))
    assert r["units"] > 0
    ok(client.post("/api/staff/deliveries/%s/deliver" % d["id"], json={"note": "Left with owner"}, headers=H))
    assert ok(client.get("/api/staff/deliveries/%s" % d["id"]))["state"] == "delivered"
    # a delivered kit can't be dispatched again
    assert client.post("/api/staff/deliveries/%s/validate" % d["id"], json={"serials": serials}, headers=H).status_code == 400

    # 7. Installation day comes (moved to today for the test); the assigned technician installs and finishes
    as_(client, "director")
    ok(client.patch("/api/staff/jobs/%s" % job["id"], json={"scheduled_at": date.today().isoformat() + "T09:00"}, headers=H))
    as_(client, "tech01")
    jid = job["id"]
    ok(client.post("/api/staff/jobs/%s/start" % jid, headers=H))
    ok(client.patch("/api/staff/jobs/%s" % jid, json={"chk_stands": True, "chk_panels": True, "chk_wiring": True,
                                                       "chk_earthing": True, "chk_generation": True, "kw_confirmed": 3,
                                                       "signed_by": "Journey Customer", "signature": SIGNATURE}, headers=H))
    ok(client.post("/api/staff/jobs/%s/photos" % jid, files={"file": ("roof.png", PNG, "image/png")}, headers=H))
    ok(client.post("/api/staff/jobs/%s/finish" % jid, headers=H))
    assert ok(client.get("/api/staff/jobs/%s" % jid))["state"] == "done"
    assert client.get("/print/certificate/%s" % jid).status_code == 200

    # 8. The customer sees the installation and warranties, then pays the balance
    as_(client, "customer")
    mine = ok(client.get("/api/my/overview"))
    assert any(w["order_id"] == oid for w in mine["warranties"]) if mine["warranties"] and "order_id" in mine["warranties"][0] else mine["warranties"]
    bal = ok(client.post("/api/my/order/pay", json={"order_id": oid, "kind": "balance"}, headers=H))
    ok(client.post("/api/my/payment/test/confirm", json={"payment_id": bal["payment_id"], "card": "4111111111111111"},
                   headers=H))
    q = ok(client.get("/api/my/quote/%s" % oid))
    assert abs(q["total"] - q["paid"]) < 1

    # 9. Subsidy paperwork from documents to disbursal
    as_(client, "sales")
    sub = next(s for s in ok(client.get("/api/staff/subsidies"))["rows"] if s.get("order_ref") == order["ref"])
    assert client.post("/api/staff/subsidies/%s/apply" % sub["id"], headers=H).status_code == 400   # documents first
    ok(client.patch("/api/staff/subsidies/%s" % sub["id"], json={"doc_id_proof": True, "doc_bill": True, "doc_bank": True},
                    headers=H))
    for action in ("apply", "inspection", "approve", "disburse"):
        ok(client.post("/api/staff/subsidies/%s/%s" % (sub["id"], action), headers=H))
    assert ok(client.get("/api/staff/subsidies/%s" % sub["id"]))["state"] == "disbursed"

    # 10. The customer reports a fault on a warrantied item; the service desk fixes it; the customer confirms
    as_(client, "customer")
    mine = ok(client.get("/api/my/overview"))
    w = mine["warranties"][0]
    t = ok(client.post("/api/my/complaint", json={"warranty_id": w["id"], "description": "Inverter shows a red light"},
                       headers=H))
    as_(client, "support")
    tid = t["id"]
    ok(client.patch("/api/staff/tickets/%s" % tid, json={"technician_id": tech["id"]}, headers=H))
    ok(client.post("/api/staff/tickets/%s/diagnose" % tid, headers=H))
    ok(client.post("/api/staff/tickets/%s/repair" % tid, headers=H))
    part = next(p for p in ok(client.get("/api/staff/products"))["rows"] if p["tracking"] == "none" and p["qty_on_hand"] > 0)
    ok(client.patch("/api/staff/tickets/%s" % tid, json={"resolution": "Replaced the DC isolator", "labour_hours": 1,
                                                          "lines": [{"product_id": part["id"], "qty": 1}]}, headers=H))
    ok(client.post("/api/staff/tickets/%s/resolve" % tid, headers=H))
    assert ok(client.get("/api/staff/tickets/%s" % tid))["stage"] == "awaiting"
    as_(client, "customer")
    ok(client.post("/api/my/ticket/confirm", json={"ticket_id": tid}, headers=H))
    assert next(x for x in ok(client.get("/api/my/overview"))["tickets"] if x["id"] == tid)["stage"] == "closed"

    # 11. The director's numbers include this order
    as_(client, "director")
    dash = ok(client.get("/api/staff/dashboard", params={"period": "month"}))
    assert dash


def test_bad_input_types_are_refused_not_crashing(client):
    """Fields of the wrong type (numbers for text, text for numbers, lists, NaN) get a 400, never a 500."""
    as_(client, "director")
    lead = ok(client.get("/api/staff/leads"))["rows"][0]
    for body in ({"contact_name": 5, "phone": True}, {"monthly_bill": "abc"}, {"salesperson_id": 0},
                 {"requested_kw": "nan"}, {"notes": ["x"]}):
        r = client.patch("/api/staff/leads/%s" % lead["id"], json=body, headers=H)
        assert r.status_code in (200, 400), (body, r.status_code, r.text)
    assert client.post("/api/staff/customers", json={"name": 5, "phone": 98, "email": True}, headers=H).status_code in (200, 400)
    assert client.post("/api/staff/notes", json={"model": {}, "res_id": "abc", "body": 1}, headers=H).status_code == 400
    assert client.post("/api/staff/notes", json={"model": [], "res_id": 1, "body": "hi"}, headers=H).status_code == 400
    assert client.post("/api/sunpower/enquiry", json={"name": 1, "phone": [], "monthly_bill": "nan"}, headers=H).status_code == 200
    tid = ok(client.get("/api/staff/tickets"))["rows"][0]["id"]
    assert client.patch("/api/staff/tickets/%s" % tid, json={"technician_id": 0}, headers=H).status_code == 400
    assert client.patch("/api/staff/tickets/%s" % tid, json={"lines": "not a list"}, headers=H).status_code == 400
    did = ok(client.get("/api/staff/deliveries"))["rows"][0]["id"]
    for serials in ("abc", [1, 2], {"1": 5}, {"1": [5, None]}):
        r = client.post("/api/staff/deliveries/%s/validate" % did, json={"serials": serials, "override": True}, headers=H)
        assert r.status_code == 400, (serials, r.status_code, r.text)


def _draft_quote(client, name):
    """Signed in as the Director: a new enquiry taken through an approved survey to a draft quote. Returns the order."""
    as_(client, "director")
    lid = ok(client.post("/api/staff/leads", json={"contact_name": name, "phone": "9822003344", "requested_kw": 2},
                         headers=H))["id"]
    ok(client.patch("/api/staff/leads/%s" % lid, json={"roof_area_sqft": 300, "grid_suitable": "yes"}, headers=H))
    sid = ok(client.post("/api/staff/leads/%s/survey" % lid, json={"technician_id": client.get("/api/staff/people").json()[0]["id"],
                         "survey_date": (date.today() + timedelta(days=2)).isoformat(), "slot": "morning"}, headers=H))["id"]
    fill_survey(client, sid, 2)
    ok(client.post("/api/staff/surveys/%s/done" % sid, headers=H))
    ok(client.post("/api/staff/surveys/%s/approve" % sid, headers=H))
    return ok(client.get("/api/staff/orders/%s" % ok(client.post("/api/staff/leads/%s/quote" % lid, headers=H))["id"]))


def test_quote_discount_must_be_a_real_number(client):
    draft = _draft_quote(client, "Disc Test")
    line = ok(client.get("/api/staff/orders/%s" % draft["id"]))["lines"][0]
    for disc in ("nan", "inf", "abc"):
        r = client.put("/api/staff/orders/%s/lines" % draft["id"], json={"lines": [{"id": line["id"], "qty": 1, "discount": disc}]},
                       headers=H)
        assert r.status_code == 400, (disc, r.text)
    assert ok(client.get("/api/staff/orders/%s" % draft["id"]))["amount_total"] == draft["amount_total"]


def test_number_settings_are_validated(client):
    as_(client, "director")
    for key, bad in (("labour_rate", "abc"), ("quote_valid_days", "0"), ("advance_pct", "150"), ("smtp_port", "x")):
        assert client.put("/api/staff/settings", json={key: bad}, headers=H).status_code == 400, key
    s = ok(client.get("/api/staff/settings"))
    assert s["labour_rate"] not in ("abc",) and s["advance_pct"] != "150"


def test_job_kw_and_dates_are_validated(client):
    as_(client, "director")
    job = next(j for j in ok(client.get("/api/staff/jobs"))["rows"] if j["state"] != "done")
    assert client.patch("/api/staff/jobs/%s" % job["id"], json={"kw_confirmed": "three"}, headers=H).status_code == 400
    assert client.patch("/api/staff/jobs/%s" % job["id"], json={"scheduled_at": "soon"}, headers=H).status_code == 400
    ok(client.patch("/api/staff/jobs/%s" % job["id"], json={"scheduled_at": "2030-01-05T10:30"}, headers=H))
    assert ok(client.get("/api/staff/jobs/%s" % job["id"]))["scheduled_at"] == "2030-01-05 10:30:00"
    r = client.patch("/api/staff/jobs/%s" % job["id"], json={"scheduled_at": "2020-01-05 10:30:00"}, headers=H)
    assert r.status_code == 400 and "past" in r.json()["detail"]
    ok(client.patch("/api/staff/jobs/%s" % job["id"], json={"scheduled_at": "2030-01-05 10:30:00", "notes": "same date"}, headers=H))


def test_acceptance_is_kept_when_online_payment_is_off(client, payments_on):
    """Accepting a quote is saved even when payment can't start (online payment switched off)."""
    from app.db import session
    oid = _draft_quote(client, "Accept Test")["id"]
    with session() as db:   # give the quote to the demo customer
        db.update("orders", oid, {"customer_id": db.val("SELECT customer_id FROM users WHERE email = 'customer@sunpower.demo'")})
    ok(client.post("/api/staff/orders/%s/send" % oid, headers=H))
    with session() as db:
        db.set_setting("test_payments", "0")
    try:
        as_(client, "customer")
        r = client.post("/api/my/quote/%s/accept" % oid, json={"name": "Test Person", "plan": "advance"}, headers=H).json()
        assert r["ok"] is False and r["accepted"] is True and "isn't switched on" in r["error"]
        assert ok(client.get("/api/my/quote/%s" % oid))["accepted_by"] == "Test Person"
    finally:
        with session() as db:
            db.set_setting("test_payments", "1")


def test_dashboard_periods_start_at_local_midnight(client):
    """Event times are stored in UTC; "today" must still count an enquiry made at 00:10 local time."""
    from datetime import datetime, time, timezone
    from app.db import session
    as_(client, "director")
    before = ok(client.get("/api/staff/dashboard", params={"period": "today"}))["kpi"]["leads_new"]
    just_after_midnight = datetime.combine(date.today(), time(0, 10)).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with session() as db:
        lid = db.insert("leads", {"ref": "ENQ-TZ", "contact_name": "Midnight", "phone": "+919800000077", "stage": "new",
                                  "channel": "web", "system_type": "on_grid", "created_at": just_after_midnight})
    try:
        assert ok(client.get("/api/staff/dashboard", params={"period": "today"}))["kpi"]["leads_new"] == before + 1
    finally:
        with session() as db:
            db.exec("DELETE FROM leads WHERE id = ?", lid)


def test_reschedule_survey_moves_it_between_technicians(client):
    """Sales moves a booked visit to another day and technician: it leaves the first technician's
    list and dashboard count and appears on the second's."""
    ids = {}
    for who in ("tech01", "tech02"):
        as_(client, who)
        ids[who] = client.get("/api/auth/me").json()["id"]
    as_(client, "sales")
    lid = ok(client.post("/api/staff/leads", json={"contact_name": "Move Me", "phone": "9822005566", "city": "Surat"}, headers=H))["id"]
    d1, d2 = (date.today() + timedelta(days=3)).isoformat(), (date.today() + timedelta(days=6)).isoformat()
    sid = ok(client.post("/api/staff/leads/%s/survey" % lid, json={"technician_id": ids["tech01"], "survey_date": d1, "slot": "morning"},
                         headers=H))["id"]

    def visits(who):
        as_(client, who)
        rows = [s["id"] for s in ok(client.get("/api/staff/surveys"))["rows"]]
        count = next((i["count"] for i in ok(client.get("/api/staff/summary")).get("items", []) if i.get("label") == "My surveys to visit"), None)
        return sid in rows, count

    before1, before2 = visits("tech01"), visits("tech02")
    assert before1[0] and not before2[0]

    as_(client, "sales")
    sug = ok(client.get("/api/staff/leads/%s/technicians" % lid, params={"day": d1, "slot": "morning", "skip": sid}))["rows"]
    assert "survey" not in next(t for t in sug if t["id"] == ids["tech01"])["busy"]      # its own slot doesn't count as busy
    assert client.post("/api/staff/surveys/%s/reschedule" % sid, json={"technician_id": ids["tech01"], "survey_date": d1, "slot": "morning"},
                       headers=H).status_code == 400                                        # nothing changed
    assert client.post("/api/staff/surveys/%s/reschedule" % sid, json={"technician_id": ids["tech02"], "survey_date": "2020-01-01",
                       "slot": "morning"}, headers=H).status_code == 400                    # not in the past
    ok(client.post("/api/staff/surveys/%s/reschedule" % sid, json={"technician_id": ids["tech02"], "survey_date": d2, "slot": "evening"},
                   headers=H))
    s = ok(client.get("/api/staff/surveys/%s" % sid))
    assert s["technician_id"] == ids["tech02"] and s["survey_date"] == d2 + " 16:00:00"
    assert any("rescheduled" in n["body"] for n in ok(client.get("/api/staff/leads/%s" % lid))["notes_log"])

    after1, after2 = visits("tech01"), visits("tech02")
    assert not after1[0] and after2[0]
    if before1[1] is not None:
        assert after1[1] == before1[1] - 1 and after2[1] == (before2[1] or 0) + 1

    # technicians can't reschedule
    assert client.post("/api/staff/surveys/%s/reschedule" % sid, json={"technician_id": ids["tech01"], "survey_date": d2, "slot": "morning"},
                       headers=H).status_code == 403


def test_technician_dashboard_matches_the_linked_lists(client):
    """Every card on the technician's Today page links to a list with the same filter,
    and that list holds exactly the same records (no fixed or made-up numbers)."""
    from urllib.parse import parse_qsl, urlsplit
    api = {"/app/jobs": "/api/staff/jobs", "/app/surveys": "/api/staff/surveys", "/app/service": "/api/staff/tickets"}
    as_(client, "tech01")
    groups = ok(client.get("/api/staff/today"))["groups"]
    assert {g["key"] for g in groups} == {"jobs", "visits", "repairs"}
    for g in groups:
        u = urlsplit(g["path"])
        listed = ok(client.get(api[u.path], params=dict(parse_qsl(u.query))))
        assert len(listed["rows"]) == g["count"], (g["key"], g["path"], len(listed["rows"]), g["count"])
        key = dict(parse_qsl(u.query)).popitem()[1]
        assert listed["counts"].get(key, 0) == g["count"], (g["key"], listed["counts"])   # the filter chip shows the same number
        for it in g["items"]:
            assert "· ·" not in it["sub"]
            assert it["tag"] in ("Today", "Tomorrow", "On site", "Not scheduled", "Urgent") or it["tag"].startswith(("In ", "Overdue")) \
                or it["tag"].endswith("d open"), it["tag"]


def test_survey_to_warranty_without_payment(client):
    """Payment step skipped (the default for now): survey -> quote sent automatically -> customer accepts =
    confirmed -> warehouse ships with serials, no advance -> surveyor installs on the day -> warranties start."""
    as_(client, "tech01")
    tech_id = client.get("/api/auth/me").json()["id"]
    as_(client, "customer")
    day = (date.today() + timedelta(days=3)).isoformat()
    lid = ok(client.post("/api/sunpower/enquiry", json={
        "name": "Flow Customer", "phone": "9822003344", "state": "Gujarat", "city": "Surat", "system_kw": 3,
        "monthly_bill": 3000, "preferred_date": day, "preferred_slot": "morning"}, headers=H))["id"]
    as_(client, "sales")
    sid = ok(client.post("/api/staff/leads/%s/survey" % lid, json={"technician_id": tech_id, "survey_date": day,
                                                                    "slot": "morning"}, headers=H))["id"]
    as_(client, "tech01")
    fill_survey(client, sid, 3)
    oid = ok(client.post("/api/staff/surveys/%s/quote" % sid, headers=H))["id"]
    assert ok(client.get("/api/staff/orders/%s" % oid))["state"] == "sent"          # straight to the customer

    as_(client, "customer")
    r = ok(client.post("/api/my/quote/%s/accept" % oid, json={"name": "Flow Customer", "plan": "advance"}, headers=H))
    assert r["confirmed"]

    as_(client, "director")
    order = ok(client.get("/api/staff/orders/%s" % oid))
    assert order["state"] == "sale"
    job = next(j for j in ok(client.get("/api/staff/jobs"))["rows"] if j["order_ref"] == order["ref"])
    assert tech_id in [t["id"] for t in ok(client.get("/api/staff/jobs/%s" % job["id"]))["techs"]]   # surveyor installs
    assert not job["scheduled_at"]                                                     # waits for Sales
    as_(client, "sales")
    day = (date.today() + timedelta(days=4)).isoformat()
    ok(client.post("/api/staff/orders/%s/schedule-installation" % oid, json={"scheduled_at": day + "T10:00"}, headers=H))
    assert ok(client.get("/api/staff/jobs/%s" % job["id"]))["scheduled_at"].startswith(day)
    past = client.post("/api/staff/orders/%s/schedule-installation" % oid, json={"scheduled_at": "2020-01-01T10:00"}, headers=H)
    assert past.status_code == 400
    as_(client, "tech01")
    assert client.post("/api/staff/orders/%s/schedule-installation" % oid, json={"scheduled_at": day + "T10:00"},
                       headers=H).status_code in (403, 404)

    as_(client, "warehouse")
    d = next(x for x in ok(client.get("/api/staff/deliveries"))["rows"] if x["order_ref"] == order["ref"])
    assert d["state"] == "ready"                                                      # no advance needed for now
    det = ok(client.get("/api/staff/deliveries/%s" % d["id"]))
    serials = {}
    for l in det["lines"]:
        if l["tracking"] == "serial":
            serials[str(l["id"])] = l["available"][:int(l["qty"])]
        elif l["tracking"] == "lot":
            serials[str(l["id"])] = (l["available"] or ["LOT-FLOW"])[:1]
    assert ok(client.post("/api/staff/deliveries/%s/validate" % d["id"], json={"serials": serials}, headers=H))["units"] > 0
    as_(client, "director")
    assert not [w for w in ok(client.get("/api/staff/warranties"))["rows"] if w.get("order_ref") == order["ref"]]  # not yet

    as_(client, "tech01")
    early = client.post("/api/staff/jobs/%s/start" % job["id"], headers=H)
    assert early.status_code == 400 and "scheduled" in early.json()["detail"]
    as_(client, "director")
    ok(client.patch("/api/staff/jobs/%s" % job["id"], json={"scheduled_at": date.today().isoformat() + "T09:00"}, headers=H))
    as_(client, "tech01")
    jid = job["id"]
    ok(client.post("/api/staff/jobs/%s/start" % jid, headers=H))
    ok(client.patch("/api/staff/jobs/%s" % jid, json={"chk_stands": True, "chk_panels": True, "chk_wiring": True,
                                                       "chk_earthing": True, "chk_generation": True, "kw_confirmed": 3,
                                                       "signed_by": "Flow Customer", "signature": "data:image/png;base64,iVBORw0KGgo="},
                    headers=H))
    ok(client.post("/api/staff/jobs/%s/photos" % jid, files={"file": ("roof.png", PNG, "image/png")}, headers=H))
    ok(client.post("/api/staff/jobs/%s/finish" % jid, headers=H))
    as_(client, "director")
    ws = [w for w in ok(client.get("/api/staff/warranties"))["rows"] if w.get("order_ref") == order["ref"]]
    assert ws and all(w["start_date"] == date.today().isoformat() for w in ws)        # warranties start at installation
    invs = ok(client.get("/api/staff/orders/%s" % oid))["invoices"]
    assert any(i["kind"] == "final" for i in invs)                                      # installed -> final invoice
    assert abs(sum(i["amount_total"] for i in invs if i["state"] != "cancel") - order["amount_total"]) < 1


def test_invoice_page_and_customer_access(client):
    as_(client, "customer")
    mine = ok(client.get("/api/my/overview"))
    inv = next(i for o in mine["orders"] for i in o["invoices"])
    page = client.get(inv["url"])
    assert page.status_code == 200 and inv["ref"] in page.text and "rupees only" in page.text and "GST" in page.text
    client.cookies.clear()
    assert client.get(inv["url"]).status_code == 200                       # the emailed link works without signing in
    assert client.get(inv["url"].split("?")[0]).status_code == 403         # but not without its token
    assert client.get(inv["url"].split("?")[0] + "?token=wrong").status_code == 403


def test_razorpay_webhook_confirms_payment(client):
    import hashlib
    import hmac
    import json as _json
    from app.db import session
    with session() as db:
        db.set_setting("razorpay_webhook_secret", "whsec_test")
        o = db.one("SELECT * FROM orders WHERE state = 'sale' AND amount_total > 1000 ORDER BY id DESC LIMIT 1")
        pid = db.insert("payments", {"ref": "PAY-WH1", "order_id": o["id"], "customer_id": o["customer_id"], "amount": 500,
                                     "method": "razorpay", "provider_ref": "order_WH1", "state": "pending", "purpose": "balance",
                                     "date": "2026-11-22 10:00:00"})
    body = _json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {
        "id": "pay_WH1", "order_id": "order_WH1", "amount": 50000}}}}).encode()
    bad = client.post("/api/sunpower/razorpay/webhook", content=body, headers={"X-Razorpay-Signature": "forged"})
    assert bad.status_code == 400
    sig = hmac.new(b"whsec_test", body, hashlib.sha256).hexdigest()
    r = client.post("/api/sunpower/razorpay/webhook", content=body, headers={"X-Razorpay-Signature": sig})
    assert r.status_code == 200, r.text
    with session() as db:
        assert not db.one("SELECT id FROM payments WHERE id = ? AND state = 'pending'", pid)
        assert db.one("SELECT id FROM payments WHERE provider_ref = 'pay_WH1' AND state = 'done'")
        email = db.val("SELECT email FROM customers WHERE id = ?", o["customer_id"])
        if email:   # the customer gets the invoice by email
            assert db.val("SELECT COUNT(*) FROM mail_queue WHERE email_to = ? AND subject LIKE 'Invoice %'", email)
    again = client.post("/api/sunpower/razorpay/webhook", content=body, headers={"X-Razorpay-Signature": sig})
    assert again.status_code == 200                                         # repeated events are harmless
