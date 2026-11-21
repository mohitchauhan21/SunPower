"""SunPower business rules, independent of the web layer.

Flow: enquiry -> phone screening -> roof survey (visited, approved by Sales)
-> quotation from the matching package -> confirmed (customer accepts online
with the advance, or Sales confirms) -> delivery + installation job + subsidy
file + customer account -> dispatch with serials (only after the advance; starts
the warranties) -> installation (checklist, photos, kW, signature) -> repairs
under / out of warranty -> job profit and the Director's dashboard.
"""
#
# WHO USES THIS FILE
#   The routers (app/routers/*.py) call these functions; they never put business
#   logic in the web layer. seed.py also uses them to build the demo data, so the
#   demo goes through exactly the same rules as real use.
#   Every function receives `db` (a db.DB object for the current request) and works
#   with plain dicts (database rows). When a rule says "no", it raises RuleError
#   with a message for the user; main.py turns that into an HTTP 400 answer.
#
import json
import secrets
from datetime import date, datetime, timedelta

from . import mailer
from .catalog import GST_GOODS, GST_SERVICE, INSTALL_CODE
from .db import now, today


# A custom error type. `class X(Exception)` makes a new kind of error;
# raising it stops the current action and its message is shown to the user.
class RuleError(Exception):
    """A business rule stopped the action; the message is shown to the user."""


# ------------------------------------------------------------------ helpers
# Rules of thumb for India: 1 kW of panels makes ~120 units (kWh) a month;
# electricity costs ~₹8 per unit; an installed system costs ~₹65,000 per kW;
# ~100 sq ft of shadow-free roof per kW. Packages are 1 to 5 kW.
UNITS_PER_KW_MONTH = 120.0
AVG_TARIFF_INR = 8.0
COST_PER_KW_INR = 65000.0
ROOF_SQFT_PER_KW = 100.0
MIN_KW, MAX_KW = 1, 5
FALLBACK_KWH_PER_KW = 1450.0

# Each status list is [(stored value, label shown to people), ...].
LEAD_STAGES = [("new", "New"), ("contacted", "Contacted"), ("survey", "Survey"),
               ("quoted", "Quoted"), ("won", "Won"), ("lost", "Lost")]
SURVEY_STATES = [("scheduled", "Scheduled"), ("done", "Visited"), ("approved", "Approved"),
                 ("rejected", "Rejected")]
ORDER_STATES = [("draft", "Draft quote"), ("sent", "Quote sent"), ("sale", "Confirmed"),
                ("cancel", "Cancelled")]
DELIVERY_STATES = [("waiting", "Waiting for advance"), ("ready", "Ready to dispatch"),
                   ("done", "Dispatched")]
JOB_STATES = [("planned", "Planned"), ("in_progress", "On site"), ("done", "Completed")]
TICKET_STAGES = [("new", "New"), ("diagnosed", "Diagnosed"), ("repair", "Repair in progress"),
                 ("awaiting", "Awaiting customer"), ("closed", "Closed"), ("cancel", "Cancelled")]
SUBSIDY_STATES = [("draft", "Documents pending"), ("applied", "Applied on portal"),
                  ("inspection", "DISCOM inspection"), ("approved", "Approved"),
                  ("disbursed", "Disbursed"), ("rejected", "Rejected")]
CHECKLIST = [("chk_stands", "Mounting stands fixed"), ("chk_panels", "Panels laid & clamped"),
             ("chk_wiring", "DCDB/ACDB & wiring connected"),
             ("chk_earthing", "Earthing & lightning arrester done"),
             ("chk_generation", "Power generation tested")]


# Label for a stored status, e.g. label(LEAD_STAGES, "won") -> "Won".
# dict(options) turns the list of pairs into a lookup table.
def label(options, key):
    return dict(options).get(key, key or "")


# Round money to 2 decimals. + 1e-9 (a tiny number) avoids 2.675 rounding down to 2.67
# because of how computers store decimals.
def r2(v):
    return round(float(v or 0) + 1e-9, 2)


