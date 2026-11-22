"""One-shot realistic demo data so every role has something to work on.

Everything goes through the real business rules (rules.py), then dates are
moved into the past so the dashboard has three months of history.

Demo logins (password for all: Sunpower@2026, recovery code 2580):
  director@sunpower.demo   Director (everything)
  sales@sunpower.demo      Sales
  warehouse@sunpower.demo  Warehouse
  support@sunpower.demo    Service desk
  tech01@sunpower.demo …   Technicians (15)
  customer@sunpower.demo   A customer with an installed system
"""
import base64
import random
from datetime import date, datetime, timedelta, timezone

from . import rules
from .catalog import TECH_RATES
from .db import now
from .security import hash_password

DEMO_PASSWORD = "Sunpower@2026"   # meets the password rules
DEMO_CODE = "2580"               # 4-digit recovery code for every demo account

FIRST = ["Aarav", "Vihaan", "Ananya", "Diya", "Rohan", "Kavya", "Arjun", "Isha", "Kabir", "Meera", "Rahul",
         "Sneha", "Vikram", "Pooja", "Aditya", "Neha", "Karan", "Riya", "Siddharth", "Tanvi", "Manish", "Priya",
         "Harsh", "Nisha", "Yash", "Anjali"]
LAST = ["Patel", "Shah", "Mehta", "Sharma", "Desai", "Joshi", "Trivedi", "Iyer", "Reddy", "Nair", "Gupta",
        "Verma", "Chauhan", "Parmar", "Rana", "Bhatt"]
# Demo customers across India: (locality, city, state, electricity board)
PLACES = [("Satellite", "Ahmedabad", "Gujarat", "Torrent Power"), ("Kothrud", "Pune", "Maharashtra", "MSEDCL"),
          ("Malviya Nagar", "Jaipur", "Rajasthan", "JVVNL"), ("Gomti Nagar", "Lucknow", "Uttar Pradesh", "MVVNL"),
          ("Whitefield", "Bengaluru", "Karnataka", "BESCOM"), ("Velachery", "Chennai", "Tamil Nadu", "TANGEDCO"),
          ("Kondapur", "Hyderabad", "Telangana", "TSSPDCL"), ("Kakkanad", "Kochi", "Kerala", "KSEB"),
          ("Vijay Nagar", "Indore", "Madhya Pradesh", "MPPKVVCL"), ("Beltola", "Guwahati", "Assam", "APDCL"),
          ("Sector 35", "Chandigarh", "Chandigarh", "CED"), ("Patia", "Bhubaneswar", "Odisha", "TPCODL"),
          ("Rohini", "Delhi", "Delhi", "TPDDL"), ("Salt Lake", "Kolkata", "West Bengal", "CESC")]
TECHS = ["Ramesh Solanki", "Suresh Makwana", "Mahesh Vaghela", "Dinesh Rathod", "Jignesh Prajapati",
         "Bharat Thakor", "Kalpesh Parmar", "Hitesh Gohil", "Nilesh Chavda", "Paresh Barot", "Vipul Dabhi",
         "Hardik Zala", "Mukesh Bariya", "Sanjay Koli", "Ajay Damor"]
FAULTS = [
    ("E-07", "Inverter showing fault code E-07, zero power since the rain started"),
    ("F-24", "Isolation fault on inverter display, tripping every morning"),
    ("", "Battery backup lasting only 30 minutes in the evening"),
    ("W-11", "Grid overvoltage warning, generation drops at noon"),
    ("", "Panel glass cracked after the hailstorm last week"),
    ("E-33", "Inverter fan noise and over-temperature alarm in the afternoon"),
]
# 1x1 transparent PNG: stands in for roof photos and signatures in the demo
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
SIGNATURE = "data:image/png;base64," + base64.b64encode(PNG).decode()


def _ts(dt):
    """Appointment times (installation slots, survey visits) are stored as local time."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _uts(dt):
    """Event times (created, paid, dispatched, on site) are stored in UTC, like db.now()."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _user(db, name, email, role, rate=0, customer_id=None):
    return db.insert("users", {"name": name, "email": email, "role": role, "hourly_rate": rate,
                               "customer_id": customer_id, "password_hash": hash_password(DEMO_PASSWORD),
                               "recovery_code_hash": hash_password(DEMO_CODE),
                               "created_at": now()})


