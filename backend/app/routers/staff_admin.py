"""Staff: overview (role-aware), Director dashboard, reports, settings, users."""
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException

from .. import mailer, rules
from ..access import need
from ..db import get_db, now
from ..security import ROLES, STAFF, director_only, make_token, staff_only
from .staff_sales import found

router = APIRouter(prefix="/api/staff")


def _range(period):
    start, end = rules.period_bounds(period)
    return start, end, datetime.combine(start, time.min).strftime("%Y-%m-%d %H:%M:%S"), \
        datetime.combine(end, time.max).strftime("%Y-%m-%d %H:%M:%S")


def dashboard_data(db, period="month"):
    start, end, ds, de = _range(period)
    won = db.q("SELECT * FROM orders WHERE state = 'sale' AND confirmed_at BETWEEN ? AND ?", ds, de)
    all_jobs = db.q("SELECT * FROM orders WHERE state = 'sale'")
    fin = {o["id"]: rules.order_financials(db, o) for o in all_jobs}
    jobs = []
    for o in (won if period != "today" else all_jobs)[:60]:
        f = fin[o["id"]]
        jobs.append({"id": o["id"], "name": o["ref"], "customer": db.val("SELECT name FROM customers WHERE id = ?", o["customer_id"]),
                     "kw": o["kw"], "type": "On-Grid" if o["system_type"] == "on_grid" else "Off-Grid",
                     "revenue": o["amount_untaxed"], "material": f["material"], "labour": f["labour"], "repair": f["repair"],
                     "profit": f["profit"], "margin": f["margin"], "stage": rules.JOB_STAGE_LABELS[f["stage"]],
                     "pending": ", ".join(f["pending"])})
    jobs.sort(key=lambda j: j["profit"])
    open_tickets = db.q("SELECT t.*, c.name AS customer, p.name AS product FROM tickets t JOIN customers c ON c.id = t.customer_id "
                        "LEFT JOIN products p ON p.id = t.product_id WHERE t.stage NOT IN ('closed','cancel') ORDER BY t.reported_on")
    nowdt = rules.parse_dt(now())
    for t in open_tickets:
        t["days"] = (nowdt - rules.parse_dt(t["reported_on"])).days
    unfinished = [o for o in all_jobs if fin[o["id"]]["stage"] != "closed"]
    subs = db.q("SELECT * FROM subsidies WHERE state NOT IN ('disbursed','rejected')")
    profit_won = sum(fin[o["id"]]["profit"] for o in won)
    # last 6 months for the chart
    months = []
    first = date.today().replace(day=1)
    for i in range(5, -1, -1):
        y, m = divmod(first.month - 1 - i, 12)
        ms = date(first.year + y, m + 1, 1)
        me = (date(ms.year + (ms.month // 12), ms.month % 12 + 1, 1) - timedelta(days=1))
        a, b = ms.isoformat() + " 00:00:00", me.isoformat() + " 23:59:59"
        months.append({"label": ms.strftime("%b"),
                       "sales": db.val("SELECT COALESCE(SUM(amount_untaxed),0) FROM orders WHERE state='sale' AND confirmed_at BETWEEN ? AND ?", a, b),
                       "installs": db.val("SELECT COUNT(*) FROM jobs WHERE site_end BETWEEN ? AND ?", a, b)})
    return {
        "period": period, "period_label": "%s → %s" % (start.strftime("%d %b"), end.strftime("%d %b %Y")), "currency": "₹",
        "kpi": {
            "leads_new": db.val("SELECT COUNT(*) FROM leads WHERE created_at BETWEEN ? AND ?", ds, de),
            "orders_won": len(won), "orders_value": sum(o["amount_untaxed"] for o in won),
            "kw_sold": sum(o["kw"] or 0 for o in won),
            "invoiced": db.val("SELECT COALESCE(SUM(amount_untaxed),0) FROM invoices WHERE state != 'cancel' AND date BETWEEN ? AND ?",
                               start.isoformat(), end.isoformat()),
            "collected": db.val("SELECT COALESCE(SUM(amount),0) FROM payments WHERE state = 'done' AND date BETWEEN ? AND ?", ds, de),
            "profit": profit_won, "loss_jobs": sum(1 for o in won if fin[o["id"]]["profit"] < 0),
            "installs_done": db.val("SELECT COUNT(*) FROM jobs WHERE site_end BETWEEN ? AND ?", ds, de),
            "installs_pending": db.val("SELECT COUNT(*) FROM jobs WHERE state != 'done'"),
            "unfinished_jobs": len(unfinished),
            "receivable": db.val("SELECT COALESCE(SUM(amount_total - amount_paid),0) FROM invoices WHERE state = 'posted'"),
            "tickets_open": len(open_tickets),
            "tickets_new": db.val("SELECT COUNT(*) FROM tickets WHERE reported_on BETWEEN ? AND ?", ds, de),
            "tickets_overdue": sum(1 for t in open_tickets if t["days"] > 3),
            "subsidy_pending": len(subs), "subsidy_amount": sum(s["amount_expected"] for s in subs),
            "stock_value": db.val("SELECT COALESCE(SUM(qty_on_hand * cost),0) FROM products WHERE is_kit = 0 AND is_service = 0"),
        },
        "jobs": jobs, "months": months,
        "tickets": [{"id": t["id"], "name": t["ref"], "customer": t["customer"], "product": t["product"] or "",
                     "stage": rules.label(rules.TICKET_STAGES, t["stage"]), "warranty": bool(t["warranty_id"]),
                     "days": t["days"]} for t in open_tickets[:15]],
        "unfinished": [{"id": o["id"], "name": o["ref"], "customer": db.val("SELECT name FROM customers WHERE id = ?", o["customer_id"]),
                        "pending": ", ".join(fin[o["id"]]["pending"])} for o in unfinished[:15]],
    }


@router.get("/dashboard")
def dashboard(period: str = "month", user=Depends(director_only), db=Depends(get_db)):
    return dashboard_data(db, period if period in ("today", "week", "month", "year") else "month")


@router.get("/summary")
def summary(user=Depends(staff_only), db=Depends(get_db)):
    """What needs attention, per role (the Overview page for non-directors)."""
    uid, role = user["id"], user["role"]
    items = []

    def add(label, count, path, tone=""):
        items.append({"label": label, "count": count or 0, "path": path, "tone": tone})

    if role in ("sales", "director"):
        add("New enquiries to call", db.val("SELECT COUNT(*) FROM leads WHERE stage = 'new'"), "/app/enquiries?stage=new", "warn")
        add("Surveys to approve", db.val("SELECT COUNT(*) FROM surveys WHERE state = 'done'"), "/app/surveys?state=done", "warn")
        add("Draft quotes to send", db.val("SELECT COUNT(*) FROM orders WHERE state = 'draft'"), "/app/orders?state=draft")
        add("Quotes awaiting customer", db.val("SELECT COUNT(*) FROM orders WHERE state = 'sent'"), "/app/orders?state=sent")
    if role in ("warehouse", "director"):
        add("Ready to dispatch", db.val("SELECT COUNT(*) FROM deliveries WHERE state = 'ready'"), "/app/dispatch?state=ready", "warn")
        add("Waiting for advance", db.val("SELECT COUNT(*) FROM deliveries WHERE state = 'waiting'"), "/app/dispatch?state=waiting")
        add("Items below minimum stock", db.val("SELECT COUNT(*) FROM products WHERE is_kit = 0 AND is_service = 0 AND qty_on_hand < min_qty"),
            "/app/stock", "bad")
    if role == "technician":
        add("My jobs to do", db.val("SELECT COUNT(*) FROM jobs j JOIN job_techs jt ON jt.job_id = j.id WHERE jt.user_id = ? AND j.state != 'done'", uid),
            "/app/jobs", "warn")
        add("My surveys to visit", db.val("SELECT COUNT(*) FROM surveys WHERE technician_id = ? AND state = 'scheduled'", uid), "/app/surveys")
        add("My open repairs", db.val("SELECT COUNT(*) FROM tickets WHERE technician_id = ? AND stage NOT IN ('closed','cancel')", uid), "/app/service")
    if role in ("support", "director"):
        add("New service requests", db.val("SELECT COUNT(*) FROM tickets WHERE stage = 'new'"), "/app/service?stage=new", "warn")
        add("Repairs in progress", db.val("SELECT COUNT(*) FROM tickets WHERE stage IN ('diagnosed','repair')"), "/app/service?stage=repair")
        add("Waiting for customer", db.val("SELECT COUNT(*) FROM tickets WHERE stage = 'awaiting'"), "/app/service?stage=awaiting")
    recent = db.q("SELECT n.model, n.res_id, n.body, n.created_at, u.name AS author FROM notes n LEFT JOIN users u ON u.id = n.author_id "
                  "ORDER BY n.id DESC LIMIT 40")
    allowed = {"lead": "leads", "survey": "surveys", "order": "orders", "delivery": "deliveries", "job": "jobs",
               "ticket": "tickets", "subsidy": "subsidies"}
    from ..access import level
    activity = []
    for n in recent:
        lvl = level(user, allowed.get(n["model"], ""))
        if lvl in ("rw", "r"):
            activity.append(n)
    return {"items": items, "activity": activity[:12]}


# ----------------------------------------------------------------- reports
@router.get("/reports/technicians")
def report_technicians(period: str = "month", user=Depends(director_only), db=Depends(get_db)):
    start, end, _ds, _de = _range(period)
    rows = db.q("SELECT u.id, u.name, u.hourly_rate, COUNT(DISTINCT t.job_id) AS jobs, COALESCE(SUM(t.hours),0) AS hours, "
                "COALESCE(SUM(t.hours * t.rate),0) AS pay FROM users u LEFT JOIN timesheets t ON t.user_id = u.id "
                "AND t.date BETWEEN ? AND ? WHERE u.role = 'technician' GROUP BY u.id ORDER BY pay DESC, u.name",
                start.isoformat(), end.isoformat())
    return {"rows": rows, "period_label": "%s → %s" % (start.strftime("%d %b"), end.strftime("%d %b %Y"))}


@router.get("/reports/invoices")
def report_invoices(status: str = "", user=Depends(director_only), db=Depends(get_db)):
    sql = ("SELECT i.*, c.name AS customer, o.ref AS order_ref FROM invoices i JOIN customers c ON c.id = i.customer_id "
           "LEFT JOIN orders o ON o.id = i.order_id")
    args = []
    if status == "unpaid":
        sql += " WHERE i.state = 'posted'"
    elif status == "paid":
        sql += " WHERE i.state = 'paid'"
    return {"rows": db.q(sql + " ORDER BY i.id DESC LIMIT 500", *args)}


@router.post("/reports/share")
def share_report(body: dict = Body(default={}), user=Depends(director_only), db=Depends(get_db)):
    email = (body.get("email") or "").strip()
    period = body.get("period") or "month"
    if "@" not in email:
        raise HTTPException(400, "Enter an email address.")
    d = dashboard_data(db, period)
    k = d["kpi"]
    html = mailer.branded(db, "SunPower performance report (%s)" % d["period_label"], [
        "Orders won: %s (%g kW), worth %s." % (k["orders_won"], k["kw_sold"], rules.money(k["orders_value"])),
        "Job profit: %s · Collected: %s · Receivable: %s." % (rules.money(k["profit"]), rules.money(k["collected"]),
                                                             rules.money(k["receivable"])),
        "Installations done: %s · Pending: %s · Open repairs: %s." % (k["installs_done"], k["installs_pending"], k["tickets_open"])],
        "Open the full report", "%s/print/report?period=%s" % (rules.frontend(db), period))
    mailer.queue(db, email, "SunPower performance report (%s)" % d["period_label"], html)
    return {"ok": True}


# ---------------------------------------------------------------- settings
PUBLIC_SETTINGS = ("company_name", "company_phone", "company_email", "company_address", "company_gstin", "frontend_url",
                   "advance_pct", "quote_valid_days", "labour_rate", "quote_note", "smtp_enabled", "smtp_host", "smtp_port",
                   "smtp_user", "smtp_from", "google_client_id", "razorpay_key_id", "test_payments", "ai_url")
SECRET_SETTINGS = ("smtp_password", "google_client_secret", "razorpay_key_secret")


@router.get("/settings")
def get_settings(user=Depends(director_only), db=Depends(get_db)):
    out = {k: db.setting(k) or "" for k in PUBLIC_SETTINGS}
    out.update({k + "_set": bool(db.setting(k)) for k in SECRET_SETTINGS})
    out["mail"] = {s["state"]: s["n"] for s in db.q("SELECT state, COUNT(*) AS n FROM mail_queue GROUP BY state")}
    out["smtp_last_error"] = db.setting("smtp_last_error") or ""
    out["google_redirect_uri"] = rules.frontend(db) + "/api/auth/google/callback"
    return out


@router.put("/settings")
def put_settings(body: dict = Body(default={}), user=Depends(director_only), db=Depends(get_db)):
    for k in PUBLIC_SETTINGS:
        if k in body:
            db.set_setting(k, (str(body[k]).strip() if body[k] is not None else ""))
    for k in SECRET_SETTINGS:  # only replaced when a new value is typed
        if body.get(k):
            db.set_setting(k, str(body[k]).strip())
    try:
        pct = float(db.setting("advance_pct") or 0)
        assert 0 <= pct <= 100
    except (ValueError, AssertionError):
        raise HTTPException(400, "The advance must be between 0 and 100%.")
    for o in db.q("SELECT id FROM orders WHERE state = 'sale'"):
        rules.refresh_delivery_state(db, o["id"])
    return {"ok": True}


@router.post("/settings/send-mail")
def send_mail_now(user=Depends(director_only)):
    sent, failed = mailer.send_pending()
    return {"ok": True, "sent": sent, "failed": failed}


@router.patch("/products/{pid}")
def update_product(pid: int, body: dict = Body(default={}), user=Depends(director_only), db=Depends(get_db)):
    found(db.get("products", pid), "Product not found.")
    vals = {}
    for k in ("price", "cost", "warranty_months", "min_qty", "tax_rate"):
        if k in body:
            try:
                vals[k] = max(float(body[k]), 0)
            except (TypeError, ValueError):
                raise HTTPException(400, "%s must be a number." % k)
    if "name" in body and body["name"].strip():
        vals["name"] = body["name"].strip()[:120]
    db.update("products", pid, vals)
    return {"ok": True}


@router.get("/kits/{pid}")
def kit(pid: int, user=Depends(staff_only), db=Depends(get_db)):
    need(user, "stock")
    return {"lines": db.q("SELECT kl.qty, p.code, p.name, p.tracking FROM kit_lines kl JOIN products p ON p.id = kl.product_id "
                          "WHERE kl.kit_id = ?", pid)}


# ------------------------------------------------------------------- users
@router.get("/users")
def users(user=Depends(director_only), db=Depends(get_db)):
    return {"rows": db.q("SELECT id, name, email, phone, role, hourly_rate, active, last_login, "
                         "password_hash IS NOT NULL AS has_password FROM users WHERE role != 'customer' ORDER BY active DESC, role, name"),
            "roles": [r for r in ROLES if r != "customer"]}


@router.post("/users")
def create_user(body: dict = Body(default={}), user=Depends(director_only), db=Depends(get_db)):
    name, email, role = (body.get("name") or "").strip(), (body.get("email") or "").strip().lower(), body.get("role")
    if not name or "@" not in email or role not in STAFF:
        raise HTTPException(400, "Enter a name, an email and a role.")
    if db.one("SELECT id FROM users WHERE email = ? COLLATE NOCASE", email):
        raise HTTPException(400, "Someone already uses this email.")
    uid = db.insert("users", {"name": name[:120], "email": email, "phone": (body.get("phone") or "").strip() or None,
                              "role": role, "hourly_rate": float(body.get("hourly_rate") or 0), "created_at": now()})
    link = rules.send_account_email(db, uid, "staff", make_token(db, uid, "staff"))
    return {"ok": True, "id": uid, "link": link}


@router.patch("/users/{uid}")
def update_user(uid: int, body: dict = Body(default={}), user=Depends(director_only), db=Depends(get_db)):
    target = found(db.get("users", uid), "User not found.")
    if target["role"] == "customer":
        raise HTTPException(400, "Customers are managed from their account.")
    vals = {}
    if "name" in body:
        if not (body.get("name") or "").strip():
            raise HTTPException(400, "The name can't be empty.")
        vals["name"] = body["name"].strip()[:120]
    if "phone" in body:
        vals["phone"] = (body.get("phone") or "").strip()[:40] or None
    if "email" in body:
        email = (body.get("email") or "").strip().lower()
        if "@" not in email:
            raise HTTPException(400, "Enter a valid email.")
        if db.val("SELECT id FROM users WHERE email = ? COLLATE NOCASE AND id != ?", email, uid):
            raise HTTPException(400, "Someone already uses this email.")
        vals["email"] = email
    if "role" in body:
        if body["role"] not in STAFF:
            raise HTTPException(400, "Unknown role.")
        vals["role"] = body["role"]
    if "active" in body:
        vals["active"] = 1 if body["active"] else 0
    if "hourly_rate" in body:
        vals["hourly_rate"] = max(float(body["hourly_rate"] or 0), 0)
    if uid == user["id"] and (vals.get("active") == 0 or vals.get("role", "director") != "director"):
        raise HTTPException(400, "You can't remove your own Director access.")
    db.update("users", uid, vals)
    if vals.get("active") == 0:
        db.exec("DELETE FROM sessions WHERE user_id = ?", uid)
    return {"ok": True}


# ------------------------------------------------------------------- today
def _utc_day_bounds(day):
    """Local calendar day -> UTC bounds (event times are stored in UTC)."""
    from datetime import timezone
    a = datetime.combine(day, time.min).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    b = datetime.combine(day, time.max).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return a, b


def _item(title, sub, path, tag="", when=None, tone=""):
    return {"title": title, "sub": sub, "path": path, "tag": tag, "when": when, "tone": tone}


@router.get("/today")
def today_view(user=Depends(staff_only), db=Depends(get_db)):
    """Today's work for the signed-in person: a few numbers and at most five groups of
    things to do, most urgent first. History and trends live in Insights."""
    uid, role = user["id"], user["role"]
    day = date.today()
    us, ue = _utc_day_bounds(day)
    ls, le = day.isoformat() + " 00:00:00", day.isoformat() + " 23:59:59"   # local (appointments)
    nowdt = rules.parse_dt(now())

    def new_leads(mine=False):
        rows = db.q("SELECT * FROM leads WHERE stage = 'new'" + (" AND salesperson_id = ?" if mine else "") +
                    " ORDER BY created_at", *([uid] if mine else []))
        return [_item(l["contact_name"], "%s · %s kW · %s" % (l["ref"], l["requested_kw"] or "?", l["city"] or "no city"),
                      "/app/enquiries/%s" % l["id"], "Call", l["created_at"], "warn") for l in rows]

    def surveys_to_approve():
        rows = db.q("SELECT s.*, l.contact_name FROM surveys s JOIN leads l ON l.id = s.lead_id WHERE s.state = 'done' ORDER BY s.id")
        return [_item(s["contact_name"], "%s · %s kW recommended" % (s["ref"], s["recommended_kw"] or "?"),
                      "/app/surveys/%s" % s["id"], "Approve") for s in rows]

    def quotes_to_move():
        out = []
        for o in db.q("SELECT o.*, c.name AS customer FROM orders o JOIN customers c ON c.id = o.customer_id "
                      "WHERE o.state IN ('draft','sent') ORDER BY o.date_order"):
            if o["state"] == "draft":
                out.append(_item(o["customer"], "%s · %g kW · %s" % (o["ref"], o["kw"], rules.money(o["amount_total"])),
                                 "/app/orders/%s" % o["id"], "Send quote"))
            elif (nowdt - rules.parse_dt(o["date_order"])).days >= 3:
                out.append(_item(o["customer"], "%s · sent %s days ago" % (o["ref"], (nowdt - rules.parse_dt(o["date_order"])).days),
                                 "/app/orders/%s" % o["id"], "Follow up"))
        return out

    def money_to_collect():
        out = []
        for o in db.q("SELECT o.*, c.name AS customer FROM orders o JOIN customers c ON c.id = o.customer_id "
                      "WHERE o.state = 'sale' ORDER BY o.confirmed_at"):
            due = rules.advance_due(db, o)
            if due > 0:
                out.append(_item(o["customer"], "%s · advance %s due" % (o["ref"], rules.money(due)),
                                 "/app/orders/%s" % o["id"], "Advance", tone="bad"))
        for i in db.q("SELECT i.*, c.name AS customer FROM invoices i JOIN customers c ON c.id = i.customer_id "
                      "WHERE i.state = 'posted' AND i.amount_total - i.amount_paid > 0.5 ORDER BY i.date"):
            out.append(_item(i["customer"], "%s · %s unpaid" % (i["ref"], rules.money(i["amount_total"] - i["amount_paid"])),
                             "/app/orders/%s" % i["order_id"] if i["order_id"] else "/app/reports", "Invoice"))
        return out

    def deliveries(state):
        rows = db.q("SELECT d.*, o.ref AS order_ref, o.kw, c.name AS customer FROM deliveries d JOIN orders o ON o.id = d.order_id "
                    "JOIN customers c ON c.id = o.customer_id WHERE d.state = ? ORDER BY d.id", state)
        return [_item(d["customer"], "%s · %g kW kit · order %s" % (d["ref"], d["kw"], d["order_ref"]), "/app/dispatch/%s" % d["id"],
                      "Dispatch" if state == "ready" else "Advance due") for d in rows]

    def low_stock():
        rows = db.q("SELECT * FROM products WHERE is_kit = 0 AND is_service = 0 AND qty_on_hand < min_qty ORDER BY qty_on_hand")
        return [_item(p["name"], "%g in stock · minimum %g" % (p["qty_on_hand"], p["min_qty"]), "/app/stock", "Reorder", tone="bad")
                for p in rows]

    def jobs(mine=False, only_today=False):
        sql = ("SELECT j.*, c.name AS customer, c.city FROM jobs j JOIN customers c ON c.id = j.customer_id WHERE j.state != 'done'")
        args = []
        if mine:
            sql += " AND j.id IN (SELECT job_id FROM job_techs WHERE user_id = ?)"
            args.append(uid)
        if only_today:
            sql += " AND j.scheduled_at BETWEEN ? AND ?"
            args += [ls, le]
        rows = db.q(sql + " ORDER BY CASE j.state WHEN 'in_progress' THEN 0 ELSE 1 END, j.scheduled_at", *args)
        return [_item(j["customer"], "%s · %g kW · %s" % (j["ref"], j["kw_planned"] or 0, j["city"] or ""), "/app/jobs/%s" % j["id"],
                      "On site" if j["state"] == "in_progress" else ("Today" if ls <= (j["scheduled_at"] or "") <= le else "Upcoming"),
                      j["scheduled_at"], "warn" if j["state"] == "in_progress" else "") for j in rows]

    def visits(mine=False, only_today=False):
        sql = ("SELECT s.*, l.contact_name, l.city FROM surveys s JOIN leads l ON l.id = s.lead_id WHERE s.state = 'scheduled'")
        args = []
        if mine:
            sql += " AND s.technician_id = ?"
            args.append(uid)
        if only_today:
            sql += " AND s.survey_date BETWEEN ? AND ?"
            args += [ls, le]
        rows = db.q(sql + " ORDER BY s.survey_date", *args)
        return [_item(s["contact_name"], "%s · roof survey · %s" % (s["ref"], s["city"] or ""), "/app/surveys/%s" % s["id"],
                      "Today" if ls <= (s["survey_date"] or "") <= le else "Visit", s["survey_date"]) for s in rows]

    def tickets(where, mine=False, tag=""):
        sql = ("SELECT t.*, c.name AS customer FROM tickets t JOIN customers c ON c.id = t.customer_id WHERE " + where)
        args = []
        if mine:
            sql += " AND t.technician_id = ?"
            args.append(uid)
        rows = db.q(sql + " ORDER BY t.priority DESC, t.reported_on", *args)
        out = []
        for t in rows:
            days = (nowdt - rules.parse_dt(t["reported_on"])).days
            out.append(_item(t["customer"], "%s · %s" % (t["ref"], (t["description"] or "")[:70]), "/app/service/%s" % t["id"],
                             tag or ("Urgent" if t["priority"] == "2" else "%sd open" % days), t["reported_on"],
                             "bad" if days > 3 or t["priority"] == "2" else ""))
        return out

    def count(sql, *args):
        return db.val(sql, *args) or 0

    groups, stats = [], []

    def group(key, title, hint, items, path):
        groups.append({"key": key, "title": title, "hint": hint, "count": len(items), "items": items[:6], "path": path})

    if role == "director":
        stats = [
            {"label": "New enquiries", "value": count("SELECT COUNT(*) FROM leads WHERE created_at BETWEEN ? AND ?", us, ue)},
            {"label": "Collected today", "value": rules.money(count("SELECT COALESCE(SUM(amount),0) FROM payments WHERE state = 'done' AND date BETWEEN ? AND ?", us, ue))},
            {"label": "Installs today", "value": count("SELECT COUNT(*) FROM jobs WHERE state != 'done' AND scheduled_at BETWEEN ? AND ?", ls, le)},
            {"label": "Open repairs", "value": count("SELECT COUNT(*) FROM tickets WHERE stage NOT IN ('closed','cancel')")},
        ]
        group("sales", "Sales to move forward", "New enquiries to call, surveys to approve, quotes to send or chase.",
              new_leads() + surveys_to_approve() + quotes_to_move(), "/app/enquiries")
        group("money", "Money to collect", "Advances still due and unpaid invoices.", money_to_collect(), "/app/orders?state=sale")
        group("site", "On site today", "Installations and roof surveys booked for today.",
              jobs(only_today=True) + visits(only_today=True), "/app/jobs")
        group("warehouse", "Warehouse", "Kits ready to dispatch and items to reorder.", deliveries("ready") + low_stock(), "/app/dispatch")
        group("service", "Service", "New and overdue repair requests.",
              tickets("t.stage = 'new'") + [t for t in tickets("t.stage IN ('diagnosed','repair')") if t["tone"] == "bad"], "/app/service")
    elif role == "sales":
        stats = [
            {"label": "New enquiries today", "value": count("SELECT COUNT(*) FROM leads WHERE created_at BETWEEN ? AND ?", us, ue)},
            {"label": "Quotes with customers", "value": count("SELECT COUNT(*) FROM orders WHERE state = 'sent'")},
            {"label": "Orders confirmed today", "value": count("SELECT COUNT(*) FROM orders WHERE state = 'sale' AND confirmed_at BETWEEN ? AND ?", us, ue)},
        ]
        group("call", "Call new enquiries", "Call within two hours: screen the roof, bill and grid.", new_leads(), "/app/enquiries?stage=new")
        group("approve", "Surveys to approve", "Visited by a technician; check the size and approve.", surveys_to_approve(), "/app/surveys?state=done")
        group("quotes", "Quotes to send or chase", "Drafts to send, and quotes sent 3+ days ago.", quotes_to_move(), "/app/orders?state=quotes")
        group("money", "Money to collect", "Advances still due and unpaid invoices.", money_to_collect(), "/app/orders?state=sale")
    elif role == "warehouse":
        stats = [
            {"label": "Ready to dispatch", "value": count("SELECT COUNT(*) FROM deliveries WHERE state = 'ready'")},
            {"label": "Dispatched today", "value": count("SELECT COUNT(*) FROM deliveries WHERE state = 'done' AND date_done BETWEEN ? AND ?", us, ue)},
            {"label": "Items to reorder", "value": count("SELECT COUNT(*) FROM products WHERE is_kit = 0 AND is_service = 0 AND qty_on_hand < min_qty")},
        ]
        group("ready", "Ready to dispatch", "Advance paid: pack, scan serials and send.", deliveries("ready"), "/app/dispatch?state=ready")
        group("waiting", "Waiting for the advance", "Can't leave until the customer pays.", deliveries("waiting"), "/app/dispatch?state=waiting")
        group("stock", "Items to reorder", "Below the minimum stock level.", low_stock(), "/app/stock")
    elif role == "technician":
        mine_jobs = jobs(mine=True)
        stats = [
            {"label": "My jobs today", "value": sum(1 for j in mine_jobs if j["tag"] in ("Today", "On site"))},
            {"label": "My visits today", "value": len(visits(mine=True, only_today=True))},
            {"label": "My open repairs", "value": count("SELECT COUNT(*) FROM tickets WHERE technician_id = ? AND stage NOT IN ('closed','cancel')", uid)},
        ]
        group("jobs", "My installations", "Start on site, then checklist, photos and the customer's signature.", mine_jobs, "/app/jobs")
        group("visits", "My roof surveys", "Measure the roof and mark the visit done.", visits(mine=True), "/app/surveys")
        group("repairs", "My repairs", "Fix, add parts and hours, then ask the customer to confirm.",
              tickets("t.stage NOT IN ('closed','cancel','awaiting')", mine=True), "/app/service")
    elif role == "support":
        stats = [
            {"label": "New today", "value": count("SELECT COUNT(*) FROM tickets WHERE reported_on BETWEEN ? AND ?", us, ue)},
            {"label": "Open requests", "value": count("SELECT COUNT(*) FROM tickets WHERE stage NOT IN ('closed','cancel')")},
            {"label": "Open over 3 days", "value": sum(1 for t in tickets("t.stage NOT IN ('closed','cancel')") if t["tone"] == "bad")},
        ]
        group("new", "New requests", "Find the equipment, assign a technician, diagnose.", tickets("t.stage = 'new'"), "/app/service?stage=new")
        group("repair", "Being repaired", "Diagnosed or with a technician.", tickets("t.stage IN ('diagnosed','repair')"), "/app/service?stage=repair")
        group("awaiting", "Waiting for the customer", "Repair done; the customer has to confirm.", tickets("t.stage = 'awaiting'", tag="Confirm"),
              "/app/service?stage=awaiting")
    return {"date": day.isoformat(), "stats": stats, "groups": groups,
            "all_clear": not any(g["count"] for g in groups)}


# ------------------------------------------------------------- money fixes
@router.post("/payments/{pid}/void")
def void_payment(pid: int, body: dict = Body(default={}), user=Depends(director_only), db=Depends(get_db)):
    """Undo a payment recorded by mistake (Director). The record stays, marked void."""
    p = found(db.get("payments", pid), "Payment not found.")
    if p["state"] != "done":
        raise HTTPException(400, "Only received payments can be voided.")
    db.update("payments", pid, {"state": "void"})
    if p["order_id"]:
        rules.allocate_payments(db, p["order_id"])
        rules.refresh_delivery_state(db, p["order_id"])
        db.note("order", p["order_id"], "Payment %s of %s voided: %s" % (
            p["ref"], rules.money(p["amount"]), (body.get("reason") or "no reason given")[:200]), user["id"])
    return {"ok": True}


@router.post("/invoices/{iid}/cancel")
def cancel_invoice(iid: int, body: dict = Body(default={}), user=Depends(director_only), db=Depends(get_db)):
    """Cancel an invoice that hasn't been paid yet (Director)."""
    inv = found(db.get("invoices", iid), "Invoice not found.")
    if inv["state"] == "cancel":
        raise HTTPException(400, "This invoice is already cancelled.")
    if inv["amount_paid"] > 0.5:
        raise HTTPException(400, "Money has been received on this invoice. Void the payment first.")
    db.update("invoices", iid, {"state": "cancel"})
    if inv["ticket_id"]:
        db.exec("UPDATE tickets SET invoice_id = NULL WHERE id = ?", inv["ticket_id"])
    if inv["order_id"]:
        rules.allocate_payments(db, inv["order_id"])
        db.note("order", inv["order_id"], "Invoice %s cancelled: %s" % (inv["ref"], (body.get("reason") or "no reason given")[:200]),
                user["id"])
    return {"ok": True}
