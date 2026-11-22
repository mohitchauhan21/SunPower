"""Public website: savings estimate and enquiry form."""
from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse

from .. import rules
from ..db import get_db
from ..security import optional_user

router = APIRouter(prefix="/api/sunpower")


def _float(v, cap=None):
    try:
        f = max(rules.as_float(v), 0.0)
    except rules.RuleError:   # not a number (or NaN / infinity): treat as not given
        f = 0.0
    return min(f, cap) if cap else f


@router.post("/estimate")
def estimate(body: dict = Body(default={})):
    return rules.estimate(_float(body.get("units")), _float(body.get("bill")), state=body.get("state"),
                          include_topup=bool(body.get("topup")), kw=_float(body.get("kw"), 100) or None,
                          cost_per_kw=_float(body.get("cost_per_kw"), 1000000) or None,
                          tariff=_float(body.get("tariff"), 100) or None,
                          system_type="off_grid" if body.get("system_type") == "off_grid" else "on_grid") or {}


@router.get("/subsidy-states")
def subsidy_states():
    """State / UT subsidy table for the Savings page and the home page averages."""
    from ..subsidy import states_payload
    return states_payload()


@router.post("/razorpay/webhook")
async def razorpay_webhook(request: Request, db=Depends(get_db)):
    """Razorpay tells us a payment was captured, even if the customer closed the window before
    our page could confirm it. Trusted only if signed with the webhook secret (Settings)."""
    import hashlib
    import hmac
    import json as _json
    raw = await request.body()
    secret = (db.setting("razorpay_webhook_secret") or "").encode()
    sig = request.headers.get("x-razorpay-signature") or ""
    if not secret or not hmac.compare_digest(hmac.new(secret, raw, hashlib.sha256).hexdigest(), sig):
        return JSONResponse({"ok": False}, status_code=400)
    try:
        event = _json.loads(raw)
        pay = event["payload"]["payment"]["entity"]
    except (ValueError, KeyError, TypeError):
        return {"ok": True}   # an event we don't use
    if event.get("event") not in ("payment.captured", "order.paid"):
        return {"ok": True}
    p = db.one("SELECT * FROM payments WHERE provider_ref = ? AND method = 'razorpay' AND state = 'pending'", pay.get("order_id"))
    if p and abs(rules.r2(pay.get("amount", 0) / 100) - p["amount"]) < 1:
        try:
            rules.complete_online_payment(db, p, provider_ref=pay.get("id"))
        except rules.RuleError:
            pass   # already completed by the customer's page
    return {"ok": True}


@router.post("/enquiry")
def enquiry(request: Request, body: dict = Body(default={}), db=Depends(get_db), user=Depends(optional_user)):
    from ..security import client_ip, rate_limited
    ip = client_ip(request)
    if rate_limited("enquiry:" + ip, limit=20, window=3600):
        return {"ok": False, "error": "Too many requests from this connection. Please call us instead."}
    from ..subsidy import BY_NAME
    cust = db.get("customers", user["customer_id"]) if user and user["role"] == "customer" and user.get("customer_id") else None
    if cust:   # the same name, mobile and email throughout: they come from the account, not the form
        body = {**body, "name": cust["name"], "email": cust["email"] or body.get("email")}
        if rules.normalize_phone(cust["phone"]):
            body["phone"] = cust["phone"]
    name = rules.text(body.get("name")).strip()[:120]
    if len(name) < 2:
        return {"ok": False, "field": "name", "error": "Please enter your full name."}
    phone = rules.normalize_phone(body.get("phone"))
    if not phone:
        return {"ok": False, "field": "phone", "error": "Enter a 10-digit Indian mobile number (e.g. 98765 43210)."}
    state = rules.text(body.get("state")).strip()
    if state and state.lower() not in BY_NAME:
        return {"ok": False, "field": "state", "error": "Choose your state from the list."}
    state = BY_NAME[state.lower()][0] if state else None
    bill = _float(body.get("monthly_bill"))
    if bill > 1000000:
        return {"ok": False, "field": "monthly_bill", "error": "That bill looks too high. Enter your monthly bill in rupees."}
    # Same phone pressed twice (or the page re-sent): reuse the open enquiry from the last 10 minutes
    recent = db.one("SELECT id, ref FROM leads WHERE phone = ? AND stage = 'new' AND created_at >= datetime('now', '-10 minutes') "
                    "ORDER BY id DESC LIMIT 1", phone)
    if recent:
        return {"ok": True, "id": recent["id"], "ref": recent["ref"], "contact": name, "signed_in": bool(user),
                "duplicate": True}
    try:
        pref_day, pref_slot = rules.check_preferred_visit(body.get("preferred_date"), body.get("preferred_slot"))
    except rules.RuleError as e:
        return {"ok": False, "field": "preferred_date", "error": str(e)}
    est = body.get("estimate") if isinstance(body.get("estimate"), dict) else None
    summary = None
    if est:
        summary = "Website estimate: %s kW %s in %s, price %s, subsidy %s, estimated total %s." % (
            est.get("kw"), "Off-Grid" if body.get("system_type") == "off_grid" else "On-Grid", state or "-",
            rules.money(_float(est.get("cost"))), rules.money(_float(est.get("subsidy"))),
            rules.money(_float(est.get("net_cost"))))
    customer_id = user["customer_id"] if user and user["role"] == "customer" else None
    if cust and not rules.normalize_phone(cust["phone"]):   # first booking: keep the mobile on the account
        db.update("customers", cust["id"], {"phone": phone})
    try:
        lid = rules.create_enquiry(db, {
            "contact_name": name, "phone": phone,
            "email": rules.text(body.get("email")).strip()[:120] or None,
            "street": rules.text(body.get("street")).strip()[:200] or None,
            "city": rules.text(body.get("city")).strip()[:80] or None,
            "requested_kw": _float(body.get("system_kw"), 500),
            "system_type": body.get("system_type"),
            "subsidy_requested": bool(body.get("subsidy")),
            "monthly_bill": bill, "state": state, "preferred_date": pref_day, "preferred_slot": pref_slot,
            "roof_area_sqft": _float(body.get("roof_area")),
            "notes": "\n".join(x for x in (rules.text(body.get("notes")).strip()[:2000], summary) if x) or None,
        }, channel="web", customer_id=customer_id)
    except rules.RuleError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "id": lid, "ref": db.val("SELECT ref FROM leads WHERE id = ?", lid),
            "contact": name, "signed_in": bool(user)}