def _receive_stock(db, actor_id):
    for p in db.q("SELECT * FROM products WHERE is_kit = 0 AND is_service = 0"):
        if p["tracking"] == "serial":
            count = 220 if p["code"] == "BAT-150" else 60
            prefix = p["code"].replace("-", "")
            rules.receive_stock(db, p, 0, ["%s-26%04d" % (prefix, n) for n in range(1, count + 1)], actor_id,
                                "Opening stock")
        else:
            qty = 1200 if p["tracking"] == "lot" else (3000 if "(m)" in p["name"] else 300)
            rules.receive_stock(db, p, qty, [], actor_id, "Opening stock")


def _dispatch(db, order_id, actor):
    d = db.one("SELECT * FROM deliveries WHERE order_id = ? AND state != 'done'", order_id)
    serials = {}
    for line in db.q("SELECT dl.*, p.tracking FROM delivery_lines dl JOIN products p ON p.id = dl.product_id "
                     "WHERE dl.delivery_id = ?", d["id"]):
        if line["tracking"] == "serial":
            serials[str(line["id"])] = [r["name"] for r in db.q(
                "SELECT name FROM serials WHERE product_id = ? AND state = 'in_stock' ORDER BY id LIMIT ?",
                line["product_id"], int(line["qty"]))]
        elif line["tracking"] == "lot":
            serials[str(line["id"])] = ["PNL-2026-%s" % "ABC"[order_id % 3]]
    rules.validate_delivery(db, d, serials, actor)
    return d["id"]


