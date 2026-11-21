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
