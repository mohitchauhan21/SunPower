"""Staff: stock & serials, dispatch, installation jobs (+ photos), service
tickets, warranties."""
import json

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from .. import rules
from ..access import can_delete, can_write, need, need_delete
from ..catalog import CATEGORIES, GST_GOODS, GST_SERVICE
from ..db import get_db, now
from ..security import staff_only
from .staff_sales import clean, found, like, notes_for

router = APIRouter(prefix="/api/staff")
MAX_PHOTO = 8 * 1024 * 1024


def _image_type(data):
    """The real image type from the file's first bytes (the browser's label can't be trusted;
    an SVG or HTML file posing as a photo could run scripts when opened)."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


# ------------------------------------------------------------------ stock
@router.get("/products")
def products(q: str = "", category: str = "", user=Depends(staff_only), db=Depends(get_db)):
    need(user, "stock")
    sql = "SELECT * FROM products WHERE active = 1"
    args = []
    if category:
        sql += " AND category = ?"
        args.append(category)
    if q:
        sql += " AND (name LIKE ? OR code LIKE ?)"
        args += [like(q)] * 2
    rows = db.q(sql + " ORDER BY is_kit, is_service, category, code", *args)
    for r in rows:
        r["low"] = not r["is_kit"] and not r["is_service"] and r["qty_on_hand"] < r["min_qty"]
        if user["role"] != "director":
            r.pop("cost", None)
    return {"rows": rows}


@router.post("/products/{pid}/receive")
def receive(pid: int, body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    need(user, "stock", write=True)
    p = found(db.get("products", pid), "Product not found.")
    serials = body.get("serials") or []
    if isinstance(serials, str):
        serials = [s for s in serials.replace(",", "\n").splitlines()]
    qty = rules.receive_stock(db, p, body.get("qty"), serials, user["id"], (body.get("note") or "")[:200] or None)
    return {"ok": True, "qty": qty}


@router.get("/serials")
def serials(q: str = "", product_id: int = 0, state: str = "", user=Depends(staff_only), db=Depends(get_db)):
    need(user, "stock")
    sql = ("SELECT s.*, p.name AS product, c.name AS customer FROM serials s JOIN products p ON p.id = s.product_id "
           "LEFT JOIN customers c ON c.id = s.customer_id WHERE 1=1")
    args = []
    if product_id:
        sql += " AND s.product_id = ?"
        args.append(product_id)
    if state:
        sql += " AND s.state = ?"
        args.append(state)
    if q:
        sql += " AND (s.name LIKE ? OR c.name LIKE ?)"
        args += [like(q)] * 2
    return {"rows": db.q(sql + " ORDER BY s.id DESC LIMIT 300", *args)}


# --------------------------------------------------------------- dispatch
@router.get("/deliveries")
def deliveries(state: str = "", q: str = "", user=Depends(staff_only), db=Depends(get_db)):
    need(user, "deliveries")
    sql = ("SELECT d.*, o.ref AS order_ref, o.kw, c.name AS customer, c.city FROM deliveries d JOIN orders o ON o.id = d.order_id "
           "JOIN customers c ON c.id = o.customer_id WHERE 1=1")
    args = []
    if state:
        sql += " AND d.state = ?"
        args.append(state)
    if q:
        sql += " AND (c.name LIKE ? OR d.ref LIKE ? OR o.ref LIKE ?)"
        args += [like(q)] * 3
    rows = db.q(sql + " ORDER BY CASE d.state WHEN 'ready' THEN 0 WHEN 'waiting' THEN 1 ELSE 2 END, d.id DESC LIMIT 300", *args)
    for r in rows:
        r["state_label"] = rules.label(rules.DELIVERY_STATES, r["state"])
    counts = {r["state"]: r["n"] for r in db.q("SELECT state, COUNT(*) AS n FROM deliveries GROUP BY state")}
    return {"rows": rows, "counts": counts}


@router.get("/deliveries/{did}")
def delivery(did: int, user=Depends(staff_only), db=Depends(get_db)):
    need(user, "deliveries")
    d = found(db.one("SELECT d.*, o.ref AS order_ref, o.id AS order_id, o.amount_total, c.name AS customer, c.phone, c.street, "
                     "c.city FROM deliveries d JOIN orders o ON o.id = d.order_id JOIN customers c ON c.id = o.customer_id "
                     "WHERE d.id = ?", did), "Delivery not found.")
    order = db.get("orders", d["order_id"])
    lines = db.q("SELECT dl.*, p.code, p.name, p.tracking, p.qty_on_hand, p.warranty_months FROM delivery_lines dl "
                 "JOIN products p ON p.id = dl.product_id WHERE dl.delivery_id = ? ORDER BY p.tracking DESC, p.code", did)
    for l in lines:
        l["serials"] = json.loads(l["serials"]) if l["serials"] else []
        if l["tracking"] == "serial" and d["state"] != "done":
            l["available"] = [r["name"] for r in db.q("SELECT name FROM serials WHERE product_id = ? AND state = 'in_stock' "
                                                       "ORDER BY id LIMIT 50", l["product_id"])]
        elif l["tracking"] == "lot" and d["state"] != "done":  # batches: suggest the ones in use
            l["available"] = [r["name"] for r in db.q("SELECT name FROM serials WHERE product_id = ? GROUP BY name "
                                                       "ORDER BY MAX(id) DESC LIMIT 5", l["product_id"])]
    return {**d, "state_label": rules.label(rules.DELIVERY_STATES, d["state"]), "lines": lines,
            "advance_due": rules.advance_due(db, order), "paid": rules.order_paid(db, order["id"]),
            "advance_needed": rules.advance_needed(db, order), "notes": notes_for(db, "delivery", did),
            "can_edit": can_write(user, "deliveries"), "can_override": user["role"] == "director"}


@router.post("/deliveries/{did}/validate")
def validate(did: int, body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    need(user, "deliveries", write=True)
    d = found(db.get("deliveries", did), "Delivery not found.")
    started = rules.validate_delivery(db, d, body.get("serials") or {}, user, override=bool(body.get("override")))
    return {"ok": True, "warranties": len(started)}


# ------------------------------------------------------------------- jobs
JOB_TECH_FIELDS = ("chk_stands", "chk_panels", "chk_wiring", "chk_earthing", "chk_generation", "kw_confirmed",
                   "generation_reading_kw", "signed_by", "signature", "notes", "photo_check")


def _job(db, user, jid, write=False):
    lvl = need(user, "jobs", write)
    j = found(db.one("SELECT j.*, o.ref AS order_ref, o.system_type, c.name AS customer, c.phone, c.street, c.city "
                     "FROM jobs j JOIN orders o ON o.id = j.order_id JOIN customers c ON c.id = j.customer_id WHERE j.id = ?", jid),
              "Job not found.")
    techs = db.q("SELECT u.id, u.name FROM job_techs jt JOIN users u ON u.id = jt.user_id WHERE jt.job_id = ?", jid)
    if lvl == "own" and user["id"] not in [t["id"] for t in techs]:
        raise HTTPException(404, "Job not found.")
    return j, techs, lvl


@router.get("/jobs")
def jobs(state: str = "", q: str = "", user=Depends(staff_only), db=Depends(get_db)):
    lvl = need(user, "jobs")
    sql = ("SELECT j.id, j.ref, j.state, j.scheduled_at, j.kw_planned, j.site_end, o.ref AS order_ref, c.name AS customer, c.city, "
           "(SELECT GROUP_CONCAT(u.name, ', ') FROM job_techs jt JOIN users u ON u.id = jt.user_id WHERE jt.job_id = j.id) AS crew "
           "FROM jobs j JOIN orders o ON o.id = j.order_id JOIN customers c ON c.id = j.customer_id WHERE 1=1")
    args = []
    if lvl == "own":
        sql += " AND j.id IN (SELECT job_id FROM job_techs WHERE user_id = ?)"
        args.append(user["id"])
    if state:
        sql += " AND j.state = ?"
        args.append(state)
    if q:
        sql += " AND (c.name LIKE ? OR j.ref LIKE ? OR c.city LIKE ?)"
        args += [like(q)] * 3
    rows = db.q(sql + " ORDER BY CASE j.state WHEN 'in_progress' THEN 0 WHEN 'planned' THEN 1 ELSE 2 END, j.scheduled_at LIMIT 300", *args)
    for r in rows:
        r["state_label"] = rules.label(rules.JOB_STATES, r["state"])
    return {"rows": rows}


@router.get("/jobs/{jid}")
def job(jid: int, user=Depends(staff_only), db=Depends(get_db)):
    j, techs, lvl = _job(db, user, jid)
    dispatched = bool(db.val("SELECT COUNT(*) FROM deliveries WHERE order_id = ? AND state = 'done'", j["order_id"]))
    return {**j, "state_label": rules.label(rules.JOB_STATES, j["state"]), "techs": techs,
            "checklist": [{"field": f, "label": l, "done": bool(j[f])} for f, l in rules.CHECKLIST],
            "photos": db.q("SELECT id, filename, note, created_at FROM attachments WHERE owner_type = 'job' AND owner_id = ?", jid),
            "warranties": db.q("SELECT w.end_date, p.name AS product, s.name AS serial FROM warranties w JOIN products p ON p.id = w.product_id "
                               "JOIN serials s ON s.id = w.serial_id WHERE w.order_id = ?", j["order_id"]),
            "dispatched": dispatched, "notes_log": notes_for(db, "job", jid), "can_edit": lvl in ("rw", "own"),
            "can_assign": lvl == "rw", "can_delete": can_delete(user, "jobs"),
            "certificate_url": "/print/certificate/%s?token=%s" % (jid, db.val("SELECT access_token FROM orders WHERE id = ?", j["order_id"]))
            if j["state"] == "done" else None}


@router.patch("/jobs/{jid}")
def update_job(jid: int, body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    j, techs, lvl = _job(db, user, jid, write=True)
    if j["state"] == "done":
        raise HTTPException(400, "This job is completed.")
    vals = clean(body, JOB_TECH_FIELDS + (("scheduled_at",) if lvl == "rw" else ()))
    for f in ("chk_stands", "chk_panels", "chk_wiring", "chk_earthing", "chk_generation"):
        if f in vals:
            vals[f] = 1 if vals[f] else 0
    if vals.get("signature") and not str(vals["signature"]).startswith("data:image/"):
        raise HTTPException(400, "Invalid signature.")
    if vals.get("signature"):
        vals["signed_on"] = now()
    db.update("jobs", jid, vals)
    if lvl == "rw" and "techs" in body:
        db.exec("DELETE FROM job_techs WHERE job_id = ?", jid)
        for uid in body.get("techs") or []:
            if db.val("SELECT COUNT(*) FROM users WHERE id = ? AND role = 'technician' AND active = 1", int(uid)):
                db.insert("job_techs", {"job_id": jid, "user_id": int(uid)})
    return {"ok": True}


@router.post("/jobs/{jid}/photos")
async def job_photo(jid: int, file: UploadFile = File(...), note: str = Form(""), user=Depends(staff_only),
                    db=Depends(get_db)):
    j, _techs, _lvl = _job(db, user, jid, write=True)
    data = await file.read(MAX_PHOTO + 1)
    mime = _image_type(data)
    if not mime or len(data) > MAX_PHOTO:
        raise HTTPException(400, "Upload a photo (JPG, PNG or WebP, up to 8 MB).")
    aid = db.insert("attachments", {"owner_type": "job", "owner_id": jid, "filename": (file.filename or "photo")[:120], "mime": mime,
                                    "data": data, "note": note[:200] or None, "created_at": now()})
    if note:
        db.update("jobs", jid, {"photo_check": note[:200]})
    return {"ok": True, "id": aid}


@router.post("/jobs/{jid}/{action}")
def job_action(jid: int, action: str, user=Depends(staff_only), db=Depends(get_db)):
    _job(db, user, jid, write=True)
    j = db.get("jobs", jid)
    if action == "start":
        rules.job_start(db, j, user["id"])
    elif action == "finish":
        rules.job_finish(db, j, user)
    else:
        raise HTTPException(404, "Unknown action.")
    return {"ok": True}


@router.get("/attachments/{aid}")
def attachment(aid: int, user=Depends(staff_only), db=Depends(get_db)):
    a = found(db.get("attachments", aid), "Not found.")
    if a["owner_type"] == "job":
        _job(db, user, a["owner_id"])
    safe = a["mime"] if a["mime"] in ("image/jpeg", "image/png", "image/webp") else "application/octet-stream"
    return Response(a["data"], media_type=safe,
                    headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff",
                             "Content-Security-Policy": "default-src 'none'; sandbox"})


# ---------------------------------------------------------------- tickets
def _ticket(db, user, tid, write=False):
    lvl = need(user, "tickets", write)
    t = found(db.one("SELECT t.*, c.name AS customer, c.phone, c.street, c.city, p.name AS product, s.name AS serial, "
                     "u.name AS technician, o.ref AS order_ref FROM tickets t JOIN customers c ON c.id = t.customer_id "
                     "LEFT JOIN products p ON p.id = t.product_id LEFT JOIN serials s ON s.id = t.serial_id "
                     "LEFT JOIN users u ON u.id = t.technician_id LEFT JOIN orders o ON o.id = t.order_id WHERE t.id = ?", tid),
              "Request not found.")
    if lvl == "own" and t["technician_id"] != user["id"]:
        raise HTTPException(404, "Request not found.")
    return t, lvl


@router.get("/tickets")
def tickets(stage: str = "", q: str = "", user=Depends(staff_only), db=Depends(get_db)):
    lvl = need(user, "tickets")
    sql = ("SELECT t.id, t.ref, t.stage, t.priority, t.reported_on, t.description, t.warranty_id, c.name AS customer, "
           "p.name AS product, u.name AS technician FROM tickets t JOIN customers c ON c.id = t.customer_id "
           "LEFT JOIN products p ON p.id = t.product_id LEFT JOIN users u ON u.id = t.technician_id WHERE 1=1")
    args = []
    if lvl == "own":
        sql += " AND t.technician_id = ?"
        args.append(user["id"])
    if stage == "open":
        sql += " AND t.stage NOT IN ('closed','cancel')"
    elif stage:
        sql += " AND t.stage = ?"
        args.append(stage)
    if q:
        sql += " AND (c.name LIKE ? OR t.ref LIKE ? OR t.description LIKE ?)"
        args += [like(q)] * 3
    rows = db.q(sql + " ORDER BY CASE WHEN t.stage IN ('closed','cancel') THEN 1 ELSE 0 END, t.priority DESC, t.reported_on DESC LIMIT 300", *args)
    for r in rows:
        r["stage_label"] = rules.label(rules.TICKET_STAGES, r["stage"])
        r["days_open"] = max((rules.parse_dt(now()) - rules.parse_dt(r["reported_on"])).days, 0)
    return {"rows": rows, "stages": [{"value": k, "label": v} for k, v in rules.TICKET_STAGES]}


@router.post("/tickets")
def create_ticket(body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    need(user, "tickets", write=True)
    serial_id = None
    cid = int(body.get("customer_id") or 0)
    if body.get("serial"):
        s = db.one("SELECT * FROM serials WHERE name = ? AND customer_id IS NOT NULL", body["serial"].strip())
        if not s:
            raise HTTPException(400, "No delivered equipment has serial %s." % body["serial"])
        serial_id, cid = s["id"], s["customer_id"]
    if not db.get("customers", cid):
        raise HTTPException(400, "Choose the customer (or enter a serial number).")
    tid = rules.create_ticket(db, cid, body.get("description"), user["id"], serial_id, body.get("fault_code"),
                              channel=body.get("channel") or "phone",
                              technician_id=int(body.get("technician_id") or 0) or None)
    return {"ok": True, "id": tid}


@router.get("/tickets/{tid}")
def ticket(tid: int, user=Depends(staff_only), db=Depends(get_db)):
    t, lvl = _ticket(db, user, tid)
    lines = db.q("SELECT tl.*, p.name AS product FROM ticket_lines tl JOIN products p ON p.id = tl.product_id WHERE tl.ticket_id = ?", tid)
    if user["role"] != "director":
        for l in lines:
            l.pop("cost", None)
    amounts = rules.ticket_amounts(db, t)
    if user["role"] != "director":
        amounts.pop("repair_cost", None)
    return {**t, "stage_label": rules.label(rules.TICKET_STAGES, t["stage"]), "lines": lines, **amounts,
            "ai_diagnosis": json.loads(t["ai_diagnosis"]) if t["ai_diagnosis"] else None,
            "invoice": db.get("invoices", t["invoice_id"]) if t["invoice_id"] else None,
            "notes": notes_for(db, "ticket", tid), "can_edit": lvl in ("rw", "own"), "can_assign": lvl == "rw",
            "can_delete": can_delete(user, "tickets"),
            "days_open": max((rules.parse_dt(t["closed_on"] or now()) - rules.parse_dt(t["reported_on"])).days, 0)}


@router.patch("/tickets/{tid}")
def update_ticket(tid: int, body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    t, lvl = _ticket(db, user, tid, write=True)
    if t["stage"] in ("closed", "cancel"):
        raise HTTPException(400, "This request is closed.")
    fields = ("resolution", "labour_hours", "fault_code") + (("technician_id", "priority") if lvl == "rw" else ())
    vals = clean(body, fields)
    if vals.get("technician_id") and not rules.is_active_role(db, vals["technician_id"], ("technician",)):
        raise HTTPException(400, "Choose an active technician.")
    if vals.get("priority") is not None and str(vals["priority"]) not in ("0", "1", "2"):
        raise HTTPException(400, "Priority must be normal, high or urgent.")
    if vals.get("labour_hours") is not None:
        try:
            vals["labour_hours"] = float(vals["labour_hours"])
            assert 0 <= vals["labour_hours"] <= 200
        except (TypeError, ValueError, AssertionError):
            raise HTTPException(400, "Labour hours must be between 0 and 200.")
    if "ai_diagnosis" in body and body["ai_diagnosis"]:
        vals["ai_diagnosis"] = json.dumps(body["ai_diagnosis"])[:8000]
    db.update("tickets", tid, vals)
    if "lines" in body:
        db.exec("DELETE FROM ticket_lines WHERE ticket_id = ?", tid)
        for l in body.get("lines") or []:
            p = db.get("products", int(l.get("product_id") or 0))
            if p:
                qty = float(l.get("qty") or 1)
                if not 0 < qty <= 1000:
                    raise HTTPException(400, "Part quantities must be between 1 and 1000.")
                db.insert("ticket_lines", {"ticket_id": tid, "product_id": p["id"], "qty": qty,
                                           "price_unit": p["price"], "cost": p["cost"],
                                           "new_serial": (l.get("new_serial") or "").strip() or None})
    return {"ok": True}


@router.post("/tickets/{tid}/{action}")
def ticket_action(tid: int, action: str, user=Depends(staff_only), db=Depends(get_db)):
    _t, lvl = _ticket(db, user, tid, write=True)
    t = db.get("tickets", tid)
    allowed = {"diagnose": ("new",), "repair": ("new", "diagnosed"), "cancel": ("new", "diagnosed", "repair")}
    if action in allowed and t["stage"] not in allowed[action]:
        raise HTTPException(400, "This request is %s, so it can't be moved there." % rules.label(rules.TICKET_STAGES, t["stage"]).lower())
    if action == "cancel" and lvl != "rw":
        raise HTTPException(403, "Only the service desk can cancel a request.")
    if action == "reopen" and t["stage"] not in ("awaiting", "closed"):
        raise HTTPException(400, "Only finished requests can be reopened.")
    if action == "diagnose":
        db.update("tickets", tid, {"stage": "diagnosed"})
    elif action == "repair":
        if not t["technician_id"]:
            raise HTTPException(400, "Assign a technician first.")
        db.update("tickets", tid, {"stage": "repair"})
    elif action == "resolve":
        rules.ticket_resolve(db, t, user["id"])
    elif action == "confirm":
        rules.ticket_confirm(db, t, user["id"])
    elif action == "reopen":
        rules.ticket_reopen(db, t, user["id"])
    elif action == "cancel":
        db.update("tickets", tid, {"stage": "cancel", "closed_on": now()})
    else:
        raise HTTPException(404, "Unknown action.")
    if action in ("diagnose", "repair", "cancel"):
        db.note("ticket", tid, "Status: %s." % rules.label(rules.TICKET_STAGES, db.get("tickets", tid)["stage"]), user["id"])
    return {"ok": True}


# ------------------------------------------------------------- warranties
@router.get("/warranties")
def warranties(q: str = "", status: str = "", user=Depends(staff_only), db=Depends(get_db)):
    lvl = need(user, "warranties")
    sql = ("SELECT w.*, p.name AS product, s.name AS serial, c.name AS customer, c.phone, o.ref AS order_ref FROM warranties w "
           "JOIN products p ON p.id = w.product_id JOIN serials s ON s.id = w.serial_id JOIN customers c ON c.id = w.customer_id "
           "LEFT JOIN orders o ON o.id = w.order_id WHERE 1=1")
    args = []
    if lvl == "own":
        sql += " AND w.order_id IN (SELECT j.order_id FROM jobs j JOIN job_techs jt ON jt.job_id = j.id WHERE jt.user_id = ?)"
        args.append(user["id"])
    t0 = now()[:10]
    if status == "active":
        sql += " AND w.end_date >= ?"
        args.append(t0)
    elif status == "expired":
        sql += " AND w.end_date < ?"
        args.append(t0)
    if q:
        sql += " AND (s.name LIKE ? OR c.name LIKE ? OR c.phone LIKE ? OR o.ref LIKE ?)"
        args += [like(q)] * 4
    rows = db.q(sql + " ORDER BY w.end_date LIMIT 300", *args)
    for r in rows:
        r["active"] = r["start_date"] <= t0 <= r["end_date"]
    return {"rows": rows}


# ======================================================================
# Create / edit / delete (CRUD) for products, jobs, tickets, warranties.
# ======================================================================
@router.post("/products")
def create_product(body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    """New component (Director). Packages (kits) come from the catalogue, not from here."""
    need(user, "stock", write=True)
    if user["role"] != "director":
        raise HTTPException(403, "Only the Director can add products.")
    code = (body.get("code") or "").strip().upper()[:30]
    name = (body.get("name") or "").strip()[:120]
    category = body.get("category")
    if not code or not name or category not in CATEGORIES or category in ("kit",):
        raise HTTPException(400, "Enter a code, a name and a category.")
    if db.val("SELECT id FROM products WHERE code = ?", code):
        raise HTTPException(400, "Another product already uses code %s." % code)
    tracking = body.get("tracking") if body.get("tracking") in ("none", "serial", "lot") else "none"

    def number(k, default=0):
        try:
            return max(float(body.get(k) if body.get(k) not in (None, "") else default), 0)
        except (TypeError, ValueError):
            raise HTTPException(400, "%s must be a number." % k.replace("_", " "))
    pid = db.insert("products", {
        "code": code, "name": name, "category": category, "tracking": tracking,
        "cost": number("cost"), "price": number("price"),
        "tax_rate": number("tax_rate", GST_SERVICE if category == "service" else GST_GOODS),
        "warranty_months": int(number("warranty_months", CATEGORIES[category][1])),
        "min_qty": number("min_qty"), "is_service": 1 if category == "service" else 0})
    return {"ok": True, "id": pid}


@router.delete("/products/{pid}")
def retire_product(pid: int, user=Depends(staff_only), db=Depends(get_db)):
    """Products are never erased (old orders, serials and warranties point to them);
    retiring hides them from lists and new quotes."""
    need(user, "stock", write=True)
    need_delete(user, "stock")
    p = found(db.get("products", pid), "Product not found.")
    if p["qty_on_hand"] > 0 and not p["is_kit"] and not p["is_service"]:
        raise HTTPException(400, "%g of %s are still in stock. Use them up or adjust stock first." % (p["qty_on_hand"], p["name"]))
    db.update("products", pid, {"active": 0})
    return {"ok": True}


@router.delete("/jobs/{jid}")
def delete_job(jid: int, user=Depends(staff_only), db=Depends(get_db)):
    """Remove a duplicate or no-longer-needed installation job (Director)."""
    j, _techs, _lvl = _job(db, user, jid, write=True)
    need_delete(user, "jobs")
    if j["state"] != "planned":
        raise HTTPException(400, "Only planned jobs can be deleted. This one has already started.")
    if db.val("SELECT COUNT(*) FROM timesheets WHERE job_id = ?", jid):
        raise HTTPException(400, "Hours are logged on this job, so it must be kept.")
    order = db.get("orders", j["order_id"])
    others = db.val("SELECT COUNT(*) FROM jobs WHERE order_id = ? AND id != ?", j["order_id"], jid)
    if order["state"] == "sale" and not others:
        raise HTTPException(400, "This is the only installation job for %s. Cancel the order instead, or reschedule the job." % order["ref"])
    db.exec("DELETE FROM attachments WHERE owner_type = 'job' AND owner_id = ?", jid)
    db.exec("DELETE FROM notes WHERE model = 'job' AND res_id = ?", jid)
    db.exec("DELETE FROM jobs WHERE id = ?", jid)
    db.note("order", j["order_id"], "Installation job %s deleted." % j["ref"], user["id"])
    return {"ok": True}


@router.delete("/tickets/{tid}")
def delete_ticket(tid: int, user=Depends(staff_only), db=Depends(get_db)):
    """Remove a request logged by mistake or twice (Director, Service desk)."""
    t, _lvl = _ticket(db, user, tid, write=True)
    need_delete(user, "tickets")
    if t["invoice_id"]:
        raise HTTPException(400, "This request has an invoice, so it must be kept. Cancel it instead.")
    db.exec("DELETE FROM notes WHERE model = 'ticket' AND res_id = ?", tid)
    db.exec("DELETE FROM tickets WHERE id = ?", tid)
    return {"ok": True}


@router.patch("/warranties/{wid}")
def update_warranty(wid: int, body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    """Extend or correct a warranty (Director only, e.g. a goodwill extension)."""
    need(user, "warranties", write=True)
    if user["role"] != "director":
        raise HTTPException(403, "Only the Director can change a warranty.")
    w = found(db.get("warranties", wid), "Warranty not found.")
    try:
        months = int(body.get("months", w["months"]))
        start = rules.date.fromisoformat(str(body.get("start_date", w["start_date"]))[:10])
    except (TypeError, ValueError):
        raise HTTPException(400, "Enter the months as a number and the start as a date.")
    if not 0 < months <= 600:
        raise HTTPException(400, "Months must be between 1 and 600.")
    db.update("warranties", wid, {"months": months, "start_date": start.isoformat(),
                                  "end_date": rules.add_months(start, months).isoformat()})
    db.note("order", w["order_id"], "Warranty of serial #%s changed to %s months from %s." % (w["serial_id"], months, start), user["id"])
    return {"ok": True}
