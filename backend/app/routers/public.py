"""Public website: savings estimate and enquiry form."""
from fastapi import APIRouter, Body, Depends

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
                          tariff=_float(body.get("tariff"), 100) or None) or {}


@router.get("/subsidy-states")
def subsidy_states():
    """State / UT subsidy table for the Savings page and the home page averages."""
    from ..subsidy import states_payload
    return states_payload()


@router.post("/enquiry")
def enquiry(body: dict = Body(default={}), db=Depends(get_db), user=Depends(optional_user)):
    name = (body.get("name") or "").strip()[:120]
    phone = (body.get("phone") or "").strip()[:40]
    if not name or not phone:
        return {"ok": False, "error": "Please enter your name and phone number."}
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
            "monthly_bill": _float(body.get("monthly_bill")),
            "roof_area_sqft": _float(body.get("roof_area")),
            "notes": (body.get("notes") or "").strip()[:2000] or None,
        }, channel="web", customer_id=customer_id)
    except rules.RuleError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "id": lid, "ref": db.val("SELECT ref FROM leads WHERE id = ?", lid),
            "contact": name, "signed_in": bool(user)}
