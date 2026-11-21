"""Create / read / update / delete for every record, with role-based access (RBAC).

For each action: the right roles may do it, the other roles get 403, and deletes
that would break history are refused with 400.
Run:  .venv/Scripts/python -m pytest -q
"""
import os
import tempfile

import pytest

os.environ["SUNPOWER_DB"] = os.path.join(tempfile.mkdtemp(), "crud.db")
os.environ["SUNPOWER_MAIL_WORKER"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.seed import DEMO_PASSWORD  # noqa: E402
from app.security import reset_rate_limits  # noqa: E402

H = {"X-SunPower": "1"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def as_(client, who):
    """Sign in as a demo user (who = director, sales, warehouse, support, tech01, customer)."""
    reset_rate_limits()
    client.cookies.clear()
    r = client.post("/api/auth/login", json={"login": "%s@sunpower.demo" % who, "password": DEMO_PASSWORD}, headers=H)
    assert r.json()["ok"], r.json()


def new_lead(client, name="Crud Test"):
    r = client.post("/api/staff/leads", json={"contact_name": name, "phone": "9000012345"}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def make_quote(client):
    """Signed in as the Director: enquiry -> screening -> survey -> approval -> draft quote. Returns the order id."""
    as_(client, "director")
    lid = new_lead(client, "Quote Test")
    client.patch("/api/staff/leads/%s" % lid, json={"roof_area_sqft": 300, "monthly_bill": 2400, "grid_suitable": "yes",
                                                   "requested_kw": 2}, headers=H)
    tech = client.get("/api/staff/people?role=technician").json()[0]
    sid = client.post("/api/staff/leads/%s/survey" % lid, json={"technician_id": tech["id"]}, headers=H).json()["id"]
    client.patch("/api/staff/surveys/%s" % sid, json={"roof_direction": "S", "usable_area_sqft": 300, "recommended_kw": 2}, headers=H)
    assert client.post("/api/staff/surveys/%s/done" % sid, headers=H).json()["ok"]
    assert client.post("/api/staff/surveys/%s/approve" % sid, headers=H).json()["ok"]
    return client.post("/api/staff/leads/%s/quote" % lid, headers=H).json()["id"]


def test_modules_say_who_may_delete(client):
    as_(client, "sales")
    mods = {m["key"]: m for m in client.get("/api/auth/me").json()["modules"]}
    assert mods["leads"]["delete"] is True and mods["customers"]["level"] == "rw"
    as_(client, "tech01")
    mods = {m["key"]: m for m in client.get("/api/auth/me").json()["modules"]}
    assert not any(m["delete"] for m in mods.values())


def test_enquiry_crud_and_roles(client):
    as_(client, "sales")
    lid = new_lead(client)
    assert client.patch("/api/staff/leads/%s" % lid, json={"city": "Surat"}, headers=H).json()["ok"]
    assert client.get("/api/staff/leads/%s" % lid).json()["city"] == "Surat"
    for who in ("support", "tech01", "warehouse"):
        as_(client, who)
        assert client.delete("/api/staff/leads/%s" % lid, headers=H).status_code == 403, who
    as_(client, "sales")
    assert client.delete("/api/staff/leads/%s" % lid, headers=H).json()["ok"]
    assert client.get("/api/staff/leads/%s" % lid).status_code == 404


def test_confirmed_order_cannot_be_deleted_but_quote_can(client):
    as_(client, "director")
    sale = client.get("/api/staff/orders?state=sale").json()["rows"][0]
    r = client.delete("/api/staff/orders/%s" % sale["id"], headers=H)
    assert r.status_code == 400 and "Cancel" in r.json()["detail"]
    lead_with_sale = client.get("/api/staff/orders/%s" % sale["id"]).json()["lead_id"]
    assert client.delete("/api/staff/leads/%s" % lead_with_sale, headers=H).status_code == 400
    draft = {"id": make_quote(client)}
    as_(client, "sales")
    o = client.get("/api/staff/orders/%s" % draft["id"]).json()
    prod = next(p for p in client.get("/api/staff/products").json()["rows"] if p["code"] == "LA-1")
    assert client.post("/api/staff/orders/%s/add-line" % draft["id"], json={"product_id": prod["id"], "qty": 2}, headers=H).json()["ok"]
    o2 = client.get("/api/staff/orders/%s" % draft["id"]).json()
    assert len(o2["lines"]) == len(o["lines"]) + 1 and o2["amount_total"] > o["amount_total"]
    added = o2["lines"][-1]["id"]
    assert client.delete("/api/staff/orders/%s/lines/%s" % (draft["id"], added), headers=H).json()["ok"]
    as_(client, "warehouse")
    assert client.delete("/api/staff/orders/%s" % draft["id"], headers=H).status_code == 403
    as_(client, "sales")
    assert client.delete("/api/staff/orders/%s" % draft["id"], headers=H).json()["ok"]


def test_customer_crud_and_roles(client):
    as_(client, "support")
    cid = client.post("/api/staff/customers", json={"name": "Walk In", "phone": "9876500000", "email": "walk.in@example.com"},
                      headers=H).json()["id"]
    assert client.patch("/api/staff/customers/%s" % cid, json={"city": "Vadodara"}, headers=H).json()["ok"]
    assert client.delete("/api/staff/customers/%s" % cid, headers=H).status_code == 403      # only the Director
    as_(client, "tech01")
    assert client.post("/api/staff/customers", json={"name": "X", "phone": "1"}, headers=H).status_code == 403
    as_(client, "director")
    busy = client.get("/api/staff/customers").json()["rows"]
    with_orders = next(c for c in busy if c["orders"])
    assert client.delete("/api/staff/customers/%s" % with_orders["id"], headers=H).status_code == 400
    assert client.delete("/api/staff/customers/%s" % cid, headers=H).json()["ok"]


def test_products_jobs_tickets_warranties(client):
    as_(client, "warehouse")
    assert client.post("/api/staff/products", json={"code": "WIFI-1", "name": "Wi-Fi monitor", "category": "bos"},
                       headers=H).status_code == 403
    as_(client, "director")
    pid = client.post("/api/staff/products", json={"code": "WIFI-1", "name": "Wi-Fi monitor", "category": "bos", "price": 2500},
                      headers=H).json()["id"]
    assert client.delete("/api/staff/products/%s" % pid, headers=H).json()["ok"]
    assert not any(p["id"] == pid for p in client.get("/api/staff/products").json()["rows"])
    # the only job of a confirmed order can't be deleted
    job = next(j for j in client.get("/api/staff/jobs").json()["rows"] if j["state"] == "planned")
    assert client.delete("/api/staff/jobs/%s" % job["id"], headers=H).status_code == 400
    as_(client, "tech01")
    assert client.delete("/api/staff/jobs/%s" % job["id"], headers=H).status_code == 403
    # tickets: Service desk may delete a request without an invoice; Sales may not
    as_(client, "support")
    cust = client.get("/api/staff/customers").json()["rows"][0]
    tid = client.post("/api/staff/tickets", json={"customer_id": cust["id"], "description": "Logged twice by mistake"},
                      headers=H).json()["id"]
    as_(client, "sales")
    assert client.delete("/api/staff/tickets/%s" % tid, headers=H).status_code == 403
    as_(client, "support")
    assert client.delete("/api/staff/tickets/%s" % tid, headers=H).json()["ok"]
    # warranties: only the Director may extend
    w = client.get("/api/staff/warranties").json()["rows"][0]
    assert client.patch("/api/staff/warranties/%s" % w["id"], json={"months": 36}, headers=H).status_code == 403
    as_(client, "director")
    assert client.patch("/api/staff/warranties/%s" % w["id"], json={"months": w["months"] + 12}, headers=H).json()["ok"]


def test_notes_edit_and_delete_own_only(client):
    as_(client, "sales")
    lid = client.get("/api/staff/leads").json()["rows"][0]["id"]
    client.post("/api/staff/notes", json={"model": "lead", "res_id": lid, "body": "Called, no answer"}, headers=H)
    note = next(n for n in client.get("/api/staff/leads/%s" % lid).json()["notes_log"] if n["kind"] == "note")
    assert client.patch("/api/staff/notes/%s" % note["id"], json={"body": "Called twice"}, headers=H).json()["ok"]
    as_(client, "support")
    assert client.delete("/api/staff/notes/%s" % note["id"], headers=H).status_code == 403
    as_(client, "director")
    assert client.delete("/api/staff/notes/%s" % note["id"], headers=H).json()["ok"]
    log = next(n for n in client.get("/api/staff/leads/%s" % lid).json()["notes_log"] if n["kind"] == "log")
    assert client.delete("/api/staff/notes/%s" % log["id"], headers=H).status_code == 400   # history stays


def test_void_payment_and_cancel_invoice(client):
    as_(client, "director")
    ready = client.get("/api/staff/deliveries?state=ready").json()["rows"]
    if not ready:
        pytest.skip("no delivery waiting in the demo data")
    order = client.get("/api/staff/orders/%s" % ready[0]["order_id"]).json()
    pay = next(p for p in order["payments"] if p["state"] == "done")
    as_(client, "sales")
    assert client.post("/api/staff/payments/%s/void" % pay["id"], headers=H).status_code == 403
    as_(client, "director")
    assert client.post("/api/staff/payments/%s/void" % pay["id"], json={"reason": "bounced"}, headers=H).json()["ok"]
    again = client.get("/api/staff/orders/%s" % order["id"]).json()
    assert again["advance_due"] > 0
    assert client.get("/api/staff/deliveries/%s" % ready[0]["id"]).json()["state"] == "waiting"
    unpaid = next((i for i in again["invoices"] if i["amount_paid"] < 0.5 and i["state"] != "cancel"), None)
    if unpaid:
        assert client.post("/api/staff/invoices/%s/cancel" % unpaid["id"], headers=H).json()["ok"]


def test_staff_accounts_edit(client):
    as_(client, "director")
    tech = next(u for u in client.get("/api/staff/users").json()["rows"] if u["email"] == "tech15@sunpower.demo")
    assert client.patch("/api/staff/users/%s" % tech["id"], json={"name": "Ajay D.", "phone": "9000000015"}, headers=H).json()["ok"]
    as_(client, "sales")
    assert client.patch("/api/staff/users/%s" % tech["id"], json={"name": "X"}, headers=H).status_code == 403


def test_customer_cancels_own_new_request_only(client):
    as_(client, "customer")
    tid = client.post("/api/my/complaint", json={"description": "Inverter beeping all night long"}, headers=H).json()["id"]
    assert client.post("/api/my/ticket/cancel", json={"ticket_id": tid}, headers=H).json()["ok"]
    as_(client, "support")
    other = client.get("/api/staff/tickets").json()["rows"][0]
    as_(client, "customer")
    assert client.post("/api/my/ticket/cancel", json={"ticket_id": other["id"]}, headers=H).status_code == 404
    assert client.delete("/api/staff/leads/1", headers=H).status_code == 403          # customers never reach staff APIs
