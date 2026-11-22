"""My Account (customers): enquiries, quotes, orders, payments, warranties,
service requests, profile. Every read is limited to the signed-in customer."""
from fastapi import APIRouter, Body, Depends, HTTPException, Request

from .. import rules
from ..db import get_db, today
from ..security import (COOKIE, check_password, end_all_sessions, hash_password, password_problem, require)

router = APIRouter(prefix="/api/my")
customer = require("customer")


def _cid(user):
    if not user["customer_id"]:
        raise HTTPException(403, "No customer profile.")
    return user["customer_id"]


def _order(db, user, order_id, states=None):
    o = db.one("SELECT * FROM orders WHERE id = ? AND customer_id = ?", rules.as_int(order_id), _cid(user))
    if not o or (states and o["state"] not in states):
        raise HTTPException(404, "Order not found.")
    return o


def order_summary(db, o):
    paid = rules.order_paid(db, o["id"])
    due = rules.advance_due(db, o) if o["state"] in ("sent", "sale") else 0
    deliveries = db.q("SELECT * FROM deliveries WHERE order_id = ?", o["id"])
    job = db.one("SELECT * FROM jobs WHERE order_id = ? ORDER BY id LIMIT 1", o["id"])
    sub = db.one("SELECT * FROM subsidies WHERE order_id = ?", o["id"])
    chk = [job[f] for f, _l in rules.CHECKLIST] if job else []
    shipped = bool(deliveries) and all(d["state"] in ("done", "delivered") for d in deliveries)
    # A finished installation means the kit reached the site, even if the warehouse never marked it delivered.
    delivered = bool(deliveries) and (all(d["state"] == "delivered" for d in deliveries) or bool(job and job["state"] == "done"))
    packed = bool(deliveries) and all(d["state"] in ("packed", "done", "delivered") for d in deliveries)
    last = deliveries[-1] if deliveries else {}
    return {
        "id": o["id"], "name": o["ref"], "kw": o["kw"] or 0, "state": o["state"],
        "project": db.val("SELECT project_ref FROM leads WHERE id = ?", o["lead_id"]) if o["lead_id"] else None,
        "quote_pending": o["state"] in ("draft", "sent"), "date": o["date_order"], "valid_until": o["valid_until"],
        "total": o["amount_total"], "paid": paid, "due": max(rules.r2(o["amount_total"] - paid), 0),
        "advance_pct": float(db.setting("advance_pct", 30)), "advance_due": due,
        "advance_amount": rules.advance_needed(db, o),
        "payment_plan": o["payment_plan"], "full_discount_pct": rules.full_discount_pct(db),
        "full_amount": rules.full_upfront_amount(db, o) if paid < 0.5 else None,
        "pdf_url": "/print/quote/%s?token=%s" % (o["id"], o["access_token"]),
        "review_url": "/account/quote/%s" % o["id"],
        "certificate_url": ("/print/certificate/%s?token=%s" % (job["id"], o["access_token"])
                            if job and job["state"] == "done" else None),
        "steps": [
            {"label": "Order confirmed", "done": o["state"] == "sale"},
            {"label": "Advance paid", "done": o["state"] == "sale" and due == 0},
            {"label": "Kit packed", "done": packed, "date": last.get("packed_at")},
            {"label": "Kit shipped", "done": shipped, "date": last.get("date_done"),
             "note": ("Expected %s" % last["expected_on"]) if shipped and not delivered and last.get("expected_on") else None},
            {"label": "Kit delivered", "done": delivered, "date": last.get("delivered_at")},
            {"label": "Installation scheduled", "done": bool(job and job["scheduled_at"]),
             "date": job["scheduled_at"] if job else None},
            {"label": "Crew on site", "done": bool(job) and job["state"] in ("in_progress", "done")},
            {"label": "Tested & handed over", "done": bool(job) and job["state"] == "done"},
        ],
        "checklist_done": sum(1 for c in chk if c), "checklist_total": len(rules.CHECKLIST),
        "subsidy": {"state": rules.label(rules.SUBSIDY_STATES, sub["state"]), "amount": sub["amount_expected"]} if sub else None,
    }


