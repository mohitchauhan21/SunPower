"""Public website: savings estimate and enquiry form."""
from fastapi import APIRouter, Body, Depends, Request

from .. import rules
from ..db import get_db
from ..security import optional_user

router = APIRouter(prefix="/api/sunpower")


def _float(v, cap=None):
    try:
        f = max(float(v or 0), 0.0)
    except (TypeError, ValueError):
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


@router.post("/enquiry")
def enquiry(request: Request, body: dict = Body(default={}), db=Depends(get_db), user=Depends(optional_user)):
    from ..security import client_ip, rate_limited
    ip = client_ip(request)
    if rate_limited("enquiry:" + ip, limit=20, window=3600):
        return {"ok": False, "error": "Too many requests from this connection. Please call us instead."}
    from ..subsidy import BY_NAME
    name = (body.get("name") or "").strip()[:120]
    if len(name) < 2:
        return {"ok": False, "field": "name", "error": "Please enter your full name."}
    phone = rules.normalize_phone(body.get("phone"))
    if not phone:
        return {"ok": False, "field": "phone", "error": "Enter a 10-digit Indian mobile number (e.g. 98765 43210)."}
    state = (body.get("state") or "").strip()
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
    est = body.get("estimate") if isinstance(body.get("estimate"), dict) else None
    summary = None
    if est:
        summary = "Website estimate: %s kW %s in %s, price %s, subsidy %s, estimated total %s." % (
            est.get("kw"), "Off-Grid" if body.get("system_type") == "off_grid" else "On-Grid", state or "-",
            rules.money(_float(est.get("cost"))), rules.money(_float(est.get("subsidy"))),
            rules.money(_float(est.get("net_cost"))))
    customer_id = user["customer_id"] if user and user["role"] == "customer" else None
    try:
        lid = rules.create_enquiry(db, {
            "contact_name": name, "phone": phone,
            "email": (body.get("email") or "").strip()[:120] or None,
            "street": (body.get("street") or "").strip()[:200] or None,
            "city": (body.get("city") or "").strip()[:80] or None,
            "requested_kw": _float(body.get("system_kw"), 500),
            "system_type": body.get("system_type"),
            "subsidy_requested": bool(body.get("subsidy")),
            "monthly_bill": bill, "state": state,
            "roof_area_sqft": _float(body.get("roof_area")),
            "notes": "\n".join(x for x in ((body.get("notes") or "").strip()[:2000], summary) if x) or None,
        }, channel="web", customer_id=customer_id)
    except rules.RuleError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "id": lid, "ref": db.val("SELECT ref FROM leads WHERE id = ?", lid),
            "contact": name, "signed_in": bool(user)}