def load_demo(db):
    rnd = random.Random(42)
    db.set_setting("test_payments", "1")      # demo only: lets the test card complete payments
    director = db.get("users", _user(db, "Asha Mehta", "director@sunpower.demo", "director"))
    sales = [_user(db, "Neel Shah", "sales@sunpower.demo", "sales"),
             _user(db, "Kriti Desai", "sales2@sunpower.demo", "sales")]
    warehouse = db.get("users", _user(db, "Vijay Rathod", "warehouse@sunpower.demo", "warehouse"))
    support = _user(db, "Farah Khan", "support@sunpower.demo", "support")
    techs = [_user(db, name, "tech%02d@sunpower.demo" % (i + 1), "technician", TECH_RATES[i % len(TECH_RATES)])
             for i, name in enumerate(TECHS)]
    for i, tid in enumerate(techs):   # each technician covers one city (and its state)
        place = PLACES[i % len(PLACES)]
        db.update("users", tid, {"service_area": "%s, %s" % (place[1], place[2])})
    _receive_stock(db, warehouse["id"])

    today = datetime.now().replace(minute=0, second=0, microsecond=0)
    plans = [{"days_ago": 800, "kw": 3, "type": "on_grid", "pay": "paid", "stage": "installed"},
             {"days_ago": 545, "kw": 5, "type": "off_grid", "pay": "paid", "stage": "installed"}]
    for i in range(38):
        days = rnd.randint(0, 85)
        plans.append({"days_ago": days, "kw": rnd.choice([1, 2, 3, 3, 3, 4, 5]),
                      "type": "off_grid" if rnd.random() < .3 else "on_grid",
                      "pay": "paid" if days > 20 else rnd.choice(["advance", "advance", "paid", "invoiced"]),
                      "loss": i in (4, 11, 23),
                      "stage": "installed" if days > 10 else rnd.choice(["installed", "dispatched", "confirmed"])})

    installed_orders, open_jobs = [], []
    for i, plan in enumerate(plans):
        when = today - timedelta(days=plan["days_ago"], hours=rnd.randint(0, 6))
        name = "%s %s" % (rnd.choice(FIRST), rnd.choice(LAST))
        email = "%s.%d@example.com" % (name.lower().replace(" ", "."), i)
        phone = "+91 98%08d" % rnd.randint(0, 99999999)
        area, city, state, discom = rnd.choice(PLACES)
        street = "%d, %s" % (rnd.randint(1, 250), area)
        cid = rules.ensure_customer(db, name, email, phone, street, city)
        db.update("customers", cid, {"state": state})
        lid = rules.create_enquiry(db, {
            "contact_name": name, "phone": phone, "email": email, "street": street, "city": city, "state": state,
            "requested_kw": plan["kw"], "system_type": plan["type"], "subsidy_requested": plan["type"] == "on_grid",
            "monthly_bill": plan["kw"] * 1000 + rnd.randint(-200, 600), "roof_area_sqft": plan["kw"] * 110 + rnd.randint(0, 150),
            "discom": discom, "consumer_no": "%s%09d" % (discom[:2].upper(), rnd.randint(0, 10 ** 9)),
            "salesperson_id": rnd.choice(sales)}, channel=rnd.choice(["web", "web", "whatsapp", "call", "referral"]),
            customer_id=cid)
        db.update("leads", lid, {"grid_suitable": "yes"})
        tech = rnd.choice(techs)
        sid = rules.schedule_survey(db, db.get("leads", lid), tech, _ts(when - timedelta(days=5)), director["id"], allow_past=True)
        db.update("surveys", sid, {"roof_type": "rcc", "roof_direction": rnd.choice(["S", "S", "SE", "SW"]),
                                   "roof_tilt": rnd.choice([10, 15, 20]), "cable_distance_m": rnd.randint(8, 35),
                                   "recommended_kw": plan["kw"], "latitude": 23.0225, "longitude": 72.5714})
        rules.survey_mark_done(db, db.get("surveys", sid), tech)
        rules.survey_approve(db, db.get("surveys", sid), director)
        oid = rules.create_quote(db, db.get("leads", lid), director["id"])
        if plan.get("loss"):
            db.exec("UPDATE order_lines SET discount = 22 WHERE order_id = ?", oid)
            rules.recompute_order(db, oid)
        o = db.get("orders", oid)
        kwh = o["kw"] * rules.FALLBACK_KWH_PER_KW
        db.update("orders", oid, {"est_kwh_year": kwh, "est_savings_year": kwh * rules.AVG_TARIFF_INR,
                                  "est_payback_years": round(o["amount_total"] / (kwh * rules.AVG_TARIFF_INR), 1),
                                  "est_source": "Rule of thumb (1450 kWh/kW/yr)", "accepted_by": name})
        # advance (confirms the order), balance per plan
        rules.record_payment(db, db.get("orders", oid), rules.advance_needed(db, o), rnd.choice(["upi", "bank"]),
                             rnd.choice(sales), purpose="advance")
        if plan["pay"] == "invoiced" or (plan["pay"] == "paid" and plan["stage"] == "installed"):
            rules.final_invoice(db, db.get("orders", oid), director["id"])
        if plan["stage"] in ("dispatched", "installed"):
            _dispatch(db, oid, warehouse)
        job = db.one("SELECT * FROM jobs WHERE order_id = ?", oid)
        crew = rnd.sample(techs, rnd.randint(2, 3))
        if plan["stage"] != "installed" and len(open_jobs) < 4:
            crew = [techs[0]] + crew[:1]   # Ramesh (tech01) always has work in the demo
        for t in crew:
            db.exec("INSERT OR IGNORE INTO job_techs (job_id, user_id) VALUES (?, ?)", job["id"], t)
        if plan["stage"] == "installed":
            hours = rnd.uniform(14, 20) if plan.get("loss") else rnd.uniform(5, 8)
            db.update("jobs", job["id"], {
                "chk_stands": 1, "chk_panels": 1, "chk_wiring": 1, "chk_earthing": 1, "chk_generation": 1,
                "kw_confirmed": o["kw"], "generation_reading_kw": round(o["kw"] * rnd.uniform(.62, .81), 2),
                "signed_by": name, "signature": SIGNATURE,
                "site_start": _ts(datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours))})
            db.insert("attachments", {"owner_type": "job", "owner_id": job["id"], "filename": "roof.png",
                                      "mime": "image/png", "data": PNG, "created_at": now()})
            rules.job_finish(db, db.get("jobs", job["id"]), director, allow_early=True)
            if plan["pay"] == "paid":
                rest = db.get("orders", oid)["amount_total"] - rules.order_paid(db, oid)
                if rest > 0.5:
                    rules.record_payment(db, db.get("orders", oid), rest, "bank", rnd.choice(sales), purpose="balance")
            installed_orders.append(oid)
        else:
            open_jobs.append(job["id"])
        _backdate(db, oid, lid, sid, when, plan["stage"], rnd)

    _subsidies(db, today)
    _tickets(db, rnd, installed_orders, techs, director, support)
    _pipeline(db, rnd, techs, sales, director, today)
    # one customer login with an installed system
    cust_id = db.val("SELECT customer_id FROM orders WHERE id = ?", installed_orders[-1])
    db.update("customers", cust_id, {"email": "customer@sunpower.demo"})
    existing = db.one("SELECT id FROM users WHERE customer_id = ?", cust_id)
    if existing:
        db.update("users", existing["id"], {"email": "customer@sunpower.demo", "password_hash": hash_password(DEMO_PASSWORD),
                                            "recovery_code_hash": hash_password(DEMO_CODE)})
    else:
        _user(db, db.val("SELECT name FROM customers WHERE id = ?", cust_id), "customer@sunpower.demo", "customer",
              customer_id=cust_id)
    db.exec("DELETE FROM mail_queue")  # demo emails are not real


