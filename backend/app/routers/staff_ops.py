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
    reserved, unpaid = rules.reserved_stock(db), rules.unpaid_demand(db)
    planned = {}
    for d in rules.survey_demand(db):
        for pid, q in d["items"].items():
            planned[pid] = planned.get(pid, 0) + q
    for r in rows:
        r["reserved"] = reserved.get(r["id"], 0)
        r["unpaid_demand"] = unpaid.get(r["id"], 0)
        r["survey_demand"] = planned.get(r["id"], 0)
        r["available"] = r["qty_on_hand"] - r["reserved"]
        r["shortfall"] = max(r["reserved"] + r["unpaid_demand"] + r["survey_demand"] - r["qty_on_hand"], 0)
        r["low"] = not r["is_kit"] and not r["is_service"] and r["available"] < r["min_qty"]
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
    qty = rules.receive_stock(db, p, body.get("qty"), serials, user["id"], rules.text(body.get("note"))[:200] or None)
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
        sql += " AND (c.name LIKE ? OR d.ref LIKE ? OR o.ref LIKE ? OR d.project_ref LIKE ?)"
        args += [like(q)] * 4
    rows = db.q(sql + " ORDER BY CASE d.state WHEN 'ready' THEN 0 WHEN 'waiting' THEN 1 ELSE 2 END, d.id DESC LIMIT 300", *args)
    for r in rows:
        r["state_label"] = rules.label(rules.DELIVERY_STATES, r["state"])
        if r["state"] in ("done", "delivered"):
            r["short"] = None
        else:   # items whose stock doesn't cover this delivery's quantity
            r["short"] = db.val("SELECT COUNT(*) FROM delivery_lines dl JOIN products p ON p.id = dl.product_id "
                                "WHERE dl.delivery_id = ? AND p.qty_on_hand < dl.qty", r["id"])
    counts = {r["state"]: r["n"] for r in db.q("SELECT state, COUNT(*) AS n FROM deliveries GROUP BY state")}
    surveys = rules.survey_demand(db)
    need_total = {}
    for d in surveys:
        for pid, qty in d["items"].items():
            need_total[pid] = need_total.get(pid, 0) + qty
    reserved, unpaid = rules.reserved_stock(db), rules.unpaid_demand(db)
    short_items = 0
    for pid in set(need_total) | set(reserved) | set(unpaid):
        on_hand = db.val("SELECT qty_on_hand FROM products WHERE id = ?", pid) or 0
        if need_total.get(pid, 0) + reserved.get(pid, 0) + unpaid.get(pid, 0) > on_hand:
            short_items += 1
    return {"rows": rows, "counts": counts, "demand": {"surveys": len(surveys), "short_items": short_items}}


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
        if l["tracking"] == "serial" and d["state"] not in ("done", "delivered"):
            l["available"] = [r["name"] for r in db.q("SELECT name FROM serials WHERE product_id = ? AND state = 'in_stock' "
                                                       "ORDER BY id LIMIT 50", l["product_id"])]
        elif l["tracking"] == "lot" and d["state"] not in ("done", "delivered"):  # batches: suggest the ones in use
            l["available"] = [r["name"] for r in db.q("SELECT name FROM serials WHERE product_id = ? GROUP BY name "
                                                       "ORDER BY MAX(id) DESC LIMIT 5", l["product_id"])]
    reserved = rules.reserved_stock(db)
    mine = d["state"] in ("ready", "packed")
    for l in lines:   # free stock for this kit = on hand minus what other paid orders hold
        l["free"] = l["qty_on_hand"] - reserved.get(l["product_id"], 0) + (l["qty"] if mine else 0)
    return {**d, "state_label": rules.label(rules.DELIVERY_STATES, d["state"]), "lines": lines,
            "advance_due": rules.advance_due(db, order), "paid": rules.order_paid(db, order["id"]),
            "advance_needed": rules.advance_needed(db, order), "notes": notes_for(db, "delivery", did),
            "can_edit": can_write(user, "deliveries"), "can_override": user["role"] == "director"}


