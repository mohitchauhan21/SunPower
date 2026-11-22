"""Staff: enquiries, roof surveys, quotes & orders, customers, subsidy files."""
import json

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile

from .. import rules
from ..access import can_delete, can_write, need, need_delete
from ..db import get_db, now
from ..security import staff_only

router = APIRouter(prefix="/api/staff")

LEAD_FIELDS = ("contact_name", "phone", "email", "street", "city", "state", "requested_kw", "system_type", "subsidy_requested",
               "monthly_bill", "monthly_units", "roof_area_sqft", "grid_suitable", "discom", "consumer_no", "notes",
               "salesperson_id", "next_action", "next_action_due", "preferred_date", "preferred_slot")
SURVEY_FIELDS = ("technician_id", "survey_date", "roof_type", "roof_direction", "roof_tilt", "usable_area_sqft",
                 "shading", "cable_distance_m", "earthing_possible", "latitude", "longitude", "recommended_kw", "notes")


def found(row, message):
    if not row:
        raise HTTPException(404, message)
    return row


def like(q):
    return "%%%s%%" % rules.text(q).strip()


def notes_for(db, model, res_id):
    return db.q("SELECT n.id, n.body, n.kind, n.created_at, n.author_id, u.name AS author FROM notes n LEFT JOIN users u ON u.id = n.author_id "
                "WHERE n.model = ? AND n.res_id = ? ORDER BY n.id DESC", model, res_id)


def clean(body, fields):
    out = {}
    for k in fields:
        if k in body:
            v = body[k]
            if isinstance(v, (list, dict)):   # every field cleaned here is a single value
                raise rules.RuleError("%s has an invalid value." % k.replace("_", " ").capitalize())
            out[k] = v.strip() if isinstance(v, str) else v
            if out[k] == "":
                out[k] = None
    return out


@router.get("/people")
def people(role: str = "", user=Depends(staff_only), db=Depends(get_db)):
    """Names for pickers (technicians, salespeople)."""
    roles = [r for r in role.split(",") if r] or ["technician"]
    marks = ",".join("?" for _ in roles)
    return db.q("SELECT id, name, role FROM users WHERE active = 1 AND role IN (%s) ORDER BY name" % marks, *roles)