# Text like "2026-11-21 10:00:00" (or just a date) -> a datetime object; None if empty or unreadable.
# Tries several formats; `continue` moves on to the next format.
def parse_dt(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    v = str(v).replace("T", " ")[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue
    return None


# Add months to a date, keeping the day valid: 31 Jan + 1 month = 28/29 Feb.
# divmod(a, b) returns (a // b, a % b): whole years and the remaining months.
# calendar.monthrange(year, month)[1] = number of days in that month.
def add_months(d, months):
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    import calendar
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


# Website address from Settings, used to build links in emails (no trailing slash).
def frontend(db):
    return (db.setting("frontend_url") or "http://localhost:5173").rstrip("/")


# ------------------------------------------------------------ calculations
# PM Surya Ghar subsidy for a system of `kw`: 30,000 per kW for the first 2 kW,
# 18,000 for the 3rd kW, never more than 78,000 in total.
def subsidy_expected(kw, state=None, include_topup=False):
    """PM Surya Ghar subsidy for `kw` in a state (central rate by state category,
    capped at 3 kW; reported state top-up only when asked). See subsidy.py."""
    from .subsidy import subsidy_for
    return subsidy_for(kw, state, include_topup)["total"]


# Suggested system size from monthly units (or the bill / ₹8), 1 to 5 kW.
# int(x + 0.5) rounds half up (360 units -> 3 kW).
def recommended_kw(units=0, bill=0):
    units = units or (bill / AVG_TARIFF_INR if bill else 0)
    if not units:
        return 0
    return int(min(max(int(units / UNITS_PER_KW_MONTH + 0.5), MIN_KW), MAX_KW))


# Savings estimate for the public website (Savings page): size, generation,
# monthly/yearly saving, price, subsidy, net cost, payback years, roof area.
# Returns None if neither units nor bill was given.
def estimate(units=0.0, bill=0.0, state=None, include_topup=False, kw=None, cost_per_kw=None, tariff=None):
    """Website savings estimate. `state` sets the subsidy (central category and
    optional reported top-up). Custom mode: pass your own `kw`, `cost_per_kw`
    (Rs per kW) and/or `tariff` (Rs per unit) to replace the defaults."""
    from .subsidy import subsidy_for
    tariff = tariff or AVG_TARIFF_INR
    units = units or (bill / tariff if bill else 0.0)
    if not units and not kw:
        return None
    custom = bool(kw or cost_per_kw or (tariff != AVG_TARIFF_INR))
    kw = round(min(max(float(kw), 0.5), 100), 1) if kw else recommended_kw(units)
    cost_per_kw = cost_per_kw or COST_PER_KW_INR
    generation = kw * UNITS_PER_KW_MONTH
    used = min(generation, units) if units else generation
    monthly_saving = used * tariff
    cost = kw * cost_per_kw
    sub = subsidy_for(kw, state, include_topup)
    net = max(cost - sub["total"], 0)
    return {"units": round(units), "kw": kw, "system_type": "on_grid", "generation": round(generation),
            "monthly_saving": round(monthly_saving), "yearly_saving": round(monthly_saving * 12),
            "cost": round(cost), "subsidy": sub["total"], "subsidy_central": sub["central"],
            "subsidy_topup": sub["topup"], "topup_available": sub["topup_available"],
            "state": sub["state"], "category": sub["category"], "net_cost": round(net),
            "cost_per_kw": round(cost_per_kw), "tariff": tariff, "custom": custom,
            "payback_years": round(net / (monthly_saving * 12), 1) if monthly_saving else 0,
            "roof_sqft": round(kw * ROOF_SQFT_PER_KW)}


# --------------------------------------------------------------- customers
# Find a customer by email (then by phone); create one if none exists.
# Fills in missing phone/address on an existing customer. Returns the customer id.
def ensure_customer(db, name, email=None, phone=None, street=None, city=None):
    email = (email or "").strip().lower() or None
    row = None
    if email:
        row = db.one("SELECT * FROM customers WHERE email = ? COLLATE NOCASE", email)
    if not row and phone:
        row = db.one("SELECT * FROM customers WHERE phone = ?", phone)
    if row:
        fill = {k: v for k, v in {"phone": phone, "street": street, "city": city, "email": email}.items()
                if v and not row.get(k)}
        db.update("customers", row["id"], fill)
        return row["id"]
    return db.insert("customers", {"name": name, "email": email, "phone": phone, "street": street,
                                   "city": city, "created_at": now()})


# Give a customer a website login (no password yet) and email them a link to choose one.
def invite_customer(db, customer_id):
    """Give a customer a website login and email a link to choose a password.
    Skips customers without email or who already have a login."""
    from .security import make_token
    cust = db.get("customers", customer_id)
    if not cust or not cust.get("email"):
        return None
    if db.one("SELECT id FROM users WHERE customer_id = ? OR email = ? COLLATE NOCASE", customer_id, cust["email"]):
        return None
    uid = db.insert("users", {"name": cust["name"], "email": cust["email"], "phone": cust["phone"],
                              "role": "customer", "customer_id": customer_id, "created_at": now()})
    send_account_email(db, uid, "invite", make_token(db, uid, "invite"))
    return uid


# Subject, first paragraph and button text of each account email, by kind.
ACCOUNT_EMAILS = {
    "reset": ("Reset your SunPower password",
              "Someone (hopefully you) asked to reset the password for your SunPower account.",
              "Choose a new password"),
    "invite": ("Your SunPower account is ready",
               "Thank you for choosing SunPower. Your order is confirmed, and you can now follow your "
               "installation, warranties and service requests online.", "Set your password"),
    "claim": ("Finish setting up your SunPower account",
              "Someone (hopefully you) tried to sign up with this email. You already have a SunPower "
              "account, so just choose a password to sign in.", "Choose a password"),
    "staff": ("Your SunPower staff account",
              "An account has been created for you on SunPower.", "Set your password"),
}


# Queue an account email (reset / invite / claim / staff) with its one-time link.
# Returns the link (the Director's screen shows it when email isn't set up yet).
def send_account_email(db, user_id, kind, token):
    user = db.get("users", user_id)
    subject, intro, button = ACCOUNT_EMAILS[kind]
    link = "%s/reset-password?token=%s%s" % (frontend(db), token, "" if kind == "reset" else "&welcome=1")
    html = mailer.branded(db, subject, ["Hi %s," % user["name"], intro + " The link works once and expires in 24 hours."],
                          button, link, "If you didn't ask for this, you can ignore this email.")
    mailer.queue(db, user["email"], subject, html)
    return link


# ----------------------------------------------------------------- enquiries
# Least-busy active salesperson (fewest open enquiries); the Director if there are no salespeople.
# The sub-SELECT inside ORDER BY counts each person's open enquiries.
def pick_salesperson(db):
    row = db.one("""SELECT u.id FROM users u WHERE u.role = 'sales' AND u.active = 1
                    ORDER BY (SELECT COUNT(*) FROM leads l WHERE l.salesperson_id = u.id
                              AND l.stage NOT IN ('won','lost')), u.id LIMIT 1""")
    if not row:
        row = db.one("SELECT id FROM users WHERE role = 'director' AND active = 1 ORDER BY id LIMIT 1")
    return row["id"] if row else None


# Create an enquiry (lead) from the website, a call, WhatsApp... Required: name and phone.
# Assigns a salesperson and sets the "call within 2 hours" reminder. Returns the lead id.
def create_enquiry(db, vals, channel="web", customer_id=None, actor_id=None):
    name = (vals.get("contact_name") or "").strip()
    if not name or not (vals.get("phone") or "").strip():
        raise RuleError("Please enter the customer's name and phone number.")
    data = {k: vals.get(k) for k in ("contact_name", "phone", "email", "street", "city", "requested_kw",
                                     "system_type", "subsidy_requested", "monthly_bill", "monthly_units",
                                     "roof_area_sqft", "notes", "discom", "consumer_no") if vals.get(k) is not None}
    data.update({"channel": channel, "stage": "new", "customer_id": customer_id,
                 "salesperson_id": vals.get("salesperson_id") or pick_salesperson(db),
                 "next_action": "Call within 2 hours: screen roof, bill and grid",
                 "next_action_due": today(), "created_at": now()})
    data["system_type"] = "off_grid" if data.get("system_type") == "off_grid" else "on_grid"
    data["subsidy_requested"] = 1 if data.get("subsidy_requested") else 0
    data["ref"] = db.next_ref("lead", "ENQ-")
    lid = db.insert("leads", data)
    db.note("lead", lid, "Enquiry received (%s)." % channel, actor_id)
    return lid


# Phone screening is complete when we know the roof area, the bill or units, and the grid is suitable.
def lead_screening_ok(lead):
    return bool(lead["roof_area_sqft"] and (lead["monthly_bill"] or lead["monthly_units"])
                and lead["grid_suitable"] == "yes")


# Suggested size from the enquiry's units or bill.
def lead_recommended_kw(lead):
    return recommended_kw(lead.get("monthly_units") or 0, lead.get("monthly_bill") or 0)


# The latest approved survey of an enquiry (or None).
def approved_survey(db, lead_id):
    return db.one("SELECT * FROM surveys WHERE lead_id = ? AND state = 'approved' ORDER BY id DESC LIMIT 1", lead_id)


# Book a roof survey with a technician. Refused until phone screening is complete.
def schedule_survey(db, lead, technician_id, survey_date, actor_id):
    if not lead_screening_ok(lead):
        raise RuleError("Complete the phone screening first: shadow-free roof area, monthly bill or "
                        "units, and a suitable grid connection.")
    if not technician_id:
        raise RuleError("Choose the technician who will visit.")
    sid = db.insert("surveys", {
        "ref": db.next_ref("survey", "SRV-"), "lead_id": lead["id"], "technician_id": technician_id,
        "survey_date": survey_date, "state": "scheduled",
        "recommended_kw": lead["requested_kw"] or lead_recommended_kw(lead),
        "usable_area_sqft": lead["roof_area_sqft"], "created_at": now()})
    if lead["stage"] in ("new", "contacted"):
        db.update("leads", lead["id"], {"stage": "survey"})
    tech = db.get("users", technician_id)
    db.note("lead", lead["id"], "Roof survey scheduled with %s." % tech["name"], actor_id)
    return sid


# Technician (or Sales) marks the visit done; needs at least the roof direction and area.
def survey_mark_done(db, survey, actor_id):
    if survey["state"] != "scheduled":
        raise RuleError("Only scheduled surveys can be marked visited.")
    if not (survey["roof_direction"] and survey["usable_area_sqft"]):
        raise RuleError("Record at least the roof direction and shadow-free area first.")
    db.update("surveys", survey["id"], {"state": "done"})
    db.note("survey", survey["id"], "Site visited.", actor_id)


# Sales or the Director approves a visited survey; its recommended kW becomes the enquiry's size.
def survey_approve(db, survey, actor):
    if actor["role"] not in ("sales", "director"):
        raise RuleError("Only Sales or the Director can approve a survey.")
    if survey["state"] != "done":
        raise RuleError("Only visited surveys can be approved.")
    if not survey["recommended_kw"]:
        raise RuleError("Set the recommended system size (kW) first.")
    db.update("surveys", survey["id"], {"state": "approved"})
    db.update("leads", survey["lead_id"], {"requested_kw": survey["recommended_kw"]})  # the approved size becomes the enquiry's size
    db.note("survey", survey["id"], "Survey approved (%s kW)." % survey["recommended_kw"], actor["id"])


# ------------------------------------------------------------------- orders
# Recalculate each line's amount and the order's totals (before GST, GST, total).
def recompute_order(db, order_id):
    lines = db.q("SELECT * FROM order_lines WHERE order_id = ?", order_id)
    untaxed = tax = 0.0
    for l in lines:
        sub = r2(l["qty"] * l["price_unit"] * (1 - (l["discount"] or 0) / 100.0))
        db.exec("UPDATE order_lines SET subtotal = ? WHERE id = ?", sub, l["id"])
        untaxed += sub
        tax += sub * (l["tax_rate"] or 0) / 100.0
    db.update("orders", order_id, {"amount_untaxed": r2(untaxed), "amount_tax": r2(tax),
                                   "amount_total": r2(untaxed + tax)})


# The package (kit product) for a size and system type, e.g. 3 kW on-grid.
def package_for(db, kw, system_type):
    return db.one("SELECT * FROM products WHERE is_kit = 1 AND active = 1 AND kw = ? AND system_type = ?",
                  round(kw or 0), system_type or "on_grid")


# Turn an enquiry with an approved survey into a draft quotation:
# the matching package + installation (kW x price per kW). Returns the order id.
def create_quote(db, lead, actor_id, kw=None, system_type=None):
    survey = approved_survey(db, lead["id"])
    if not survey:
        raise RuleError("A quotation can only be prepared after the roof survey is approved.")
    kw = kw or survey["recommended_kw"] or lead["requested_kw"]
    system_type = system_type or lead["system_type"] or "on_grid"
    kit = package_for(db, kw, system_type)
    if not kit:
        raise RuleError("No package matches %s kW %s." % (kw, system_type))
    install = db.one("SELECT * FROM products WHERE code = ?", INSTALL_CODE)
    customer_id = lead["customer_id"] or ensure_customer(db, lead["contact_name"], lead["email"], lead["phone"],
                                                         lead["street"], lead["city"])
    if not lead["customer_id"]:
        db.update("leads", lead["id"], {"customer_id": customer_id})
    valid = (date.today() + timedelta(days=int(db.setting("quote_valid_days", 15)))).isoformat()
    oid = db.insert("orders", {
        "ref": db.next_ref("order", "SO-"), "lead_id": lead["id"], "customer_id": customer_id,
        "survey_id": survey["id"], "state": "draft", "kit_product_id": kit["id"], "kw": kit["kw"],
        "system_type": kit["system_type"], "salesperson_id": lead["salesperson_id"] or actor_id,
        "date_order": now(), "valid_until": valid, "note": db.setting("quote_note"),
        "access_token": secrets.token_urlsafe(16), "created_at": now()})  # secret token: lets the customer open the quote PDF without signing in
    db.insert("order_lines", {"order_id": oid, "product_id": kit["id"], "description": kit["name"], "qty": 1,
                              "price_unit": kit["price"], "tax_rate": GST_GOODS})
    db.insert("order_lines", {"order_id": oid, "product_id": install["id"], "description": install["name"],
                              "qty": kit["kw"], "price_unit": install["price"], "tax_rate": GST_SERVICE})
    recompute_order(db, oid)
    db.update("leads", lead["id"], {"stage": "quoted"})
    db.note("lead", lead["id"], "Quotation prepared.", actor_id)
    db.note("order", oid, "Quotation prepared from the %s package." % kit["name"], actor_id)
    return oid


# Yearly generation and payback for an order: asks PVGIS (a free EU solar calculator)
# for the surveyed roof; if that fails (no internet), uses 1450 kWh per kW per year.
# httpx is the HTTP client library used to call other websites.
def generation_estimate(db, order):
    """Yearly generation from PVGIS (EU JRC) for the surveyed roof, with an
    offline rule of thumb."""
    import httpx
    survey = db.get("surveys", order["survey_id"]) if order["survey_id"] else {}
    aspect = {"S": 0, "SW": 45, "W": 90, "NW": 135, "N": 180, "NE": -135, "E": -90, "SE": -45}
    kw = order["kw"] or 1
    lat = (survey or {}).get("latitude") or 23.0225
    lon = (survey or {}).get("longitude") or 72.5714
    try:
        r = httpx.get("https://re.jrc.ec.europa.eu/api/v5_2/PVcalc", timeout=12, params={
            "lat": lat, "lon": lon, "peakpower": kw, "loss": 14, "angle": (survey or {}).get("roof_tilt") or 20,
            "aspect": aspect.get((survey or {}).get("roof_direction") or "S", 0), "outputformat": "json"})
        r.raise_for_status()
        kwh = r.json()["outputs"]["totals"]["fixed"]["E_y"]
        source = "PVGIS (EU JRC) for %.4f, %.4f" % (lat, lon)
    except Exception:
        kwh = kw * FALLBACK_KWH_PER_KW
        source = "Rule of thumb (%d kWh/kW/yr)" % FALLBACK_KWH_PER_KW
    savings = kwh * AVG_TARIFF_INR
    db.update("orders", order["id"], {"est_kwh_year": round(kwh), "est_savings_year": round(savings),
                                      "est_payback_years": round(order["amount_total"] / savings, 1) if savings else 0,
                                      "est_source": source})


# Link the customer opens to review and accept a quotation.
def quote_link(db, order):
    return "%s/account/quote/%s" % (frontend(db), order["id"])


# Mark a quote as sent and email it (also creating the customer's login if needed).
def send_quote(db, order, actor_id):
    if order["state"] not in ("draft", "sent"):
        raise RuleError("Only quotations can be sent.")
    if not approved_survey(db, order["lead_id"]) and order["lead_id"]:
        raise RuleError("The customer can only receive a quote after the roof survey is approved.")
    cust = db.get("customers", order["customer_id"])
    db.update("orders", order["id"], {"state": "sent"})
    if cust.get("email"):
        if not db.one("SELECT id FROM users WHERE customer_id = ?", cust["id"]):
            invite_customer(db, cust["id"])
        html = mailer.branded(db, "Your solar quotation %s" % order["ref"], [
            "Hi %s," % cust["name"],
            "Your quotation for a %g kW rooftop system is ready: %s including GST." % (
                order["kw"], money(order["amount_total"])),
            "Review it, accept it online and pay the %s%% advance to book your installation." % db.setting("advance_pct")],
            "Review my quotation", quote_link(db, order))
        mailer.queue(db, cust["email"], "Your SunPower quotation %s" % order["ref"], html)
    db.note("order", order["id"], "Quotation sent to the customer.", actor_id)


# Format rupees the Indian way: 1234567 -> "₹12,34,567" (groups of 2 after the first 3 digits).
def money(v):
    s = "%.0f" % round(v or 0)
    neg = s.startswith("-")
    s = s.lstrip("-")
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if neg else "") + "₹" + s


# Confirm an order. This is the big automatic step: it creates the warehouse delivery
# (the package broken into its parts), the installation job, the subsidy file (if wanted),
# marks the enquiry won and invites the customer to their account.
def confirm_order(db, order, actor_id=None, invite=True, accepted_by=None):
    if order["state"] not in ("draft", "sent"):
        raise RuleError("This order is already %s." % label(ORDER_STATES, order["state"]).lower())
    if order["lead_id"] and not approved_survey(db, order["lead_id"]):
        raise RuleError("The roof survey must be approved before the order is confirmed.")
    data = {"state": "sale", "confirmed_at": now()}
    if accepted_by:
        data.update({"accepted_by": accepted_by, "accepted_at": now()})
    db.update("orders", order["id"], data)
    order = db.get("orders", order["id"])
    cust = db.get("customers", order["customer_id"])
    # delivery order for the warehouse (kit exploded into components)
    did = db.insert("deliveries", {"ref": db.next_ref("delivery", "DEL-"), "order_id": order["id"],
                                   "state": "waiting", "created_at": now()})
    for line in db.q("SELECT ol.* FROM order_lines ol JOIN products p ON p.id = ol.product_id "
                     "WHERE ol.order_id = ? AND p.is_service = 0", order["id"]):
        prod = db.get("products", line["product_id"])
        if prod["is_kit"]:
            for kl in db.q("SELECT * FROM kit_lines WHERE kit_id = ?", prod["id"]):
                db.insert("delivery_lines", {"delivery_id": did, "product_id": kl["product_id"],
                                             "qty": kl["qty"] * line["qty"]})
        else:
            db.insert("delivery_lines", {"delivery_id": did, "product_id": prod["id"], "qty": line["qty"]})
    # installation job on the crew schedule
    when = (datetime.now() + timedelta(days=7)).replace(hour=10, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")
    label_type = "On-Grid" if order["system_type"] == "on_grid" else "Off-Grid"
    jid = db.insert("jobs", {"ref": db.next_ref("job", "JOB-"), "order_id": order["id"],
                             "customer_id": order["customer_id"], "kw_planned": order["kw"],
                             "scheduled_at": when, "state": "planned", "created_at": now(),
                             "notes": "Install %g kW %s – %s" % (order["kw"], label_type, cust["name"])})
    # subsidy paperwork
    lead = db.get("leads", order["lead_id"]) if order["lead_id"] else None
    if lead and lead["subsidy_requested"]:
        db.insert("subsidies", {"ref": db.next_ref("subsidy", "SUB-"), "order_id": order["id"],
                                "customer_id": order["customer_id"], "kw": order["kw"],
                                "amount_expected": subsidy_expected(order["kw"])})
    if lead:
        db.update("leads", lead["id"], {"stage": "won"})
    refresh_delivery_state(db, order["id"])
    db.note("order", order["id"], "Order confirmed: delivery %s sent to the warehouse and job %s put on the crew "
            "schedule." % (db.val("SELECT ref FROM deliveries WHERE id = ?", did),
                           db.val("SELECT ref FROM jobs WHERE id = ?", jid)), actor_id)
    if invite:
        invite_customer(db, order["customer_id"])
    return order


# Cancel an order (not possible once the kit has been dispatched).
def cancel_order(db, order, actor_id):
    if order["state"] == "sale" and db.val("SELECT COUNT(*) FROM deliveries WHERE order_id = ? AND state = 'done'", order["id"]):
        raise RuleError("A dispatched order can't be cancelled.")
    db.update("orders", order["id"], {"state": "cancel"})
    db.exec("DELETE FROM deliveries WHERE order_id = ? AND state != 'done'", order["id"])
    db.exec("DELETE FROM jobs WHERE order_id = ? AND state = 'planned'", order["id"])
    db.note("order", order["id"], "Order cancelled.", actor_id)


# ---------------------------------------------------------- money: invoices
# Money received so far for an order (completed payments only).
def order_paid(db, order_id):
    return r2(db.val("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE order_id = ? AND state = 'done'", order_id))


# The advance required before dispatch: advance % (Settings) of the order total.
def advance_needed(db, order):
    pct = float(db.setting("advance_pct", 30) or 0)
    return r2(order["amount_total"] * pct / 100.0)


# How much of the advance is still missing (never below 0).
def advance_due(db, order):
    return max(r2(advance_needed(db, order) - order_paid(db, order["id"])), 0)


# Split an amount into (before GST, GST) using the order's own ratio.
def _split_tax(order, amount):
    ratio = (order["amount_untaxed"] / order["amount_total"]) if order["amount_total"] else 1
    untaxed = r2(amount * ratio)
    return untaxed, r2(amount - untaxed)


# Create an invoice of `kind` (advance / final / service) for `amount` including GST.
def create_invoice(db, order, kind, amount):
    untaxed, tax = _split_tax(order, amount)
    return db.insert("invoices", {"ref": db.next_ref("invoice", "INV-"), "order_id": order["id"],
                                  "customer_id": order["customer_id"], "kind": kind, "amount_untaxed": untaxed,
                                  "amount_tax": tax, "amount_total": r2(amount), "date": today()})


# Invoice whatever part of the order hasn't been invoiced yet.
def final_invoice(db, order, actor_id):
    if order["state"] != "sale":
        raise RuleError("Only confirmed orders can be invoiced.")
    billed = r2(db.val("SELECT COALESCE(SUM(amount_total), 0) FROM invoices WHERE order_id = ? AND state != 'cancel'",
                       order["id"]))
    rest = r2(order["amount_total"] - billed)
    if rest <= 0.5:
        raise RuleError("The full order value is already invoiced.")
    iid = create_invoice(db, order, "final", rest)
    allocate_payments(db, order["id"])
    db.note("order", order["id"], "Final invoice %s issued for %s." % (
        db.val("SELECT ref FROM invoices WHERE id = ?", iid), money(rest)), actor_id)
    return iid


# Mark invoices paid using the money received, oldest invoice first.
def allocate_payments(db, order_id):
    """Spread the order's received money over its invoices, oldest first."""
    pool = order_paid(db, order_id)
    for inv in db.q("SELECT * FROM invoices WHERE order_id = ? AND state != 'cancel' ORDER BY id", order_id):
        paid = min(pool, inv["amount_total"])
        pool = r2(pool - paid)
        db.update("invoices", inv["id"], {"amount_paid": r2(paid),
                                          "state": "paid" if paid + 0.5 >= inv["amount_total"] else "posted"})


# Record money received for an order (cash, bank, UPI, online...).
# Creates an advance invoice if needed, and confirms a quotation automatically once the advance is paid.
def record_payment(db, order, amount, method, actor_id=None, provider_ref=None, purpose="advance"):
    """Money received for an order. A payment without an open invoice gets an
    advance invoice (marked paid). An online payment of the advance on a sent
    quotation confirms the order."""
    amount = r2(amount)
    if amount <= 0:
        raise RuleError("Enter an amount above zero.")
    if order["state"] == "cancel":
        raise RuleError("This order is cancelled.")
    was_due = advance_due(db, order) > 0 or order["state"] != "sale"  # remember: was the advance still missing before this payment?
    open_amount = r2(db.val("SELECT COALESCE(SUM(amount_total - amount_paid), 0) FROM invoices "
                            "WHERE order_id = ? AND state = 'posted'", order["id"]))
    pid = db.insert("payments", {"ref": db.next_ref("payment", "PAY-"), "order_id": order["id"],
                                 "customer_id": order["customer_id"], "amount": amount, "method": method,
                                 "provider_ref": provider_ref, "state": "done", "purpose": purpose,
                                 "date": now(), "created_by": actor_id})
    if amount > open_amount + 0.5:
        create_invoice(db, order, "advance" if purpose == "advance" else "final", r2(amount - open_amount))
    allocate_payments(db, order["id"])
    db.note("order", order["id"], "Payment of %s received (%s)." % (money(amount), method), actor_id)
    if order["state"] in ("draft", "sent") and order_paid(db, order["id"]) + 0.5 >= advance_needed(db, order):  # advance paid on a quote -> confirm the order
        confirm_order(db, order, actor_id, accepted_by=order.get("accepted_by"))
    order = db.get("orders", order["id"])
    refresh_delivery_state(db, order["id"])
    if order["state"] == "sale" and was_due and advance_due(db, order) == 0:
        db.note("order", order["id"], "The advance is complete: the kit can be dispatched.", actor_id)
    return pid


# A delivery is "ready" when the advance is fully paid, otherwise "waiting".
def refresh_delivery_state(db, order_id):
    order = db.get("orders", order_id)
    ready = advance_due(db, order) == 0
    db.exec("UPDATE deliveries SET state = ? WHERE order_id = ? AND state != 'done'",
            "ready" if ready else "waiting", order_id)


# -------------------------------------------------------------------- stock
# Add stock: serial-tracked items need one serial per unit; others just a quantity.
def receive_stock(db, product, qty, serials, actor_id, note=None):
    qty = float(qty or 0)
    names = [s.strip() for s in (serials or []) if s and s.strip()]
    if product["tracking"] == "serial":
        if not names:
            raise RuleError("Enter the serial number of each unit received.")
        qty = len(names)
    if qty <= 0:
        raise RuleError("Enter a quantity above zero.")
    for name in names:
        if db.one("SELECT id FROM serials WHERE name = ? AND product_id = ?", name, product["id"]):
            raise RuleError("Serial %s already exists." % name)
        db.insert("serials", {"name": name, "product_id": product["id"], "created_at": now()})
    db.exec("UPDATE products SET qty_on_hand = qty_on_hand + ? WHERE id = ?", qty, product["id"])
    db.insert("stock_moves", {"product_id": product["id"], "qty": qty, "kind": "in", "note": note,
                              "user_id": actor_id, "date": now()})
    return qty


# Dispatch a delivery. Checks: advance paid (or a Director override), enough stock,
# a serial for every tracked unit. Then takes the stock out and starts a warranty
# for every delivered serial/batch. Returns the list of serials whose warranty started.
def validate_delivery(db, delivery, serials_by_line, actor, override=False):
    """Dispatch: advance paid, stock available, a serial for every tracked unit.
    Starts the warranty of every delivered serial/lot."""
    if delivery["state"] == "done":
        raise RuleError("Already dispatched.")
    order = db.get("orders", delivery["order_id"])
    due = advance_due(db, order)
    if due > 0 and not (override and actor["role"] == "director"):  # only the Director may dispatch without the advance
        raise RuleError("%s cannot be dispatched yet: %s%% advance (%s) is required, %s received so far." % (
            order["ref"], db.setting("advance_pct"), money(advance_needed(db, order)), money(order_paid(db, order["id"]))))
    lines = db.q("SELECT dl.*, p.name, p.tracking, p.qty_on_hand, p.warranty_months, p.cost FROM delivery_lines dl "
                 "JOIN products p ON p.id = dl.product_id WHERE dl.delivery_id = ?", delivery["id"])
    plan = []
    for l in lines:
        names = [s.strip() for s in (serials_by_line.get(str(l["id"])) or serials_by_line.get(l["id"]) or [])
                 if s and s.strip()]
        if l["tracking"] == "serial" and len(set(names)) != int(l["qty"]):
            raise RuleError("%s: scan %d serial numbers (got %d)." % (l["name"], int(l["qty"]), len(set(names))))
        if l["tracking"] == "lot" and not names:
            raise RuleError("%s: enter the batch / lot number." % l["name"])
        if l["qty_on_hand"] < l["qty"]:
            raise RuleError("Not enough %s in stock (%g needed, %g available)." % (l["name"], l["qty"], l["qty_on_hand"]))
        plan.append((l, names))
    start = today()
    started = []
    for l, names in plan:
        db.exec("UPDATE products SET qty_on_hand = qty_on_hand - ? WHERE id = ?", l["qty"], l["product_id"])
        db.insert("stock_moves", {"product_id": l["product_id"], "qty": -l["qty"], "kind": "out",
                                  "delivery_id": delivery["id"], "user_id": actor["id"], "date": now()})
        db.exec("UPDATE delivery_lines SET serials = ? WHERE id = ?", json.dumps(names), l["id"])
        for name in names:
            s = db.one("SELECT * FROM serials WHERE name = ? AND product_id = ?", name, l["product_id"])
            if s and s["state"] == "delivered" and l["tracking"] == "serial":
                raise RuleError("Serial %s was already delivered." % name)
            if s:
                db.update("serials", s["id"], {"state": "delivered", "delivery_id": delivery["id"],
                                               "customer_id": order["customer_id"], "order_id": order["id"]})
                sid = s["id"]
            else:
                sid = db.insert("serials", {"name": name, "product_id": l["product_id"], "state": "delivered",
                                            "delivery_id": delivery["id"], "customer_id": order["customer_id"],
                                            "order_id": order["id"], "created_at": now()})
            if l["warranty_months"] and not db.one("SELECT id FROM warranties WHERE serial_id = ? AND customer_id = ?",
                                                   sid, order["customer_id"]):
                end = add_months(date.fromisoformat(start), l["warranty_months"]).isoformat()
                db.insert("warranties", {"serial_id": sid, "product_id": l["product_id"],
                                         "customer_id": order["customer_id"], "order_id": order["id"],
                                         "delivery_id": delivery["id"], "start_date": start,
                                         "months": l["warranty_months"], "end_date": end})
                started.append(name)
    db.update("deliveries", delivery["id"], {"state": "done", "date_done": now(), "done_by": actor["id"]})
    msg = "Kit dispatched."
    if started:
        msg += " Warranty started for %d serial/lot numbers: %s." % (len(started), ", ".join(started))
    db.note("delivery", delivery["id"], msg, actor["id"])
    db.note("order", order["id"], msg, actor["id"])
    return started


# --------------------------------------------------------------------- jobs
# Technician starts the installation on site.
def job_start(db, job, actor_id):
    if job["state"] == "done":
        raise RuleError("This job is already completed.")
    db.update("jobs", job["id"], {"state": "in_progress", "site_start": job["site_start"] or now()})
    db.note("job", job["id"], "Work started on site.", actor_id)


# Finish an installation. Refused until: checklist complete, a roof photo,
# the installed kW, the customer's signature and the kit dispatched. Then logs
# each technician's hours (labour cost) and emails the certificate link.
def job_finish(db, job, actor):
    missing = [lbl for f, lbl in CHECKLIST if not job[f]]
    if missing:
        raise RuleError("Checklist incomplete: %s." % ", ".join(missing))
    if not db.val("SELECT COUNT(*) FROM attachments WHERE owner_type = 'job' AND owner_id = ?", job["id"]):
        raise RuleError("Upload at least one photo of the finished roof.")
    if not job["kw_confirmed"]:
        raise RuleError("Confirm the installed system size (kW).")
    if not job["signature"]:
        raise RuleError("The homeowner must sign to accept the work.")
    if not db.val("SELECT COUNT(*) FROM deliveries WHERE order_id = ? AND state = 'done'", job["order_id"]):
        raise RuleError("The kit hasn't been dispatched yet.")
    end = now()
    start = job["site_start"] or end
    hours = max((parse_dt(end) - parse_dt(start)).total_seconds() / 3600.0, 0.25)  # time on site in hours, at least a quarter hour
    db.update("jobs", job["id"], {"state": "done", "site_start": start, "site_end": end,
                                  "signed_on": job["signed_on"] or end})
    techs = db.q("SELECT u.* FROM job_techs jt JOIN users u ON u.id = jt.user_id WHERE jt.job_id = ?", job["id"]) or [actor]
    for t in techs:
        db.insert("timesheets", {"job_id": job["id"], "user_id": t["id"], "hours": round(hours, 2),
                                 "rate": t.get("hourly_rate") or 0, "date": today()})
    cust = db.get("customers", job["customer_id"])
    order = db.get("orders", job["order_id"])
    if cust.get("email"):
        html = mailer.branded(db, "Your solar system is installed", [
            "Hi %s," % cust["name"],
            "Our crew has installed and tested your %g kW system (order %s), and it was accepted by %s." % (
                job["kw_confirmed"], order["ref"], job["signed_by"] or cust["name"]),
            "Your installation certificate and the warranty of every panel and inverter are in your account."],
            "View my certificate", "%s/print/certificate/%s?token=%s" % (frontend(db), job["id"], order["access_token"]))
        mailer.queue(db, cust["email"], "Installation complete – SunPower certificate", html)
    db.note("job", job["id"], "Installation completed and accepted by %s." % (job["signed_by"] or cust["name"]), actor["id"])
    db.note("order", job["order_id"], "Installation completed (%s)." % job["ref"], actor["id"])


# ------------------------------------------------------------------ tickets
# True if the warranty covers that day (dates as "YYYY-MM-DD" text compare correctly).
def warranty_active_on(w, day):
    return bool(w and w["start_date"] <= day <= w["end_date"])


# Create a service request. If a serial is given, links its product, order and warranty.
def create_ticket(db, customer_id, description, actor_id=None, serial_id=None, fault_code=None,
                  channel="phone", technician_id=None):
    description = (description or "").strip()
    if len(description) < 10:
        raise RuleError("Please describe the problem in a few words (at least 10 characters).")
    data = {"ref": db.next_ref("ticket", "TKT-"), "customer_id": customer_id, "description": description,
            "fault_code": (fault_code or "").strip() or None, "reported_on": now(), "stage": "new",
            "channel": channel, "technician_id": technician_id,
            "labour_rate": float(db.setting("labour_rate", 500) or 500)}
    if serial_id:
        serial = db.get("serials", serial_id)
        w = db.one("SELECT * FROM warranties WHERE serial_id = ? AND customer_id = ?", serial_id, customer_id)
        data.update({"serial_id": serial_id, "product_id": serial["product_id"], "order_id": serial["order_id"],
                     "warranty_id": w["id"] if w else None})
    tid = db.insert("tickets", data)
    db.note("ticket", tid, "Request raised (%s)." % channel, actor_id)
    return tid


# Money for a request: parts price, labour, cost to the company, and what the customer
# pays (nothing if the equipment was under warranty on the day it was reported).
def ticket_amounts(db, ticket):
    lines = db.q("SELECT * FROM ticket_lines WHERE ticket_id = ?", ticket["id"])
    parts = sum(l["qty"] * l["price_unit"] for l in lines)
    parts_cost = sum(l["qty"] * l["cost"] for l in lines)
    labour = (ticket["labour_hours"] or 0) * (ticket["labour_rate"] or 0)
    w = db.get("warranties", ticket["warranty_id"]) if ticket["warranty_id"] else None
    under = warranty_active_on(w, (ticket["reported_on"] or now())[:10])  # [:10] keeps just the date part
    return {"parts_price": r2(parts), "labour": r2(labour), "repair_cost": r2(parts_cost + labour),
            "customer_charge": 0.0 if under else r2(parts + labour), "under_warranty": under,
            "warranty_end": w["end_date"] if w else None}


# Repair done: invoice the customer if out of warranty, then ask them to confirm by email.
def ticket_resolve(db, ticket, actor_id):
    if ticket["stage"] in ("closed", "cancel", "awaiting"):
        raise RuleError("This request is already %s." % label(TICKET_STAGES, ticket["stage"]).lower())
    if not (ticket["resolution"] or "").strip():
        raise RuleError("Describe what was repaired or replaced first.")
    amounts = ticket_amounts(db, ticket)
    if not amounts["under_warranty"] and amounts["customer_charge"] and not ticket["invoice_id"]:
        untaxed = amounts["customer_charge"]
        tax = r2(untaxed * GST_SERVICE / 100.0)
        iid = db.insert("invoices", {"ref": db.next_ref("invoice", "INV-"), "ticket_id": ticket["id"],
                                     "order_id": ticket["order_id"], "customer_id": ticket["customer_id"],
                                     "kind": "service", "amount_untaxed": untaxed, "amount_tax": tax,
                                     "amount_total": r2(untaxed + tax), "date": today()})
        db.update("tickets", ticket["id"], {"invoice_id": iid})
        db.note("ticket", ticket["id"], "Out of warranty: invoice %s created for %s." % (
            db.val("SELECT ref FROM invoices WHERE id = ?", iid), money(untaxed + tax)), actor_id)
    db.update("tickets", ticket["id"], {"stage": "awaiting"})
    cust = db.get("customers", ticket["customer_id"])
    if cust.get("email"):
        html = mailer.branded(db, "Your repair is done", [
            "Hi %s," % cust["name"], "We've finished working on request %s. Please confirm everything works." % ticket["ref"]],
            "Confirm the repair", "%s/account?tab=service" % frontend(db))
        mailer.queue(db, cust["email"], "Please confirm your repair (%s)" % ticket["ref"], html)
    db.note("ticket", ticket["id"], "Repair completed; waiting for the customer to confirm.", actor_id)


# The customer confirms the fix: the request is closed.
def ticket_confirm(db, ticket, actor_id):
    if ticket["stage"] != "awaiting":
        raise RuleError("This request is not waiting for confirmation.")
    db.update("tickets", ticket["id"], {"stage": "closed", "customer_confirmed": 1, "closed_on": now()})
    db.note("ticket", ticket["id"], "Customer confirmed the system works. Request closed.", actor_id)


# The customer says it's still not working: back to "repair".
def ticket_reopen(db, ticket, actor_id, note=""):
    db.update("tickets", ticket["id"], {"stage": "repair", "customer_confirmed": 0, "closed_on": None})
    db.note("ticket", ticket["id"], "Reopened: the problem is not fixed. %s" % (note or ""), actor_id)


# ---------------------------------------------------------------- financials
# Job costing for one order: revenue - material - labour - warranty repairs = profit,
# plus the job stage and what is still pending (Dispatch, Installation, Payment, Subsidy).
# Used by the dashboard, Insights and the order screen (Director only).
def order_financials(db, order):
    """Job costing: revenue - material - labour - warranty repairs."""
    oid = order["id"]
    invoiced = r2(db.val("SELECT COALESCE(SUM(amount_untaxed), 0) FROM invoices WHERE order_id = ? AND state != 'cancel' "
                         "AND kind != 'service'", oid))
    collected = order_paid(db, oid)
    material = r2(db.val("SELECT COALESCE(SUM(-m.qty * p.cost), 0) FROM stock_moves m JOIN deliveries d ON d.id = m.delivery_id "
                         "JOIN products p ON p.id = m.product_id WHERE d.order_id = ?", oid))
    labour_row = db.one("SELECT COALESCE(SUM(t.hours * t.rate), 0) AS cost, COALESCE(SUM(t.hours), 0) AS hours "
                        "FROM timesheets t JOIN jobs j ON j.id = t.job_id WHERE j.order_id = ?", oid)
    repair = 0.0
    for t in db.q("SELECT * FROM tickets WHERE order_id = ? AND stage != 'cancel'", oid):
        a = ticket_amounts(db, t)
        if a["under_warranty"]:
            repair += a["repair_cost"]
    revenue = order["amount_untaxed"] if order["state"] == "sale" else 0.0
    profit = r2(revenue - material - labour_row["cost"] - repair)  # the job's profit
    delivered = bool(db.val("SELECT COUNT(*) FROM deliveries WHERE order_id = ?", oid)) and not db.val(
        "SELECT COUNT(*) FROM deliveries WHERE order_id = ? AND state != 'done'", oid)
    jobs = db.q("SELECT state FROM jobs WHERE order_id = ?", oid)
    installed = bool(jobs) and all(j["state"] == "done" for j in jobs)
    paid = collected + 0.5 >= order["amount_total"]
    pending = []
    if order["state"] != "sale":
        stage = "quote"
    else:
        if not delivered:
            pending.append("Dispatch")
        if not installed:
            pending.append("Installation")
        if not paid:
            pending.append("Payment")
        if db.val("SELECT COUNT(*) FROM subsidies WHERE order_id = ? AND state NOT IN ('disbursed','rejected')", oid):
            pending.append("Subsidy")
        stage = ("closed" if not pending or pending == ["Subsidy"] else "installed" if installed
                 else "dispatched" if delivered else "confirmed")
    return {"invoiced": invoiced, "collected": collected, "material": material,
            "labour": r2(labour_row["cost"]), "hours": r2(labour_row["hours"]), "repair": r2(repair),
            "revenue": r2(revenue), "profit": profit, "margin": round(profit / revenue * 100, 1) if revenue else 0.0,
            "stage": stage, "pending": pending}


# Labels for the job stages computed by order_financials().
JOB_STAGE_LABELS = {"quote": "Quotation", "confirmed": "Confirmed – awaiting dispatch",
                    "dispatched": "Dispatched – awaiting install", "installed": "Installed",
                    "closed": "Completed & paid"}


# First and last day of a period: today, this week (from Monday), this month or this year.
def period_bounds(period):
    t = date.today()
    if period == "today":
        start = t
    elif period == "week":
        start = t - timedelta(days=t.weekday())
    elif period == "year":
        start = t.replace(month=1, day=1)
    else:
        start = t.replace(day=1)
    return start, t


# ------------------------------------------------------------ online payments
# Which online payment options are switched on: Razorpay (if keys are set) and/or test payments.
def payment_modes(db):
    modes = []
    if db.setting("razorpay_key_id") and db.setting("razorpay_key_secret"):
        modes.append("razorpay")
    if db.setting("test_payments", "1") == "1":
        modes.append("test")
    return modes


# Start an online payment: a "pending" payment row, plus a Razorpay order when Razorpay is set up.
# Returns what the website needs to open the payment window.
def start_online_payment(db, order, amount, purpose, user_id):
    """Create a pending payment (and a Razorpay order when Razorpay is set up)."""
    import httpx
    modes = payment_modes(db)
    if not modes:
        raise RuleError("Online payment isn't switched on yet. Please call us on %s to pay." % db.setting("company_phone"))
    amount = r2(amount)
    if amount <= 0:
        raise RuleError("Nothing to pay right now. Thank you!")
    mode = modes[0]
    pid = db.insert("payments", {"ref": db.next_ref("payment", "PAY-"), "order_id": order["id"],
                                 "customer_id": order["customer_id"], "amount": amount, "method": mode,
                                 "state": "pending", "purpose": purpose, "date": now(), "created_by": user_id})
    out = {"payment_id": pid, "mode": mode, "amount": amount, "currency": "INR",
           "description": "%s %s" % ("Advance for" if purpose == "advance" else "Payment for", order["ref"])}
    if mode == "razorpay":
        try:
            r = httpx.post("https://api.razorpay.com/v1/orders", timeout=15,
                           auth=(db.setting("razorpay_key_id"), db.setting("razorpay_key_secret")),
                           json={"amount": int(round(amount * 100)), "currency": "INR",
                                 "receipt": "PAY-%s" % pid, "notes": {"order": order["ref"]}})
            r.raise_for_status()
            rz = r.json()
        except Exception:
            raise RuleError("The payment service isn't reachable right now. Please try again in a minute.")
        db.update("payments", pid, {"provider_ref": rz["id"]})
        out["razorpay"] = {"key": db.setting("razorpay_key_id"), "order_id": rz["id"],
                           "name": db.setting("company_name")}
    return out


# The bank confirmed a pending payment: record it as received (via record_payment).
def complete_online_payment(db, payment, provider_ref=None, actor_id=None):
    if payment["state"] == "done":
        return payment["id"]
    order = db.get("orders", payment["order_id"])
    db.exec("DELETE FROM payments WHERE id = ?", payment["id"])  # re-recorded as a completed payment
    return record_payment(db, order, payment["amount"], payment["method"], actor_id,
                          provider_ref=provider_ref or payment["provider_ref"], purpose=payment["purpose"])


# Check that a payment confirmation really came from Razorpay: Razorpay signs
# "order_id|payment_id" with our secret key (HMAC-SHA256); we recompute and compare.
def verify_razorpay_signature(db, razorpay_order_id, razorpay_payment_id, signature):
    import hashlib
    import hmac
    secret = (db.setting("razorpay_key_secret") or "").encode()
    expected = hmac.new(secret, ("%s|%s" % (razorpay_order_id, razorpay_payment_id)).encode(), hashlib.sha256).hexdigest()
    return bool(secret) and hmac.compare_digest(expected, signature or "")