@router.get("/overview")
def overview(user=Depends(customer), db=Depends(get_db)):
    cid = _cid(user)
    cust = db.get("customers", cid)
    orders = db.q("SELECT * FROM orders WHERE customer_id = ? AND state IN ('sent','sale') ORDER BY date_order DESC", cid)
    leads = db.q("SELECT * FROM leads WHERE customer_id = ? AND stage NOT IN ('won','lost') ORDER BY created_at DESC LIMIT 10", cid)
    enquiries = []
    for l in leads:
        if db.val("SELECT COUNT(*) FROM orders WHERE lead_id = ? AND state IN ('sent','sale')", l["id"]):
            continue
        s = db.one("SELECT s.*, u.name AS tech FROM surveys s LEFT JOIN users u ON u.id = s.technician_id "
                   "WHERE s.lead_id = ? ORDER BY s.id DESC LIMIT 1", l["id"])
        enquiries.append({"id": l["id"], "name": l["ref"], "project": l["project_ref"], "created": l["created_at"],
                          "kw": l["requested_kw"] or 0,
                          "stage": rules.label(rules.LEAD_STAGES, l["stage"]), **rules.enquiry_progress(l, s),
                          "survey": {"state": rules.label(rules.SURVEY_STATES, s["state"]), "date": s["survey_date"],
                                     "technician": s["tech"]} if s else None})
    warranties = db.q("SELECT w.*, p.name AS product, s.name AS serial FROM warranties w JOIN products p ON p.id = w.product_id "
                      "JOIN serials s ON s.id = w.serial_id WHERE w.customer_id = ? ORDER BY w.end_date", cid)
    t0 = today()
    from datetime import date
    tickets = db.q("SELECT t.*, p.name AS product, s.name AS serial, u.name AS tech FROM tickets t "
                   "LEFT JOIN products p ON p.id = t.product_id LEFT JOIN serials s ON s.id = t.serial_id "
                   "LEFT JOIN users u ON u.id = t.technician_id WHERE t.customer_id = ? ORDER BY t.reported_on DESC", cid)
    out_tickets = []
    for t in tickets:
        a = rules.ticket_amounts(db, t)
        out_tickets.append({
            "id": t["id"], "name": t["ref"], "stage": t["stage"], "stage_label": rules.label(rules.TICKET_STAGES, t["stage"]),
            "product": t["product"], "serial": t["serial"], "reported": t["reported_on"], "closed": t["closed_on"],
            "description": t["description"] or "", "fault_code": t["fault_code"], "under_warranty": a["under_warranty"],
            "charge": a["customer_charge"], "technician": t["tech"], "resolution": t["resolution"],
            "can_confirm": t["stage"] == "awaiting", "can_cancel": t["stage"] == "new"})
    return {
        "customer": {"name": cust["name"], "email": cust["email"], "phone": cust["phone"], "street": cust["street"],
                     "city": cust["city"]},
        "enquiries": enquiries,
        "orders": [order_summary(db, o) for o in orders],
        "warranties": [{"id": w["id"], "product": w["product"], "serial": w["serial"], "start": w["start_date"],
                        "end": w["end_date"], "active": w["start_date"] <= t0 <= w["end_date"],
                        "days_left": max((date.fromisoformat(w["end_date"]) - date.today()).days, 0)} for w in warranties],
        "tickets": out_tickets,
        "payment_modes": rules.payment_modes(db),
    }


# ------------------------------------------------------------------ quotes
@router.get("/quote/{order_id}")
def quote(order_id: int, user=Depends(customer), db=Depends(get_db)):
    o = _order(db, user, order_id, ("sent", "sale"))
    lines = db.q("SELECT description, qty, price_unit, discount, tax_rate, subtotal FROM order_lines WHERE order_id = ?", o["id"])
    sub = (rules.subsidy_expected(o["kw"], rules.lead_state(db, o))
           if o["system_type"] == "on_grid" and db.val("SELECT subsidy_requested FROM leads WHERE id = ?", o["lead_id"]) else 0)
    return {**order_summary(db, o), "lines": lines, "untaxed": o["amount_untaxed"], "tax": o["amount_tax"],
            "note": o["note"], "accepted_by": o["accepted_by"], "accepted_at": o["accepted_at"],
            "subsidy_expected": sub, "est_kwh_year": o["est_kwh_year"], "est_savings_year": o["est_savings_year"],
            "system_type": o["system_type"], "payment_modes": rules.payment_modes(db)}