@router.post("/deliveries/{did}/validate")
def validate(did: int, body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    need(user, "deliveries", write=True)
    d = found(db.get("deliveries", did), "Delivery not found.")
    serials = body.get("serials") or {}
    if not isinstance(serials, dict):   # {delivery line id: [serial, ...]}
        raise HTTPException(400, "Scan the serial numbers for each line.")
    started = rules.validate_delivery(db, d, serials, user, override=bool(body.get("override")))
    vals = {"vehicle": rules.text(body.get("vehicle")).strip()[:120] or None}
    if body.get("expected_on"):
        vals["expected_on"] = str(body["expected_on"])[:10]
    db.update("deliveries", did, vals)
    return {"ok": True, "units": len(started)}   # serial / batch numbers recorded; warranties start at installation


@router.post("/deliveries/{did}/{action}")
def delivery_action(did: int, action: str, body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    need(user, "deliveries", write=True)
    d = found(db.get("deliveries", did), "Delivery not found.")
    if action == "pack":
        rules.pack_delivery(db, d, user)
    elif action == "deliver":
        rules.deliver_delivery(db, d, user, rules.text(body.get("note")).strip()[:200] or None)
    else:
        raise HTTPException(404, "Unknown action.")
    return {"ok": True}


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
    sql = ("SELECT j.id, j.ref, j.project_ref, j.state, j.scheduled_at, j.kw_planned, j.site_end, o.ref AS order_ref, c.name AS customer, c.city, "
           "(SELECT GROUP_CONCAT(u.name, ', ') FROM job_techs jt JOIN users u ON u.id = jt.user_id WHERE jt.job_id = j.id) AS crew "
           "FROM jobs j JOIN orders o ON o.id = j.order_id JOIN customers c ON c.id = j.customer_id WHERE 1=1")
    args = []
    if lvl == "own":
        sql += " AND j.id IN (SELECT job_id FROM job_techs WHERE user_id = ?)"
        args.append(user["id"])
    if state == "open":   # not finished yet (planned or on site)
        sql += " AND j.state != 'done'"
    elif state:
        sql += " AND j.state = ?"
        args.append(state)
    if q:
        sql += " AND (c.name LIKE ? OR j.ref LIKE ? OR c.city LIKE ? OR j.project_ref LIKE ?)"
        args += [like(q)] * 4
    rows = db.q(sql + " ORDER BY CASE j.state WHEN 'in_progress' THEN 0 WHEN 'planned' THEN 1 ELSE 2 END, j.scheduled_at LIMIT 300", *args)
    for r in rows:
        r["state_label"] = rules.label(rules.JOB_STATES, r["state"])
    mine = " WHERE id IN (SELECT job_id FROM job_techs WHERE user_id = %d)" % user["id"] if lvl == "own" else ""
    counts = {r["state"]: r["n"] for r in db.q("SELECT state, COUNT(*) AS n FROM jobs%s GROUP BY state" % mine)}
    counts["open"] = sum(n for s, n in counts.items() if s != "done")
    return {"rows": rows, "counts": counts}


@router.get("/jobs/{jid}")
def job(jid: int, user=Depends(staff_only), db=Depends(get_db)):
    j, techs, lvl = _job(db, user, jid)
    dispatched = bool(db.val("SELECT COUNT(*) FROM deliveries WHERE order_id = ? AND state IN ('done', 'delivered')", j["order_id"]))
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
    if vals.get("scheduled_at") is not None:
        vals["scheduled_at"] = rules.as_local_datetime(vals["scheduled_at"], "installation date")
        # A new date can't be in the past (an old job keeps its original date when other fields are saved).
        if vals["scheduled_at"] != j["scheduled_at"] and vals["scheduled_at"][:10] < rules.date.today().isoformat():
            raise HTTPException(400, "The installation can't be scheduled in the past.")
    for f, what in (("kw_confirmed", "installed size"), ("generation_reading_kw", "generation reading")):
        if vals.get(f) is not None:   # stored as numbers: the certificate and emails format them as kW
            v = rules.as_float(vals[f], what)
            if v > 1000 or v < 0 or (v == 0 and f == "kw_confirmed"):   # a reading of 0 (cloudy) is fine
                raise HTTPException(400, "The %s must be between 0 and 1000 kW." % what)
            vals[f] = v
    if vals.get("signature") and not str(vals["signature"]).startswith("data:image/"):
        raise HTTPException(400, "Invalid signature.")
    if vals.get("signature"):
        vals["signed_on"] = now()
    db.update("jobs", jid, vals)
    if lvl == "rw" and "techs" in body:
        db.exec("DELETE FROM job_techs WHERE job_id = ?", jid)
        for uid in rules.as_list(body.get("techs")):
            uid = rules.as_int(uid, "technician")
            if db.val("SELECT COUNT(*) FROM users WHERE id = ? AND role = 'technician' AND active = 1", uid):
                db.exec("INSERT OR IGNORE INTO job_techs (job_id, user_id) VALUES (?, ?)", jid, uid)
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
    elif a["owner_type"] == "survey":
        from .staff_sales import _survey
        _survey(db, user, a["owner_id"])
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
    sql = ("SELECT t.id, t.ref, t.project_ref, t.stage, t.priority, t.reported_on, t.description, t.warranty_id, c.name AS customer, "
           "p.name AS product, u.name AS technician FROM tickets t JOIN customers c ON c.id = t.customer_id "
           "LEFT JOIN products p ON p.id = t.product_id LEFT JOIN users u ON u.id = t.technician_id WHERE 1=1")
    args = []
    if lvl == "own":
        sql += " AND t.technician_id = ?"
        args.append(user["id"])
    if stage == "open":
        sql += " AND t.stage NOT IN ('closed','cancel')"
    elif stage == "active":   # someone has to work on it (not waiting for the customer)
        sql += " AND t.stage NOT IN ('closed','cancel','awaiting')"
    elif stage:
        sql += " AND t.stage = ?"
        args.append(stage)
    if q:
        sql += " AND (c.name LIKE ? OR t.ref LIKE ? OR t.description LIKE ? OR t.project_ref LIKE ?)"
        args += [like(q)] * 4
    rows = db.q(sql + " ORDER BY CASE WHEN t.stage IN ('closed','cancel') THEN 1 ELSE 0 END, t.priority DESC, t.reported_on DESC LIMIT 300", *args)
    for r in rows:
        r["stage_label"] = rules.label(rules.TICKET_STAGES, r["stage"])
        r["days_open"] = max((rules.parse_dt(now()) - rules.parse_dt(r["reported_on"])).days, 0)
    mine = " WHERE technician_id = %d" % user["id"] if lvl == "own" else ""
    counts = {r["stage"]: r["n"] for r in db.q("SELECT stage, COUNT(*) AS n FROM tickets%s GROUP BY stage" % mine)}
    counts["open"] = sum(n for s, n in counts.items() if s not in ("closed", "cancel"))
    counts["active"] = counts["open"] - counts.get("awaiting", 0)
    return {"rows": rows, "counts": counts, "stages": [{"value": k, "label": v} for k, v in rules.TICKET_STAGES]}


@router.post("/tickets")
def create_ticket(body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    need(user, "tickets", write=True)
    serial_id = None
    cid = rules.as_int(body.get("customer_id"))
    if body.get("serial"):
        s = db.one("SELECT * FROM serials WHERE name = ? AND customer_id IS NOT NULL", rules.text(body.get("serial")).strip())
        if not s:
            raise HTTPException(400, "No delivered equipment has serial %s." % body["serial"])
        serial_id, cid = s["id"], s["customer_id"]
    if not db.get("customers", cid):
        raise HTTPException(400, "Choose the customer (or enter a serial number).")
    tid = rules.create_ticket(db, cid, body.get("description"), user["id"], serial_id, body.get("fault_code"),
                              channel=body.get("channel") or "phone",
                              technician_id=rules.as_int(body.get("technician_id")) or None)
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
    if vals.get("technician_id") is not None:   # null / "" = unassign; anything else must be an active person
        vals["technician_id"] = rules.as_int(vals["technician_id"], "person")
    if vals.get("technician_id") is not None and not rules.is_active_role(db, vals["technician_id"], ("technician",)):
        raise HTTPException(400, "Choose an active technician.")
    if vals.get("priority") is not None and str(vals["priority"]) not in ("0", "1", "2"):
        raise HTTPException(400, "Priority must be normal, high or urgent.")
    if vals.get("labour_hours") is not None:
        try:
            vals["labour_hours"] = rules.as_float(vals["labour_hours"], "labour hours")
            assert 0 <= vals["labour_hours"] <= 200
        except (rules.RuleError, AssertionError):
            raise HTTPException(400, "Labour hours must be between 0 and 200.")
    if "ai_diagnosis" in body and body["ai_diagnosis"]:
        vals["ai_diagnosis"] = json.dumps(body["ai_diagnosis"])[:8000]
    db.update("tickets", tid, vals)
    if "lines" in body:
        db.exec("DELETE FROM ticket_lines WHERE ticket_id = ?", tid)
        for l in rules.as_list(body.get("lines"), dict):
            p = db.get("products", rules.as_int(l.get("product_id")))
            if p:
                qty = rules.as_float(l.get("qty"), "quantity", 1)
                if not 0 < qty <= 1000:
                    raise HTTPException(400, "Part quantities must be between 1 and 1000.")
                db.insert("ticket_lines", {"ticket_id": tid, "product_id": p["id"], "qty": qty,
                                           "price_unit": p["price"], "cost": p["cost"],
                                           "new_serial": rules.text(l.get("new_serial")).strip() or None})
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
        sql += " AND (s.name LIKE ? OR c.name LIKE ? OR c.phone LIKE ? OR o.ref LIKE ? OR w.project_ref LIKE ?)"
        args += [like(q)] * 5
    rows = db.q(sql + " ORDER BY w.end_date LIMIT 300", *args)
    for r in rows:
        r["active"] = r["start_date"] <= t0 <= r["end_date"]
    return {"rows": rows}


# ======================================================================
# Create / edit / delete (CRUD) for products, jobs, tickets, warranties.
# ======================================================================
@router.post("/products")
def create_product(body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    """New item (Warehouse or Director). The code is the item's unique key and never changes.
    Only the Director sets cost and selling price. Packages (kits) come from the catalogue, not from here."""
    need(user, "stock", write=True)
    if user["role"] not in ("director", "warehouse"):
        raise HTTPException(403, "Only the warehouse or the Director can add items.")
    code = rules.text(body.get("code")).strip().upper()[:30]
    name = rules.text(body.get("name")).strip()[:120]
    category = body.get("category")
    if not code or not name or category not in CATEGORIES or category in ("kit",):
        raise HTTPException(400, "Enter a code, a name and a category.")
    if not all(c.isalnum() or c in "-_/." for c in code):
        raise HTTPException(400, "Use letters, numbers and - _ / . in the code (e.g. CBL-DC6).")
    other = db.one("SELECT name, active FROM products WHERE code = ?", code)
    if other:
        raise HTTPException(400, "Code %s is already used by %s%s. Each item needs its own code." % (
            code, other["name"], "" if other["active"] else " (retired)"))
    tracking = body.get("tracking") if body.get("tracking") in ("none", "serial", "lot") else "none"

    def number(k, default=0):
        try:
            return max(rules.as_float(body.get(k), k, default), 0)
        except rules.RuleError:
            raise HTTPException(400, "%s must be a number." % k.replace("_", " "))
    pid = db.insert("products", {
        "code": code, "name": name, "category": category, "tracking": tracking,
        "cost": number("cost") if user["role"] == "director" else 0,
        "price": number("price") if user["role"] == "director" else 0,
        "location": rules.text(body.get("location")).strip()[:40] or None,
        "unit": rules.text(body.get("unit")).strip()[:12] or None,
        "tax_rate": number("tax_rate", GST_SERVICE if category == "service" else GST_GOODS),
        "warranty_months": int(number("warranty_months", CATEGORIES[category][1])),
        "min_qty": number("min_qty"), "is_service": 1 if category == "service" else 0})
    return {"ok": True, "id": pid}


@router.get("/products/{pid}")
def product(pid: int, user=Depends(staff_only), db=Depends(get_db)):
    """One item: details, stock movements, units in stock and who needs it."""
    need(user, "stock")
    p = found(db.get("products", pid), "Product not found.")
    if user["role"] != "director":
        p.pop("cost", None)
    p["moves"] = db.q("SELECT m.qty, m.kind, m.note, m.date, u.name AS user, d.ref AS delivery FROM stock_moves m "
                      "LEFT JOIN users u ON u.id = m.user_id LEFT JOIN deliveries d ON d.id = m.delivery_id "
                      "WHERE m.product_id = ? ORDER BY m.id DESC LIMIT 60", pid)
    p["serials"] = db.q("SELECT id, name, created_at FROM serials WHERE product_id = ? AND state = 'in_stock' ORDER BY id", pid) \
        if p["tracking"] == "serial" else []
    p["reserved"] = rules.reserved_stock(db).get(pid, 0)
    p["unpaid_demand"] = rules.unpaid_demand(db).get(pid, 0)
    demand = rules.survey_demand(db)
    p["survey_demand"] = sum(d["items"].get(pid, 0) for d in demand)
    p["available"] = p["qty_on_hand"] - p["reserved"]
    p["shortfall"] = max(p["reserved"] + p["unpaid_demand"] + p["survey_demand"] - p["qty_on_hand"], 0)
    p["can_price"] = user["role"] == "director"
    return p


@router.patch("/products/{pid}")
def update_product(pid: int, body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    """Warehouse: name, location, unit, reorder level, tracking (while nothing is in stock).
    Director: also prices, GST and warranty. The code never changes (orders and serials refer to it)."""
    need(user, "stock", write=True)
    if user["role"] not in ("director", "warehouse"):
        raise HTTPException(403, "Only the warehouse or the Director can edit items.")
    p = found(db.get("products", pid), "Product not found.")
    if "code" in body and rules.text(body["code"]).strip().upper() != p["code"]:
        raise HTTPException(400, "The item code can't be changed. Retire this item and add a new one instead.")
    money = ("price", "cost", "warranty_months", "tax_rate")
    if user["role"] != "director":
        for k in money:
            if body.get(k) in (None, ""):
                continue
            try:
                same = float(body[k]) == float(p[k] or 0)
            except (TypeError, ValueError):
                same = False
            if not same:
                raise HTTPException(403, "Only the Director can change prices, GST or warranty.")
    vals = {}
    for k in ("min_qty",) + (money if user["role"] == "director" else ()):
        if k in body and body[k] not in (None, ""):
            try:
                vals[k] = max(rules.as_float(body[k], k), 0)
            except rules.RuleError:
                raise HTTPException(400, "%s must be a number." % k.replace("_", " "))
    if "name" in body:
        name = rules.text(body.get("name")).strip()[:120]
        if not name:
            raise HTTPException(400, "Enter the item's name.")
        vals["name"] = name
    for k, size in (("location", 40), ("unit", 12)):
        if k in body:
            vals[k] = rules.text(body.get(k)).strip()[:size] or None
    if "category" in body and body["category"] != p["category"]:
        if body["category"] not in CATEGORIES or body["category"] in ("kit", "service") or p["is_kit"] or p["is_service"]:
            raise HTTPException(400, "Choose a component category.")
        vals["category"] = body["category"]
    if "tracking" in body and body["tracking"] != p["tracking"]:
        if body["tracking"] not in ("none", "serial", "lot"):
            raise HTTPException(400, "Choose how the item is tracked.")
        if p["qty_on_hand"] or db.val("SELECT COUNT(*) FROM serials WHERE product_id = ?", pid):
            raise HTTPException(400, "Tracking can only change while none of this item is in stock or on record.")
        vals["tracking"] = body["tracking"]
    if vals:
        db.update("products", pid, vals)
    return {"ok": True}


@router.post("/products/{pid}/adjust")
def adjust(pid: int, body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    need(user, "stock", write=True)
    if user["role"] not in ("director", "warehouse"):
        raise HTTPException(403, "Only the warehouse or the Director can correct stock.")
    p = found(db.get("products", pid), "Product not found.")
    return {"ok": True, "change": rules.adjust_stock(db, p, body.get("counted"), body.get("reason"), user["id"])}


@router.post("/serials/{sid}/scrap")
def scrap(sid: int, body: dict = Body(default={}), user=Depends(staff_only), db=Depends(get_db)):
    need(user, "stock", write=True)
    if user["role"] not in ("director", "warehouse"):
        raise HTTPException(403, "Only the warehouse or the Director can remove units.")
    rules.scrap_serial(db, found(db.get("serials", sid), "Serial not found."), body.get("reason"), user["id"])
    return {"ok": True}


@router.get("/demand")
def demand(user=Depends(staff_only), db=Depends(get_db)):
    """Material demand from visited surveys, per item, with what's on the shelves.
    The per-survey breakdown (customer names) is only for people who manage stock."""
    lvl = need(user, "stock")
    surveys = rules.survey_demand(db)
    totals = {}
    for d in surveys:
        for pid, q in d["items"].items():
            totals[pid] = totals.get(pid, 0) + q
    reserved, unpaid = rules.reserved_stock(db), rules.unpaid_demand(db)
    items = []
    for pid, q in totals.items():
        p = db.get("products", pid)
        need_total = reserved.get(pid, 0) + unpaid.get(pid, 0) + q
        items.append({"id": pid, "code": p["code"], "name": p["name"], "unit": p["unit"], "location": p["location"],
                      "on_hand": p["qty_on_hand"], "reserved": reserved.get(pid, 0), "unpaid_demand": unpaid.get(pid, 0),
                      "survey_demand": q, "shortfall": max(need_total - p["qty_on_hand"], 0)})
    items.sort(key=lambda r: (-r["shortfall"], r["code"]))
    out = {"items": items, "survey_count": len(surveys)}
    if lvl == "rw":
        names = {r["id"]: (r["code"], r["name"]) for r in db.q("SELECT id, code, name FROM products")}
        out["surveys"] = [{**{k: v for k, v in d.items() if k != "items"},
                           "items": [{"id": pid, "code": names[pid][0], "name": names[pid][1], "qty": q} for pid, q in d["items"].items()]}
                          for d in surveys]
    return out


@router.delete("/products/{pid}")
def retire_product(pid: int, user=Depends(staff_only), db=Depends(get_db)):
    """Products are never erased (old orders, serials and warranties point to them);
    retiring hides them from lists and new quotes."""
    need(user, "stock", write=True)
    need_delete(user, "stock")
    p = found(db.get("products", pid), "Product not found.")
    used = db.q("SELECT k.name FROM kit_lines kl JOIN products k ON k.id = kl.kit_id WHERE kl.product_id = ? AND k.active = 1", pid)
    if used:
        raise HTTPException(400, "%s is part of %d package(s) (e.g. %s). Change those packages first." % (
            p["name"], len(used), used[0]["name"]))
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