def _backdate(db, oid, lid, sid, when, stage, rnd):
    """Move one job's history to `when` so reports have three months of data."""
    w = _uts(when)
    db.update("leads", lid, {"created_at": _uts(when - timedelta(days=9)), "next_action": None, "next_action_due": None})
    db.update("surveys", sid, {"created_at": _uts(when - timedelta(days=8))})
    db.update("orders", oid, {"date_order": _uts(when - timedelta(days=2)), "confirmed_at": w, "created_at": w,
                              "valid_until": (when + timedelta(days=13)).date().isoformat()})
    db.exec("UPDATE payments SET date = ? WHERE order_id = ?", w, oid)
    db.exec("UPDATE invoices SET date = ? WHERE order_id = ?", when.date().isoformat(), oid)
    shipped = when + timedelta(days=2)
    for d in db.q("SELECT * FROM deliveries WHERE order_id = ? AND state = 'done'", oid):
        db.update("deliveries", d["id"], {"date_done": _uts(shipped)})
        db.exec("UPDATE stock_moves SET date = ? WHERE delivery_id = ?", _uts(shipped), d["id"])
    installed = (when + timedelta(days=3)).date()
    for wr in db.q("SELECT * FROM warranties WHERE order_id = ?", oid):   # warranties start on the installation day
        db.update("warranties", wr["id"], {"start_date": installed.isoformat(),
                                           "end_date": rules.add_months(installed, wr["months"]).isoformat()})
    job = db.one("SELECT * FROM jobs WHERE order_id = ?", oid)
    if stage == "installed":
        start = when + timedelta(days=3, hours=9)
        hours = (rules.parse_dt(job["site_end"]) - rules.parse_dt(job["site_start"])).total_seconds() / 3600
        end = start + timedelta(hours=hours)
        db.update("jobs", job["id"], {"scheduled_at": _ts(start), "site_start": _uts(start), "site_end": _uts(end),
                                      "signed_on": _uts(end)})
        db.exec("UPDATE timesheets SET date = ? WHERE job_id = ?", start.date().isoformat(), job["id"])
    else:
        upcoming = datetime.now().replace(minute=0, second=0, microsecond=0) + timedelta(days=rnd.randint(0, 6))
        db.update("jobs", job["id"], {"scheduled_at": _ts(upcoming.replace(hour=rnd.choice([9, 10, 11, 14])))})
    db.exec("UPDATE notes SET created_at = ? WHERE (model = 'order' AND res_id = ?) OR (model = 'lead' AND res_id = ?)",
            w, oid, lid)