@router.post("/quote/{order_id}/accept")
def accept_quote(order_id: int, body: dict = Body(default={}), user=Depends(customer), db=Depends(get_db)):
    o = _order(db, user, order_id, ("sent",))
    name = rules.text(body.get("name")).strip()[:120]
    plan = body.get("plan") if body.get("plan") in ("advance", "full") else None
    if len(name) < 2:
        return {"ok": False, "field": "name", "error": "Type your full name to accept."}
    if not plan:
        return {"ok": False, "field": "plan", "error": "Choose how you'd like to pay."}
    if o["valid_until"] and o["valid_until"] < today():
        return {"ok": False, "error": "This quotation has expired. Please contact us for a fresh one."}
    db.update("orders", o["id"], {"accepted_by": name, "accepted_at": rules.now(), "payment_plan": plan})
    db.note("order", o["id"], "Quotation accepted online by %s (%s)." % (
        name, "pays 100% upfront" if plan == "full" else "advance now, balance after installation"), user["id"])
    try:
        return {"ok": True, **_pay(db, user, db.get("orders", o["id"]), plan)}
    except rules.RuleError as e:
        # The acceptance stands even if payment can't start now (e.g. online payment switched off):
        # the customer pays later from the same page or by phone.
        return {"ok": False, "accepted": True, "error": str(e)}


def _pay(db, user, o, kind):
    paid = rules.order_paid(db, o["id"])
    if kind == "full":
        if paid > 0.5:   # the upfront discount is only for paying everything in one go
            kind = "balance"
        else:
            return rules.start_online_payment(db, o, rules.full_upfront_amount(db, o), "full", user["id"])
    amount = (o["amount_total"] - paid) if kind == "balance" else rules.advance_needed(db, o) - paid
    return rules.start_online_payment(db, o, amount, "balance" if kind == "balance" else "advance", user["id"])


@router.post("/order/pay")
def order_pay(body: dict = Body(default={}), user=Depends(customer), db=Depends(get_db)):
    o = _order(db, user, body.get("order_id"), ("sent", "sale"))
    if o["state"] == "sent" and not o["accepted_by"]:
        return {"ok": False, "error": "Please review and accept the quotation first."}
    try:
        return {"ok": True, **_pay(db, user, o, body.get("kind") or "advance")}
    except rules.RuleError as e:
        return {"ok": False, "error": str(e)}


def _pending(db, user, payment_id):
    p = db.one("SELECT * FROM payments WHERE id = ? AND customer_id = ?", rules.as_int(payment_id), _cid(user))
    if not p:
        raise HTTPException(404, "Payment not found.")
    return p


@router.post("/payment/test/confirm")
def test_confirm(body: dict = Body(default={}), user=Depends(customer), db=Depends(get_db)):
    """Test mode only: simulates the bank. Card 4000 0000 0000 0002 is declined."""
    if db.setting("test_payments", "1") != "1":
        raise HTTPException(403, "Test payments are switched off.")
    p = _pending(db, user, body.get("payment_id"))
    if p["method"] != "test" or p["state"] != "pending":
        return {"ok": False, "error": "This payment can't be completed."}
    card = "".join(ch for ch in rules.text(body.get("card")) if ch.isdigit())
    if len(card) < 12:
        return {"ok": False, "field": "card", "error": "Enter the test card number."}
    if card.endswith("0002"):
        db.update("payments", p["id"], {"state": "failed"})
        return {"ok": False, "error": "The bank declined this card (test decline). Try another card."}
    rules.complete_online_payment(db, p, provider_ref="TEST-%s" % card[-4:], actor_id=user["id"])
    return {"ok": True}


@router.post("/payment/razorpay/verify")
def razorpay_verify(body: dict = Body(default={}), user=Depends(customer), db=Depends(get_db)):
    p = _pending(db, user, body.get("payment_id"))
    if p["method"] != "razorpay" or p["state"] != "pending" or p["provider_ref"] != body.get("razorpay_order_id"):
        return {"ok": False, "error": "This payment can't be verified."}
    if not rules.verify_razorpay_signature(db, body.get("razorpay_order_id"), body.get("razorpay_payment_id"),
                                           body.get("razorpay_signature")):
        db.update("payments", p["id"], {"state": "failed"})
        return {"ok": False, "error": "We couldn't verify this payment. If money was taken, call us."}
    rules.complete_online_payment(db, p, provider_ref=body.get("razorpay_payment_id"), actor_id=user["id"])
    return {"ok": True}


# ---------------------------------------------------------------- service
@router.post("/complaint")
def complaint(body: dict = Body(default={}), user=Depends(customer), db=Depends(get_db)):
    serial_id = None
    if body.get("warranty_id"):
        w = db.one("SELECT * FROM warranties WHERE id = ? AND customer_id = ?", rules.as_int(body["warranty_id"]), _cid(user))
        if not w:
            return {"ok": False, "field": "warranty_id", "error": "Please pick your own equipment."}
        serial_id = w["serial_id"]
    try:
        tid = rules.create_ticket(db, _cid(user), rules.text(body.get("description"))[:2000], user["id"], serial_id,
                                  rules.text(body.get("fault_code"))[:20], channel="website")
    except rules.RuleError as e:
        return {"ok": False, "field": "description", "error": str(e)}
    return {"ok": True, "id": tid, "name": db.val("SELECT ref FROM tickets WHERE id = ?", tid)}