@router.post("/notes")
def add_note(body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    model, res_id, text = rules.text(body.get("model")), rules.as_int(body.get("res_id")), rules.text(body.get("body")).strip()
    area = {"lead": "leads", "survey": "surveys", "order": "orders", "delivery": "deliveries", "job": "jobs",
            "ticket": "tickets", "subsidy": "subsidies"}.get(model)
    if not area or not text:
        raise HTTPException(400, "Write a note first.")
    lvl = need(user, area)
    table = {"lead": "leads", "survey": "surveys", "order": "orders", "delivery": "deliveries", "job": "jobs",
             "ticket": "tickets", "subsidy": "subsidies"}[model]
    row = found(db.get(table, res_id), "Record not found.")
    if lvl == "own":  # technicians: only their own surveys, jobs and repairs
        mine = {"survey": row.get("technician_id") == user["id"],
                "ticket": row.get("technician_id") == user["id"],
                "job": bool(db.val("SELECT COUNT(*) FROM job_techs WHERE job_id = ? AND user_id = ?", res_id, user["id"]))}
        if not mine.get(model):
            raise HTTPException(404, "Record not found.")
    db.note(model, res_id, text[:2000], user["id"], kind="note")
    return {"ok": True}


# ------------------------------------------------------------------ leads
def lead_row(db, l):
    return {**l, "stage_label": rules.label(rules.LEAD_STAGES, l["stage"]),
            "recommended_kw": rules.lead_recommended_kw(l), "screening_ok": rules.lead_screening_ok(l)}


@router.get("/leads")
def leads(stage: str = "", q: str = "", mine: int = 0, user=Depends(staff_only), db=Depends(get_db)):
    need(user, "leads")
    sql = ("SELECT l.*, u.name AS salesperson FROM leads l LEFT JOIN users u ON u.id = l.salesperson_id WHERE 1=1")
    args = []
    if stage:
        sql += " AND l.stage = ?"
        args.append(stage)
    if q:
        sql += " AND (l.contact_name LIKE ? OR l.phone LIKE ? OR l.ref LIKE ? OR l.city LIKE ? OR l.project_ref LIKE ?)"
        args += [like(q)] * 5
    if mine:
        sql += " AND l.salesperson_id = ?"
        args.append(user["id"])
    rows = db.q(sql + " ORDER BY l.created_at DESC LIMIT 500", *args)
    counts = {r["stage"]: r["n"] for r in db.q("SELECT stage, COUNT(*) AS n FROM leads GROUP BY stage")}
    return {"rows": [lead_row(db, r) for r in rows], "counts": counts,
            "stages": [{"value": k, "label": v} for k, v in rules.LEAD_STAGES]}


@router.post("/leads")
def create_lead(body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    need(user, "leads", write=True)
    vals = clean(body, LEAD_FIELDS)
    channel = body.get("channel") if body.get("channel") in ("call", "whatsapp", "walkin", "referral", "web") else "call"
    cid = rules.ensure_customer(db, vals.get("contact_name") or "", vals.get("email"), vals.get("phone"),
                                vals.get("street"), vals.get("city")) if vals.get("contact_name") and vals.get("phone") else None
    lid = rules.create_enquiry(db, vals, channel=channel, customer_id=cid, actor_id=user["id"])
    return {"ok": True, "id": lid}


@router.get("/leads/{lid}")
def lead(lid: int, user=Depends(staff_only), db=Depends(get_db)):
    need(user, "leads")
    l = db.one("SELECT l.*, u.name AS salesperson FROM leads l LEFT JOIN users u ON u.id = l.salesperson_id WHERE l.id = ?", lid)
    if not l:
        raise HTTPException(404, "Enquiry not found.")
    surveys = db.q("SELECT s.*, u.name AS technician FROM surveys s LEFT JOIN users u ON u.id = s.technician_id "
                   "WHERE s.lead_id = ? ORDER BY s.id DESC", lid)
    orders = db.q("SELECT id, ref, state, amount_total, kw, date_order FROM orders WHERE lead_id = ? ORDER BY id DESC", lid)
    l["preferred_slot_label"] = dict(rules.SURVEY_SLOTS).get(l.get("preferred_slot"), "")
    for s in surveys:
        s["state_label"] = rules.label(rules.SURVEY_STATES, s["state"])
    for o in orders:
        o["state_label"] = rules.label(rules.ORDER_STATES, o["state"])
    return {**lead_row(db, l), "surveys": surveys, "orders": orders, "notes_log": notes_for(db, "lead", lid),
            "has_approved_survey": bool(rules.approved_survey(db, lid)), "can_edit": can_write(user, "leads"),
            "can_delete": can_delete(user, "leads")}


@router.patch("/leads/{lid}")
def update_lead(lid: int, body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    need(user, "leads", write=True)
    l = found(db.get("leads", lid), "Enquiry not found.")
    vals = clean(body, LEAD_FIELDS + ("stage",))
    if "stage" in vals and vals["stage"] not in dict(rules.LEAD_STAGES):
        raise HTTPException(400, "Unknown stage.")
    if vals.get("stage") == "won":
        raise HTTPException(400, "An enquiry is won when its order is confirmed, not by hand.")
    if vals.get("salesperson_id") is not None:   # null / "" = unassign; anything else must be an active person
        vals["salesperson_id"] = rules.as_int(vals["salesperson_id"], "person")
    if vals.get("salesperson_id") is not None and not rules.is_active_role(db, vals["salesperson_id"], ("sales", "director")):
        raise HTTPException(400, "Choose an active salesperson.")
    for k in ("requested_kw", "monthly_bill", "monthly_units", "roof_area_sqft"):
        if vals.get(k) is not None:
            try:
                vals[k] = rules.as_float(vals[k], k)
                assert 0 <= vals[k] <= 10000000
            except (rules.RuleError, AssertionError):
                raise HTTPException(400, "%s must be a positive number." % k.replace("_", " "))
    if vals.get("grid_suitable") and vals["grid_suitable"] not in ("yes", "no", "unknown"):
        raise HTTPException(400, "Grid connection must be yes, no or unknown.")
    if "contact_name" in vals and not vals["contact_name"]:
        raise HTTPException(400, "The customer's name can't be empty.")
    if l["stage"] == "new" and "stage" not in vals:
        vals["stage"] = "contacted"
    db.update("leads", lid, vals)
    if l["customer_id"]:
        db.update("customers", l["customer_id"], {k: vals[k] for k in ("phone", "street", "city") if vals.get(k)})
    return {"ok": True}


@router.post("/leads/{lid}/survey")
def lead_survey(lid: int, body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    need(user, "leads", write=True)
    l = found(db.get("leads", lid), "Enquiry not found.")
    sid = rules.schedule_survey(db, l, rules.as_int(body.get("technician_id")) or None, body.get("survey_date"), user["id"],
                                slot=body.get("slot"))
    return {"ok": True, "id": sid}


@router.get("/leads/{lid}/technicians")
def lead_technicians(lid: int, day: str = "", slot: str = "", skip: int = 0, user=Depends(staff_only), db=Depends(get_db)):
    """Who to send: technicians covering the customer's area and free in that slot come first."""
    need(user, "leads")
    l = found(db.get("leads", lid), "Enquiry not found.")
    return {"rows": rules.suggest_technicians(db, l, day[:10] or None, slot or None, skip),
            "slots": [{"value": k, "label": v} for k, v in rules.SURVEY_SLOTS]}


@router.get("/leads/{lid}/availability")
def lead_availability(lid: int, start: str = "", days: int = 10, skip: int = 0, user=Depends(staff_only), db=Depends(get_db)):
    """Each technician's free and busy slots for the coming days (survey booking)."""
    need(user, "leads")
    l = found(db.get("leads", lid), "Enquiry not found.")
    try:
        return rules.technician_availability(db, l, start[:10] or None, max(1, min(days, 21)), skip)
    except ValueError:
        raise HTTPException(400, "Choose a valid start day.")


@router.post("/leads/{lid}/quote")
def lead_quote(lid: int, user=Depends(staff_only), db=Depends(get_db)):
    need(user, "leads", write=True)
    l = found(db.get("leads", lid), "Enquiry not found.")
    return {"ok": True, "id": rules.create_quote(db, l, user["id"])}


@router.post("/leads/{lid}/lost")
def lead_lost(lid: int, body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    need(user, "leads", write=True)
    db.update("leads", lid, {"stage": "lost", "lost_reason": rules.text(body.get("reason")).strip()[:300] or None})
    db.note("lead", lid, "Marked lost: %s" % (body.get("reason") or "no reason given"), user["id"])
    return {"ok": True}


# ---------------------------------------------------------------- surveys
def _survey(db, user, sid, write=False):
    lvl = need(user, "surveys", write)
    s = db.one("SELECT s.*, l.contact_name, l.phone, l.street, l.city, l.ref AS lead_ref, l.requested_kw, l.system_type, "
               "u.name AS technician FROM surveys s JOIN leads l ON l.id = s.lead_id "
               "LEFT JOIN users u ON u.id = s.technician_id WHERE s.id = ?", sid)
    if not s or (lvl == "own" and s["technician_id"] != user["id"]):
        raise HTTPException(404, "Survey not found.")
    return s, lvl


@router.get("/surveys")
def surveys(state: str = "", q: str = "", user=Depends(staff_only), db=Depends(get_db)):
    lvl = need(user, "surveys")
    sql = ("SELECT s.*, l.contact_name, l.city, l.ref AS lead_ref, u.name AS technician FROM surveys s "
           "JOIN leads l ON l.id = s.lead_id LEFT JOIN users u ON u.id = s.technician_id WHERE 1=1")
    args = []
    if lvl == "own":
        sql += " AND s.technician_id = ?"
        args.append(user["id"])
    if state:
        sql += " AND s.state = ?"
        args.append(state)
    if q:
        sql += " AND (l.contact_name LIKE ? OR s.ref LIKE ? OR l.city LIKE ? OR s.project_ref LIKE ?)"
        args += [like(q)] * 4
    rows = db.q(sql + " ORDER BY COALESCE(s.survey_date, s.created_at) DESC LIMIT 500", *args)
    for r in rows:
        r["state_label"] = rules.label(rules.SURVEY_STATES, r["state"])
    mine = " WHERE technician_id = %d" % user["id"] if lvl == "own" else ""   # live counts for the filter chips
    counts = {r["state"]: r["n"] for r in db.q("SELECT state, COUNT(*) AS n FROM surveys%s GROUP BY state" % mine)}
    return {"rows": rows, "counts": counts, "states": [{"value": k, "label": v} for k, v in rules.SURVEY_STATES]}


@router.post("/surveys/{sid}/quote")
def survey_quote(sid: int, user=Depends(staff_only), db=Depends(get_db)):
    """After the visit: the technician (or Sales) builds the customer's quote from the survey."""
    s, lvl = _survey(db, user, sid, write=True)
    if user["role"] not in ("technician", "sales", "director"):
        raise HTTPException(403, "You don't have access to this.")
    return {"ok": True, "id": rules.quote_from_survey(db, db.get("surveys", sid), user, strict=True)}


@router.post("/surveys/{sid}/photos")
async def survey_photo(sid: int, file: UploadFile = File(...), category: str = Form(...), user=Depends(staff_only),
                       db=Depends(get_db)):
    from .staff_ops import MAX_PHOTO, _image_type
    s, _lvl = _survey(db, user, sid, write=True)
    if s["state"] in ("approved", "rejected"):
        raise HTTPException(400, "This survey is closed.")
    if category not in [p[0] for p in rules.SURVEY_PHOTOS]:
        raise HTTPException(400, "Choose what the photo shows.")
    data = await file.read(MAX_PHOTO + 1)
    mime = _image_type(data)
    if not mime or len(data) > MAX_PHOTO:
        raise HTTPException(400, "Upload a photo (JPG, PNG or WebP, up to 8 MB).")
    aid = db.insert("attachments", {"owner_type": "survey", "owner_id": sid, "filename": (file.filename or "photo")[:120],
                                    "mime": mime, "data": data, "note": category, "created_at": now()})
    return {"ok": True, "id": aid}


@router.delete("/surveys/{sid}/photos/{aid}")
def survey_photo_delete(sid: int, aid: int, user=Depends(staff_only), db=Depends(get_db)):
    s, _lvl = _survey(db, user, sid, write=True)
    if s["state"] in ("approved", "rejected"):
        raise HTTPException(400, "This survey is closed.")
    db.exec("DELETE FROM attachments WHERE id = ? AND owner_type = 'survey' AND owner_id = ?", aid, sid)
    return {"ok": True}


@router.get("/surveys/{sid}")
def survey(sid: int, user=Depends(staff_only), db=Depends(get_db)):
    s, lvl = _survey(db, user, sid)
    quote = db.one("SELECT id, ref, state FROM orders WHERE lead_id = ? AND state != 'cancel' ORDER BY id DESC LIMIT 1", s["lead_id"])
    kit = rules.package_for(db, s["recommended_kw"] or s["requested_kw"], s["system_type"])
    form = {
        "details": rules.survey_details(s),
        "spec": {k: {"section": v[0], "kind": v[1], "options": v[2] if v[1] in ("choice", "multi") else None,
                     "range": v[2] if v[1] == "num" else None, "required": v[3]} for k, v in rules.SURVEY_FIELDS_SPEC.items()},
        "sections": [{"key": k, "label": l} for k, l in rules.SURVEY_SECTIONS],
        "photo_types": [{"key": c, "label": l, "required": r, "section": sec} for c, l, r, sec in rules.SURVEY_PHOTOS],
        "issue_types": rules.ISSUE_TYPES, "results": [{"value": k, "label": l} for k, l in rules.SURVEY_RESULTS],
        "photos": db.q("SELECT id, note AS category, filename, created_at FROM attachments WHERE owner_type = 'survey' "
                       "AND owner_id = ? ORDER BY id", sid),
        "missing": [{"section": a, "label": b, "key": k} for a, b, k in rules.survey_missing(db, s, s["system_type"])],
        "parts": [{"code": p["code"], "name": p["name"], "qty": q, "reason": r} for p, q, r in rules.survey_parts(db, s, kit)] if kit else [],
    }
    return {**s, **form, "quote": quote, "can_quote": lvl in ("rw", "own") and user["role"] in ("technician", "sales", "director")
            and s["state"] in ("scheduled", "done", "approved") and not quote,
            "state_label": rules.label(rules.SURVEY_STATES, s["state"]), "max_kw_fit": round((s["usable_area_sqft"] or 0) / 100, 1),
            "notes_log": notes_for(db, "survey", sid), "can_edit": lvl in ("rw", "own"),
            "can_approve": user["role"] in ("sales", "director"), "can_delete": can_delete(user, "surveys")}


@router.patch("/surveys/{sid}")
def update_survey(sid: int, body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    s, lvl = _survey(db, user, sid, write=True)
    if s["state"] in ("approved", "rejected"):
        raise HTTPException(400, "This survey is closed. Reset it to make changes.")
    fields = SURVEY_FIELDS if lvl == "rw" else tuple(f for f in SURVEY_FIELDS if f != "technician_id")
    vals = clean(body, fields)
    if "details" in body:
        if not isinstance(body["details"], dict):
            raise HTTPException(400, "Invalid survey details.")
        vals["details"] = json.dumps(rules.clean_survey_details(body["details"], rules.survey_details(s)))
    if "result" in body:
        if body["result"] not in (None, "", *dict(rules.SURVEY_RESULTS)):
            raise HTTPException(400, "Choose the survey result.")
        vals["result"] = body["result"] or None
    if vals.get("survey_date") is not None:
        vals["survey_date"] = rules.as_local_datetime(vals["survey_date"], "survey date")
        if vals["survey_date"] != s["survey_date"] and vals["survey_date"][:10] < rules.date.today().isoformat():
            raise HTTPException(400, "The survey can't be moved to a past date.")
    if vals.get("technician_id") is not None:   # null / "" = unassign; anything else must be an active person
        vals["technician_id"] = rules.as_int(vals["technician_id"], "person")
    if vals.get("technician_id") is not None and not rules.is_active_role(db, vals["technician_id"], ("technician",)):
        raise HTTPException(400, "Choose an active technician.")
    for k in ("roof_tilt", "usable_area_sqft", "cable_distance_m", "recommended_kw"):
        if vals.get(k) is not None:
            try:
                vals[k] = rules.as_float(vals[k], k)
                assert 0 <= vals[k] <= {"roof_tilt": 90, "recommended_kw": 100, "cable_distance_m": 1000}.get(k, 100000)
            except (rules.RuleError, AssertionError):
                if k == "recommended_kw":
                    raise HTTPException(400, "Recommended size must be between 1 and 100 kW.")
                raise HTTPException(400, "%s must be a sensible positive number." % k.replace("_", " "))
    if body.get("system_type") and body["system_type"] != s["system_type"]:   # technician decides On-Grid / Off-Grid
        if body["system_type"] not in ("on_grid", "off_grid"):
            raise HTTPException(400, "Choose On-Grid or Off-Grid.")
        db.update("leads", s["lead_id"], {"system_type": body["system_type"]})
        db.note("survey", sid, "System type set to %s by the survey." % ("Off-Grid" if body["system_type"] == "off_grid" else "On-Grid"),
                user["id"])
        s = {**s, "system_type": body["system_type"]}
    if vals:
        db.update("surveys", sid, vals)
    if vals.get("recommended_kw") or body.get("system_type"):
        from ..catalog import ensure_package
        ensure_package(db, vals.get("recommended_kw") or s["recommended_kw"] or 0, s["system_type"])
    return {"ok": True}


@router.post("/surveys/{sid}/{action}")
def survey_action(sid: int, action: str, body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    s, lvl = _survey(db, user, sid, write=True)
    s = db.get("surveys", sid)
    if action == "done":
        rules.survey_mark_done(db, s, user["id"], strict=True)
    elif action == "approve":
        rules.survey_approve(db, s, user)
    elif action in ("reject", "reset"):
        if user["role"] not in ("sales", "director"):
            raise HTTPException(403, "Only Sales or the Director can do this.")
        used = db.one("SELECT ref FROM orders WHERE survey_id = ? AND state != 'cancel'", sid)
        if used:
            raise HTTPException(400, "Quotation %s is based on this survey. Cancel or delete it first." % used["ref"])
        if action == "reject":
            db.update("surveys", sid, {"state": "rejected", "rejection_reason": rules.text(body.get("reason"))[:300] or None})
            db.note("survey", sid, "Survey rejected: %s" % (body.get("reason") or "no reason given"), user["id"])
        else:
            db.update("surveys", sid, {"state": "scheduled"})
    elif action == "reschedule":   # new day / slot and/or technician (Sales or the Director)
        if user["role"] not in ("sales", "director"):
            raise HTTPException(403, "Only Sales or the Director can reschedule a visit.")
        rules.reschedule_survey(db, s, body.get("technician_id"), body.get("survey_date"), body.get("slot"), user["id"])
    else:
        raise HTTPException(404, "Unknown action.")
    return {"ok": True}


# ----------------------------------------------------------------- orders
@router.get("/orders")
def orders(state: str = "", q: str = "", user=Depends(staff_only), db=Depends(get_db)):
    lvl = need(user, "orders")
    sql = ("SELECT o.id, o.ref, o.state, o.kw, o.system_type, o.amount_total, o.date_order, o.valid_until, c.name AS customer, "
           "u.name AS salesperson, l.project_ref FROM orders o JOIN customers c ON c.id = o.customer_id "
           "LEFT JOIN users u ON u.id = o.salesperson_id LEFT JOIN leads l ON l.id = o.lead_id WHERE 1=1")
    args = []
    if lvl == "own":   # technician: quotes built from their own surveys
        sql += " AND o.survey_id IN (SELECT id FROM surveys WHERE technician_id = ?)"
        args.append(user["id"])
    if state == "quotes":
        sql += " AND o.state IN ('draft','sent')"
    elif state == "approval":
        sql += " AND o.approval_state = 'pending'"
    elif state:
        sql += " AND o.state = ?"
        args.append(state)
    if q:
        sql += " AND (c.name LIKE ? OR o.ref LIKE ? OR l.project_ref LIKE ?)"
        args += [like(q)] * 3
    rows = db.q(sql + " ORDER BY o.date_order DESC LIMIT 500", *args)
    for r in rows:
        r["state_label"] = rules.label(rules.ORDER_STATES, r["state"])
        r["paid"] = rules.order_paid(db, r["id"])
    counts = {r["state"]: r["n"] for r in db.q("SELECT state, COUNT(*) AS n FROM orders GROUP BY state")}
    return {"rows": rows, "counts": counts}


def _order(db, user, oid, write=False):
    lvl = need(user, "orders", write)
    o = db.one("SELECT o.*, c.name AS customer, c.email AS customer_email, c.phone AS customer_phone, "
               "c.street AS customer_street, c.city AS customer_city, u.name AS salesperson, l.project_ref FROM orders o "
               "JOIN customers c ON c.id = o.customer_id LEFT JOIN users u ON u.id = o.salesperson_id "
               "LEFT JOIN leads l ON l.id = o.lead_id WHERE o.id = ?", oid)
    if not o:
        raise HTTPException(404, "Order not found.")
    if lvl == "own" and db.val("SELECT technician_id FROM surveys WHERE id = ?", o["survey_id"]) != user["id"]:
        raise HTTPException(404, "Order not found.")
    return o


@router.get("/orders/{oid}")
def order(oid: int, user=Depends(staff_only), db=Depends(get_db)):
    o = _order(db, user, oid)
    lines = db.q("SELECT ol.*, p.code, p.is_kit FROM order_lines ol LEFT JOIN products p ON p.id = ol.product_id "
                 "WHERE ol.order_id = ? ORDER BY ol.id", oid)
    out = {**o, "access_token": None, "state_label": rules.label(rules.ORDER_STATES, o["state"]), "lines": lines,
           "paid": rules.order_paid(db, oid), "advance_needed": rules.advance_needed(db, o),
           "advance_due": rules.advance_due(db, o), "advance_pct": float(db.setting("advance_pct", 30)),
           "payments": db.q("SELECT id, ref, amount, method, state, date, purpose FROM payments WHERE order_id = ? ORDER BY id", oid),
           "invoices": db.q("SELECT * FROM invoices WHERE order_id = ? ORDER BY id", oid),
           "deliveries": db.q("SELECT id, ref, state, date_done FROM deliveries WHERE order_id = ?", oid),
           "jobs": db.q("SELECT id, ref, state, scheduled_at FROM jobs WHERE order_id = ?", oid),
           "subsidy": db.one("SELECT id, ref, state, amount_expected FROM subsidies WHERE order_id = ?", oid),
           "warranties": db.val("SELECT COUNT(*) FROM warranties WHERE order_id = ?", oid),
           "tickets": db.q("SELECT id, ref, stage FROM tickets WHERE order_id = ?", oid),
           "notes": notes_for(db, "order", oid), "can_edit": can_write(user, "orders"),
           "can_confirm": user["role"] in ("sales", "director"),
           "can_approve": user["role"] in ("sales", "director") and o["approval_state"] == "pending",
           "needs_approval": rules.discount_needs_approval(db, o),
           "discount_limit": float(db.setting("discount_approval_pct", 5)),
           "can_delete": can_delete(user, "orders"), "can_money": can_delete(user, "money"),
           "print_url": "/print/quote/%s?token=%s" % (oid, o["access_token"]),
           "subsidy_expected": rules.subsidy_expected(o["kw"])}
    if user["role"] == "director":
        out["financials"] = rules.order_financials(db, o)
        out["financials"]["stage_label"] = rules.JOB_STAGE_LABELS[out["financials"]["stage"]]
    return out


def _editable_quote(db, o, user):
    """A quote can change until the customer accepts it. Changing a sent quote takes it back to draft,
    so it's checked (discount approval) and sent again."""
    if o["state"] not in ("draft", "sent") or o.get("accepted_by"):
        raise HTTPException(400, "This quotation can't be changed any more (already accepted or confirmed).")
    if o["state"] == "sent":
        db.update("orders", o["id"], {"state": "draft"})
        db.note("order", o["id"], "Quote changed after sending: back to draft, send it again.", user["id"])


@router.put("/orders/{oid}/lines")
def order_lines(oid: int, body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    o = _order(db, user, oid, write=True)
    _editable_quote(db, o, user)
    for l in rules.as_list(body.get("lines"), dict):
        row = db.one("SELECT * FROM order_lines WHERE id = ? AND order_id = ?", rules.as_int(l.get("id")), oid)
        if not row:
            continue
        qty = rules.as_float(l.get("qty", row["qty"]), "quantity")
        if not 0 < qty <= 10000:
            raise HTTPException(400, "Quantities must be between 1 and 10,000 (delete a line to remove it).")
        disc = min(max(rules.as_float(l.get("discount", row["discount"]), "discount"), 0), 100)
        if user["role"] == "technician" and disc > 15:
            raise HTTPException(400, "Technicians can offer at most 15% (above 5% needs approval).")
        if user["role"] == "sales" and disc > 10:
            raise HTTPException(400, "Discounts above 10% need the Director.")
        if disc != row["discount"]:
            db.update("orders", oid, {"approval_state": None})   # a changed discount must be approved again
        db.update("order_lines", row["id"], {"qty": qty, "discount": disc})
    rules.recompute_order(db, oid)
    return {"ok": True}


@router.post("/orders/{oid}/schedule-installation")
def schedule_installation(oid: int, body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    """Sales sets the installation date once the customer has confirmed."""
    o = _order(db, user, oid, write=True)
    if user["role"] not in ("sales", "director"):
        raise HTTPException(403, "Only Sales or the Director can schedule installations.")
    if o["state"] != "sale":
        raise HTTPException(400, "Installations are scheduled once the order is confirmed.")
    job = db.one("SELECT * FROM jobs WHERE order_id = ? ORDER BY id LIMIT 1", oid)
    if not job:
        raise HTTPException(400, "This order has no installation job.")
    rules.schedule_installation(db, job, body.get("scheduled_at"), user)
    return {"ok": True}


@router.post("/orders/{oid}/{action}")
def order_action(oid: int, action: str, body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    o = _order(db, user, oid, write=True)
    o = db.get("orders", oid)
    if user["role"] == "technician" and action not in ("send", "add-line", "estimate"):
        raise HTTPException(403, "Sales confirms orders and records payments.")
    if action == "approve-discount":
        if user["role"] not in ("sales", "director"):
            raise HTTPException(403, "Only Sales or Admin can approve a discount.")
        db.update("orders", oid, {"approval_state": "approved"})
        db.note("order", oid, "Discount approved.", user["id"])
        return {"ok": True}
    if action == "send":
        if rules.discount_needs_approval(db, o):
            # keep the "waiting for approval" mark even though the send itself is refused
            db.update("orders", oid, {"approval_state": "pending"})
            db.note("order", oid, "Discount sent for approval.", user["id"])
            db.commit()
            raise HTTPException(400, "The discount is above %s%%, so Sales or Admin must approve it before the quote goes "
                                     "to the customer. It's now waiting for approval." % db.setting("discount_approval_pct", 5))
        rules.send_quote(db, o, user["id"])
    elif action == "confirm":
        rules.confirm_order(db, o, user["id"], accepted_by=rules.text(body.get("accepted_by")).strip() or None)
    elif action == "cancel":
        rules.cancel_order(db, o, user["id"])
    elif action == "payment":
        if user["role"] not in ("sales", "director"):
            raise HTTPException(403, "Only Sales or the Director can record payments.")
        method = body.get("method") if body.get("method") in ("cash", "bank", "upi", "cheque") else "bank"
        if db.val("SELECT COUNT(*) FROM payments WHERE order_id = ? AND amount = ? AND method = ? AND state = 'done' "
                  "AND created_by = ? AND date >= datetime('now', '-2 minutes')", oid, rules.r2(rules.as_float(body.get("amount"))),
                  method, user["id"]):
            raise HTTPException(400, "This payment was just recorded. Refresh to see it before adding it again.")
        rules.record_payment(db, o, rules.as_float(body.get("amount")), method, user["id"],
                             provider_ref=rules.text(body.get("reference"))[:80] or None,
                             purpose="advance" if o["state"] != "sale" or rules.advance_due(db, o) else "balance")
    elif action == "final-invoice":
        rules.final_invoice(db, o, user["id"])
    elif action == "estimate":
        rules.generation_estimate(db, o)
    elif action == "add-line":
        _editable_quote(db, o, user)
        p = db.get("products", rules.as_int(body.get("product_id")))
        if not p or not p["active"]:
            raise HTTPException(400, "Choose a product.")
        db.insert("order_lines", {"order_id": oid, "product_id": p["id"], "description": p["name"],
                                  "qty": max(rules.as_float(body.get("qty"), "quantity", 1), 0), "price_unit": p["price"],
                                  "tax_rate": p["tax_rate"]})
        rules.recompute_order(db, oid)
    else:
        raise HTTPException(404, "Unknown action.")
    return {"ok": True}


# -------------------------------------------------------------- customers
@router.get("/customers")
def customers(q: str = "", user=Depends(staff_only), db=Depends(get_db)):
    need(user, "customers")
    sql = ("SELECT c.*, (SELECT COUNT(*) FROM orders o WHERE o.customer_id = c.id AND o.state = 'sale') AS orders, "
           "(SELECT COUNT(*) FROM tickets t WHERE t.customer_id = c.id AND t.stage NOT IN ('closed','cancel')) AS open_tickets "
           "FROM customers c")
    args = []
    if q:
        sql += (" WHERE c.name LIKE ? OR c.phone LIKE ? OR c.email LIKE ? OR c.id IN "
                "(SELECT customer_id FROM serials WHERE name LIKE ?)")
        args = [like(q)] * 4
    return {"rows": db.q(sql + " ORDER BY c.name LIMIT 300", *args)}


@router.get("/customers/{cid}")
def customer(cid: int, user=Depends(staff_only), db=Depends(get_db)):
    need(user, "customers")
    c = found(db.get("customers", cid), "Customer not found.")
    orders = db.q("SELECT id, ref, state, kw, amount_total, date_order FROM orders WHERE customer_id = ? ORDER BY id DESC", cid)
    for o in orders:
        o["state_label"] = rules.label(rules.ORDER_STATES, o["state"])
    tickets = db.q("SELECT id, ref, stage, reported_on, description FROM tickets WHERE customer_id = ? ORDER BY id DESC", cid)
    for t in tickets:
        t["stage_label"] = rules.label(rules.TICKET_STAGES, t["stage"])
    return {**c, "orders": orders, "tickets": tickets,
            "leads": db.q("SELECT id, ref, stage, created_at FROM leads WHERE customer_id = ? ORDER BY id DESC", cid),
            "warranties": db.q("SELECT w.*, p.name AS product, s.name AS serial FROM warranties w JOIN products p ON p.id = w.product_id "
                               "JOIN serials s ON s.id = w.serial_id WHERE w.customer_id = ? ORDER BY w.end_date", cid),
            "has_login": bool(db.val("SELECT COUNT(*) FROM users WHERE customer_id = ?", cid)),
            "can_edit": can_write(user, "customers"), "can_delete": can_delete(user, "customers")}


# ---------------------------------------------------------------- subsidy
@router.get("/subsidies")
def subsidies(state: str = "", user=Depends(staff_only), db=Depends(get_db)):
    need(user, "subsidies")
    sql = ("SELECT s.*, c.name AS customer, o.ref AS order_ref FROM subsidies s JOIN customers c ON c.id = s.customer_id "
           "JOIN orders o ON o.id = s.order_id")
    args = []
    if state:
        sql += " WHERE s.state = ?"
        args.append(state)
    rows = db.q(sql + " ORDER BY s.id DESC", *args)
    for r in rows:
        r["state_label"] = rules.label(rules.SUBSIDY_STATES, r["state"])
    return {"rows": rows, "states": [{"value": k, "label": v} for k, v in rules.SUBSIDY_STATES]}


@router.get("/subsidies/{sid}")
def subsidy(sid: int, user=Depends(staff_only), db=Depends(get_db)):
    need(user, "subsidies")
    s = db.one("SELECT s.*, c.name AS customer, c.phone, o.ref AS order_ref, l.discom, l.consumer_no FROM subsidies s "
               "JOIN customers c ON c.id = s.customer_id JOIN orders o ON o.id = s.order_id "
               "LEFT JOIN leads l ON l.id = o.lead_id WHERE s.id = ?", sid)
    if not s:
        raise HTTPException(404, "Subsidy file not found.")
    return {**s, "state_label": rules.label(rules.SUBSIDY_STATES, s["state"]), "notes": notes_for(db, "subsidy", sid),
            "can_edit": can_write(user, "subsidies"), "can_delete": can_delete(user, "subsidies")}


@router.patch("/subsidies/{sid}")
def update_subsidy(sid: int, body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    need(user, "subsidies", write=True)
    s = found(db.get("subsidies", sid), "Subsidy file not found.")
    if s["state"] in ("disbursed", "rejected"):
        raise HTTPException(400, "This subsidy file is closed.")
    vals = clean(body, ("application_no", "amount_received", "doc_id_proof", "doc_bill", "doc_bank", "doc_photo", "doc_net_meter"))
    for k in ("doc_id_proof", "doc_bill", "doc_bank", "doc_photo", "doc_net_meter"):
        if k in vals:
            vals[k] = 1 if vals[k] else 0
    if vals.get("amount_received") is not None:
        try:
            vals["amount_received"] = rules.as_float(vals["amount_received"])
            assert 0 <= vals["amount_received"] <= 200000
        except (rules.RuleError, AssertionError):
            raise HTTPException(400, "Amount received must be a number up to ₹2,00,000.")
    db.update("subsidies", sid, vals)
    return {"ok": True}


SUBSIDY_FLOW = {"apply": ("draft", "applied", "applied_on"), "inspection": ("applied", "inspection", "inspection_on"),
                "approve": ("inspection", "approved", None), "disburse": ("approved", "disbursed", "disbursed_on"),
                "reject": ("*open*", "rejected", None)}


@router.post("/subsidies/{sid}/{action}")
def subsidy_action(sid: int, action: str, user=Depends(staff_only), db=Depends(get_db)):
    need(user, "subsidies", write=True)
    s = found(db.get("subsidies", sid), "Subsidy file not found.")
    if action not in SUBSIDY_FLOW:
        raise HTTPException(404, "Unknown action.")
    frm, to, date_field = SUBSIDY_FLOW[action]
    if frm == "*open*":
        if s["state"] in ("disbursed", "rejected"):
            raise HTTPException(400, "This file is %s." % rules.label(rules.SUBSIDY_STATES, s["state"]).lower())
    elif frm and s["state"] != frm:
        raise HTTPException(400, "This file is %s." % rules.label(rules.SUBSIDY_STATES, s["state"]).lower())
    if action == "apply" and not all(s[f] for f in ("doc_id_proof", "doc_bill", "doc_bank")):
        raise HTTPException(400, "Collect the ID proof, electricity bill and bank details before applying.")
    vals = {"state": to}
    if date_field:
        vals[date_field] = now()[:10]
    if action == "disburse":
        vals["amount_received"] = s["amount_received"] or s["amount_expected"]
    db.update("subsidies", sid, vals)
    db.note("subsidy", sid, "Status: %s." % rules.label(rules.SUBSIDY_STATES, to), user["id"])
    return {"ok": True}


# ======================================================================
# Delete / edit endpoints (CRUD). Permissions: access.ACCESS (write) and
# access.DELETE (delete). Each one also refuses when it would break history.
# ======================================================================
def _delete_quote(db, oid):
    """Remove a quotation that never became a real order (no money, no delivery, no job)."""
    o = db.get("orders", oid)
    for table, what in (("payments", "payments"), ("invoices", "invoices"), ("deliveries", "a delivery"),
                        ("jobs", "an installation job"), ("subsidies", "a subsidy file")):
        if db.val("SELECT COUNT(*) FROM %s WHERE order_id = ?" % table, oid):
            raise HTTPException(400, "%s has %s, so it can't be deleted. Cancel it instead." % (o["ref"], what))
    db.exec("DELETE FROM notes WHERE model = 'order' AND res_id = ?", oid)
    db.exec("DELETE FROM order_lines WHERE order_id = ?", oid)
    db.exec("DELETE FROM orders WHERE id = ?", oid)


@router.delete("/leads/{lid}")
def delete_lead(lid: int, user=Depends(staff_only), db=Depends(get_db)):
    need(user, "leads", write=True)
    need_delete(user, "leads")
    found(db.get("leads", lid), "Enquiry not found.")
    if db.val("SELECT COUNT(*) FROM orders WHERE lead_id = ? AND state = 'sale'", lid):
        raise HTTPException(400, "This enquiry has a confirmed order, so it can't be deleted. Mark it lost or cancel the order.")
    for o in db.q("SELECT id FROM orders WHERE lead_id = ?", lid):
        _delete_quote(db, o["id"])
    for s in db.q("SELECT id FROM surveys WHERE lead_id = ?", lid):
        db.exec("DELETE FROM notes WHERE model = 'survey' AND res_id = ?", s["id"])
    db.exec("DELETE FROM surveys WHERE lead_id = ?", lid)
    db.exec("DELETE FROM notes WHERE model = 'lead' AND res_id = ?", lid)
    db.exec("DELETE FROM leads WHERE id = ?", lid)
    return {"ok": True}


@router.delete("/surveys/{sid}")
def delete_survey(sid: int, user=Depends(staff_only), db=Depends(get_db)):
    need(user, "surveys", write=True)
    need_delete(user, "surveys")
    s = found(db.get("surveys", sid), "Survey not found.")
    used = db.one("SELECT ref FROM orders WHERE survey_id = ? AND state != 'cancel'", sid)
    if used:
        raise HTTPException(400, "Quotation %s is based on this survey, so it can't be deleted." % used["ref"])
    db.exec("UPDATE orders SET survey_id = NULL WHERE survey_id = ?", sid)
    db.exec("DELETE FROM notes WHERE model = 'survey' AND res_id = ?", sid)
    db.exec("DELETE FROM surveys WHERE id = ?", sid)
    lead = db.get("leads", s["lead_id"])
    if lead and lead["stage"] == "survey" and not db.val("SELECT COUNT(*) FROM surveys WHERE lead_id = ?", lead["id"]):
        db.update("leads", lead["id"], {"stage": "contacted"})
    db.note("lead", s["lead_id"], "Survey %s deleted." % s["ref"], user["id"])
    return {"ok": True}


@router.delete("/orders/{oid}")
def delete_order(oid: int, user=Depends(staff_only), db=Depends(get_db)):
    o = _order(db, user, oid, write=True)
    need_delete(user, "orders")
    if o["state"] == "sale":
        raise HTTPException(400, "Confirmed orders can't be deleted. Cancel the order instead.")
    _delete_quote(db, oid)
    if o["lead_id"]:
        lead = db.get("leads", o["lead_id"])
        if lead and lead["stage"] == "quoted" and not db.val("SELECT COUNT(*) FROM orders WHERE lead_id = ?", lead["id"]):
            db.update("leads", lead["id"], {"stage": "survey"})
        db.note("lead", o["lead_id"], "Quotation %s deleted." % o["ref"], user["id"])
    return {"ok": True}


@router.delete("/orders/{oid}/lines/{line_id}")
def delete_order_line(oid: int, line_id: int, user=Depends(staff_only), db=Depends(get_db)):
    o = _order(db, user, oid, write=True)
    _editable_quote(db, o, user)
    if db.val("SELECT COUNT(*) FROM order_lines WHERE order_id = ?", oid) <= 1:
        raise HTTPException(400, "A quotation needs at least one line.")
    db.exec("DELETE FROM order_lines WHERE id = ? AND order_id = ?", line_id, oid)
    rules.recompute_order(db, oid)
    return {"ok": True}


CUSTOMER_FIELDS = ("name", "phone", "email", "street", "city")


@router.post("/customers")
def create_customer(body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    need(user, "customers", write=True)
    vals = {k: rules.text(v).strip() or None for k, v in clean(body, CUSTOMER_FIELDS).items()}   # all text fields
    if not vals.get("name") or not vals.get("phone"):
        raise HTTPException(400, "Enter at least the customer's name and phone.")
    if vals.get("email"):
        vals["email"] = vals["email"].lower()
        if db.val("SELECT id FROM customers WHERE email = ? COLLATE NOCASE", vals["email"]):
            raise HTTPException(400, "A customer with this email already exists.")
    cid = db.insert("customers", {**vals, "created_at": now()})
    return {"ok": True, "id": cid}


@router.patch("/customers/{cid}")
def update_customer(cid: int, body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    need(user, "customers", write=True)
    c = found(db.get("customers", cid), "Customer not found.")
    vals = {k: rules.text(v).strip() or None for k, v in clean(body, CUSTOMER_FIELDS).items()}   # all text fields
    if "name" in vals and not vals["name"]:
        raise HTTPException(400, "The name can't be empty.")
    if vals.get("email"):
        vals["email"] = vals["email"].lower()
        if vals["email"] != (c["email"] or "").lower():
            if db.val("SELECT id FROM customers WHERE email = ? COLLATE NOCASE AND id != ?", vals["email"], cid):
                raise HTTPException(400, "Another customer already uses this email.")
            if db.val("SELECT COUNT(*) FROM users WHERE customer_id = ?", cid):
                raise HTTPException(400, "This customer signs in with their email, so it can't be changed here.")
    db.update("customers", cid, vals)
    db.exec("UPDATE users SET name = COALESCE(?, name), phone = COALESCE(?, phone) WHERE customer_id = ?",
            vals.get("name"), vals.get("phone"), cid)
    return {"ok": True}


@router.delete("/customers/{cid}")
def delete_customer(cid: int, user=Depends(staff_only), db=Depends(get_db)):
    need(user, "customers", write=True)
    need_delete(user, "customers")
    c = found(db.get("customers", cid), "Customer not found.")
    for table, what in (("orders", "orders"), ("leads", "enquiries"), ("tickets", "service requests"),
                        ("warranties", "warranties")):
        if db.val("SELECT COUNT(*) FROM %s WHERE customer_id = ?" % table, cid):
            raise HTTPException(400, "%s has %s, so the record must be kept." % (c["name"], what))
    for u in db.q("SELECT id FROM users WHERE customer_id = ?", cid):
        db.exec("DELETE FROM sessions WHERE user_id = ?", u["id"])
        db.exec("DELETE FROM tokens WHERE user_id = ?", u["id"])
        db.exec("DELETE FROM users WHERE id = ?", u["id"])
    db.exec("DELETE FROM customers WHERE id = ?", cid)
    return {"ok": True}


@router.delete("/subsidies/{sid}")
def delete_subsidy(sid: int, user=Depends(staff_only), db=Depends(get_db)):
    need(user, "subsidies", write=True)
    need_delete(user, "subsidies")
    s = found(db.get("subsidies", sid), "Subsidy file not found.")
    db.exec("DELETE FROM notes WHERE model = 'subsidy' AND res_id = ?", sid)
    db.exec("DELETE FROM subsidies WHERE id = ?", sid)
    db.note("order", s["order_id"], "Subsidy file %s deleted." % s["ref"], user["id"])
    return {"ok": True}


def _own_note(db, user, nid):
    n = found(db.get("notes", nid), "Note not found.")
    if n["kind"] != "note":
        raise HTTPException(400, "Automatic history entries can't be changed.")
    if n["author_id"] != user["id"] and user["role"] != "director":
        raise HTTPException(403, "You can only change your own notes.")
    return n


@router.patch("/notes/{nid}")
def update_note(nid: int, body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    n = _own_note(db, user, nid)
    if n["author_id"] != user["id"]:
        raise HTTPException(403, "You can only edit your own notes.")
    text = rules.text(body.get("body")).strip()
    if not text:
        raise HTTPException(400, "Write something, or delete the note.")
    db.exec("UPDATE notes SET body = ? WHERE id = ?", text[:2000], nid)
    return {"ok": True}


@router.delete("/notes/{nid}")
def delete_note(nid: int, user=Depends(staff_only), db=Depends(get_db)):
    _own_note(db, user, nid)
    db.exec("DELETE FROM notes WHERE id = ?", nid)
    return {"ok": True}