def _subsidies(db, today):
    states = ["draft", "applied", "inspection", "approved", "disbursed"]
    for s in db.q("SELECT s.*, o.confirmed_at FROM subsidies s JOIN orders o ON o.id = s.order_id"):
        confirmed = rules.parse_dt(s["confirmed_at"])
        st = states[min((today - confirmed).days // 15, 4)]
        vals = {"state": st, "application_no": "PMSG-GJ-%06d" % s["id"], "doc_id_proof": 1, "doc_bill": 1,
                "doc_bank": int(st != "draft"), "doc_photo": int(st != "draft"),
                "doc_net_meter": int(st in ("approved", "disbursed"))}
        if st != "draft":
            vals["applied_on"] = (confirmed + timedelta(days=4)).date().isoformat()
        if st in ("inspection", "approved", "disbursed"):
            vals["inspection_on"] = (confirmed + timedelta(days=25)).date().isoformat()
        if st == "disbursed":
            vals.update(amount_received=s["amount_expected"], disbursed_on=(confirmed + timedelta(days=60)).date().isoformat())
        db.update("subsidies", s["id"], vals)


def _tickets(db, rnd, installed, techs, director, support):
    for n, (code, desc) in enumerate(FAULTS):
        oid = installed[n] if n < 2 else rnd.choice(installed)
        o = db.get("orders", oid)
        w = db.one("SELECT w.* FROM warranties w JOIN products p ON p.id = w.product_id WHERE w.order_id = ? "
                   "AND p.category = 'inverter'", oid) or db.one("SELECT * FROM warranties WHERE order_id = ?", oid)
        tech = techs[0] if n in (0, 3) else rnd.choice(techs)
        tid = rules.create_ticket(db, o["customer_id"], desc, support, w["serial_id"] if w else None, code,
                                  channel=rnd.choice(["phone", "website", "whatsapp"]), technician_id=tech)
        db.update("tickets", tid, {"reported_on": _ts(datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=rnd.randint(0, 6), hours=rnd.randint(1, 8))),
                                   "priority": rnd.choice(["0", "1", "2"])})
        if n in (2, 3):
            db.update("tickets", tid, {"stage": "diagnosed"})
        if n == 3:
            db.update("tickets", tid, {"stage": "repair"})
    # a closed warranty repair whose parts cost lands on the job
    oid = installed[-1]
    o = db.get("orders", oid)
    w = db.one("SELECT * FROM warranties WHERE order_id = ? ORDER BY id LIMIT 1", oid)
    tid = rules.create_ticket(db, o["customer_id"], "Replaced the faulty unit under warranty", support, w["serial_id"],
                              channel="phone", technician_id=techs[1])
    prod = db.get("products", w["product_id"])
    db.insert("ticket_lines", {"ticket_id": tid, "product_id": prod["id"], "qty": 1, "price_unit": prod["price"],
                               "cost": prod["cost"]})
    db.update("tickets", tid, {"labour_hours": 3, "resolution": "Unit replaced under warranty.",
                               "reported_on": _ts(datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=9))})
    rules.ticket_resolve(db, db.get("tickets", tid), techs[1])
    rules.ticket_confirm(db, db.get("tickets", tid), director["id"])


def _pipeline(db, rnd, techs, sales, director, today):
    """Fresh enquiries at every stage, so Sales has work today."""
    for i in range(7):
        name = "%s %s" % (rnd.choice(FIRST), rnd.choice(LAST))
        kw = rnd.choice([2, 3, 5])
        lid = rules.create_enquiry(db, {
            "contact_name": name, "phone": "+91 97%08d" % rnd.randint(0, 99999999),
            "email": "%s.new%d@example.com" % (name.lower().replace(" ", "."), i), "city": PLACES[i][1],
            "state": PLACES[i][2], "street": "%d, %s" % (rnd.randint(1, 250), PLACES[i][0]), "requested_kw": kw,
            "subsidy_requested": True, "salesperson_id": sales[i % 2]}, channel=rnd.choice(["web", "whatsapp", "call"]))
        db.update("leads", lid, {"created_at": _ts(datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=rnd.randint(1, 60)))})
        if i < 2:
            continue                                    # new: call them
        db.update("leads", lid, {"roof_area_sqft": 400, "monthly_bill": 3200, "grid_suitable": "yes", "stage": "contacted"})
        if i < 3:
            continue                                    # screened, survey to book
        tech = techs[0] if i in (3, 4) else rnd.choice(techs)
        sid = rules.schedule_survey(db, db.get("leads", lid), tech,
                                    _ts((today + timedelta(days=1)).replace(hour=10 + i)), director["id"], allow_past=True)
        if i < 5:
            continue                                    # survey scheduled (Ramesh visits tomorrow)
        db.update("surveys", sid, {"roof_type": "rcc", "roof_direction": "S", "roof_tilt": 15, "recommended_kw": kw})
        rules.survey_mark_done(db, db.get("surveys", sid), tech)
        if i < 6:
            continue                                    # visited, waiting for Sales approval
        rules.survey_approve(db, db.get("surveys", sid), director)
        rules.create_quote(db, db.get("leads", lid), sales[0])   # draft quote to send