def _ticket(db, user, ticket_id):
    t = db.one("SELECT * FROM tickets WHERE id = ? AND customer_id = ?", rules.as_int(ticket_id), _cid(user))
    if not t:
        raise HTTPException(404, "Request not found.")
    return t


@router.post("/ticket/confirm")
def ticket_confirm(body: dict = Body(default={}), user=Depends(customer), db=Depends(get_db)):
    t = _ticket(db, user, body.get("ticket_id"))
    if t["stage"] != "awaiting":
        return {"ok": False, "error": "This request is not waiting for your confirmation."}
    rules.ticket_confirm(db, t, user["id"])
    return {"ok": True}


@router.post("/ticket/reopen")
def ticket_reopen(body: dict = Body(default={}), user=Depends(customer), db=Depends(get_db)):
    t = _ticket(db, user, body.get("ticket_id"))
    if t["stage"] != "awaiting":
        return {"ok": False, "error": "This request is not waiting for your confirmation."}
    rules.ticket_reopen(db, t, user["id"], rules.text(body.get("note"))[:1000])
    return {"ok": True}


# ---------------------------------------------------------------- profile
@router.post("/profile")
def profile(body: dict = Body(default={}), user=Depends(customer), db=Depends(get_db)):
    vals = {}
    if "name" in body:
        name = rules.text(body.get("name")).strip()[:120]
        if not name:
            return {"ok": False, "field": "name", "error": "Please enter your name."}
        vals["name"] = name
    for k in ("phone", "street", "city"):
        if k in body:
            vals[k] = rules.text(body.get(k)).strip()[:200] or None
    db.update("customers", _cid(user), vals)
    if "name" in vals or "phone" in vals:
        db.update("users", user["id"], {k: v for k, v in vals.items() if k in ("name", "phone")})
    return {"ok": True}


@router.post("/password")
def password(request: Request, body: dict = Body(default={}), user=Depends(require("customer", "director", "sales",
                                                                                     "warehouse", "technician", "support")),
             db=Depends(get_db)):
    new = rules.text(body.get("new"))
    problem = password_problem(new)
    if problem:
        return {"ok": False, "field": "new", "error": problem}
    if "confirm" in body and body.get("confirm") != new:
        return {"ok": False, "field": "confirm", "error": "The two new passwords don't match."}
    if not check_password(rules.text(body.get("old")), user["password_hash"]):
        return {"ok": False, "field": "old", "error": "Your current password is not correct."}
    db.update("users", user["id"], {"password_hash": hash_password(new)})
    end_all_sessions(db, user["id"], keep_token=request.cookies.get(COOKIE))
    return {"ok": True}


# ---------------------------------------------------------- cancel own items
@router.post("/ticket/cancel")
def ticket_cancel(body: dict = Body(default={}), user=Depends(customer), db=Depends(get_db)):
    """The customer withdraws a request that nobody has started on yet."""
    t = _ticket(db, user, body.get("ticket_id"))
    if t["stage"] != "new":
        return {"ok": False, "error": "A technician is already working on this request. Please call us to stop it."}
    db.update("tickets", t["id"], {"stage": "cancel", "closed_on": rules.now()})
    db.note("ticket", t["id"], "Cancelled by the customer.", user["id"])
    return {"ok": True}


@router.post("/enquiry/cancel")
def enquiry_cancel(body: dict = Body(default={}), user=Depends(customer), db=Depends(get_db)):
    """The customer withdraws an enquiry before any quotation was sent."""
    lead = db.one("SELECT * FROM leads WHERE id = ? AND customer_id = ?", rules.as_int(body.get("lead_id")), _cid(user))
    if not lead or lead["stage"] in ("won", "lost"):
        return {"ok": False, "error": "This enquiry can't be cancelled."}
    if db.val("SELECT COUNT(*) FROM orders WHERE lead_id = ? AND state IN ('sent','sale')", lead["id"]):
        return {"ok": False, "error": "A quotation is already with you; just don't accept it, or call us."}
    db.update("leads", lead["id"], {"stage": "lost", "lost_reason": "Cancelled by the customer"})
    db.exec("UPDATE surveys SET state = 'rejected', rejection_reason = 'Cancelled by the customer' "
            "WHERE lead_id = ? AND state = 'scheduled'", lead["id"])
    db.note("lead", lead["id"], "Cancelled by the customer from their account.", user["id"])
    return {"ok": True}
