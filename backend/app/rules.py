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


# ------------------------------------------------------- request input
# Request bodies are plain JSON, so a field can arrive as any type. These turn a
# field into the type the code expects, or stop the request with a clear 400
# (RuleError) instead of crashing with a 500 on input like {"name": 5} or {"amount": "abc"}.
def text(v):
    """A text field: numbers become text; lists, objects, true/false and null count as empty."""
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return str(v)
    return ""


def as_float(v, what="amount", default=0.0):
    """A number field ("" / null = default). Refuses text, true/false, NaN and infinity."""
    if v is None or v == "":
        return default
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        raise RuleError("%s must be a number." % what.capitalize())
    try:
        f = float(v)
    except ValueError:
        raise RuleError("%s must be a number." % what.capitalize())
    if f != f or abs(f) > 1e15:   # NaN, infinity or absurdly large (SQLite can't store it as a whole number)
        raise RuleError("%s must be a number." % what.capitalize())
    return f


def as_local_datetime(v, what="date"):
    """An appointment time ("YYYY-MM-DD HH:MM[:SS]" or with a T), stored as local "YYYY-MM-DD HH:MM:SS"."""
    try:
        return datetime.fromisoformat(text(v).strip().replace(" ", "T")[:19]).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise RuleError("Enter a valid %s and time." % what)


def as_list(v, of=None):
    """A list field (quote lines, technicians). null = empty; anything that isn't a list is
    refused. of=dict also refuses items that aren't objects (each line is {"id": .., "qty": ..})."""
    if v is None or v == "":
        return []
    if not isinstance(v, list) or (of and not all(isinstance(x, of) for x in v)):
        raise RuleError("The list sent is not in the expected format.")
    return v


def as_int(v, what="id", default=0):
    """A whole-number field such as a record id ("" / null = default)."""
    f = as_float(v, what, default)
    if f != int(f):
        raise RuleError("%s must be a whole number." % what.capitalize())
    return int(f)


# ------------------------------------------------------------------ helpers
# Rules of thumb for India: 1 kW of panels makes ~120 units (kWh) a month;
# electricity costs ~₹8 per unit; an installed system costs ~₹65,000 per kW;
# ~100 sq ft of shadow-free roof per kW. Packages are 1 to 5 kW.
UNITS_PER_KW_MONTH = 120.0
AVG_TARIFF_INR = 8.0
COST_PER_KW_INR = 65000.0
ROOF_SQFT_PER_KW = 100.0
MIN_KW, MAX_KW = 1, 10        # household rooftop sizes the estimator recommends
FALLBACK_KWH_PER_KW = 1450.0

# Each status list is [(stored value, label shown to people), ...].
LEAD_STAGES = [("new", "New"), ("contacted", "Contacted"), ("survey", "Survey"),
               ("quoted", "Quoted"), ("won", "Won"), ("lost", "Lost")]
SURVEY_STATES = [("scheduled", "Scheduled"), ("done", "Visited"), ("approved", "Approved"),
                 ("rejected", "Rejected")]
ORDER_STATES = [("draft", "Draft quote"), ("sent", "Quote sent"), ("sale", "Confirmed"),
                ("cancel", "Cancelled")]
DELIVERY_STATES = [("waiting", "Waiting for advance"), ("ready", "Ready to pack"), ("packed", "Packed"),
                   ("done", "Shipped"), ("delivered", "Delivered")]
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
def is_active_role(db, user_id, roles):
    """True if `user_id` is an active user with one of `roles` (for assignment pickers)."""
    marks = ",".join("?" for _ in roles)
    return bool(user_id) and bool(db.val("SELECT COUNT(*) FROM users WHERE id = ? AND active = 1 AND role IN (%s)" % marks,
                                         as_int(user_id), *roles))


def claim(db, table, rid, from_states, to_state):
    """Move a record to `to_state` only if it is still in one of `from_states`; True if this
    request won. Two clicks (or two people) at once can't both act on the same record:
    SQLite lets one write at a time, so the second sees the new state and gets False."""
    marks = ",".join("?" for _ in from_states)
    cur = db.exec("UPDATE %s SET state = ? WHERE id = ? AND state IN (%s)" % (table, marks), to_state, rid, *from_states)
    return cur.rowcount == 1


def lead_state(db, order):
    """The customer's state for an order (sets the subsidy rate), if known."""
    if order.get("lead_id"):
        st = db.val("SELECT state FROM leads WHERE id = ?", order["lead_id"])
        if st:
            return st
    return db.val("SELECT state FROM customers WHERE id = ?", order["customer_id"])


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
OFF_GRID_BATTERY_PER_KW = 28000   # 2 x 150 Ah batteries per kW (catalogue price), off-grid only


def normalize_phone(raw):
    """Indian mobile number as +91XXXXXXXXXX, or None if it isn't one.
    Accepts spaces, dashes, a leading 0, 91 or +91."""
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] not in "6789":
        return None
    return "+91" + digits


def estimate(units=0.0, bill=0.0, state=None, include_topup=False, kw=None, cost_per_kw=None, tariff=None,
             system_type="on_grid"):
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
    off_grid = system_type == "off_grid"
    cost = kw * (cost_per_kw + (OFF_GRID_BATTERY_PER_KW if off_grid else 0))
    sub = subsidy_for(kw, state, include_topup)
    if off_grid:  # PM Surya Ghar covers grid-connected rooftop systems only
        sub = dict(sub, central=0, topup=0, total=0)
    net = max(cost - sub["total"], 0)
    return {"units": round(units), "kw": kw, "system_type": "off_grid" if off_grid else "on_grid",
            "generation": round(generation),
            "monthly_saving": round(monthly_saving), "yearly_saving": round(monthly_saving * 12),
            "cost": round(cost), "subsidy": sub["total"], "subsidy_central": sub["central"],
            "subsidy_topup": sub["topup"], "topup_available": sub["topup_available"],
            "state": sub["state"], "category": sub["category"], "net_cost": round(net),
            "cost_per_kw": round(cost_per_kw), "tariff": tariff, "custom": custom,
            "coverage": round(min(generation / units, 1) * 100) if units else 100,
            "payback_years": round(net / (monthly_saving * 12), 1) if monthly_saving else 0,
            "roof_sqft": round(kw * ROOF_SQFT_PER_KW)}


# --------------------------------------------------------------- customers
# Find a customer by email (then by phone); create one if none exists.
# Fills in missing phone/address on an existing customer. Returns the customer id.
def ensure_customer(db, name, email=None, phone=None, street=None, city=None):
    email = text(email).strip().lower() or None
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
    name = text(vals.get("contact_name")).strip()
    if not name or not text(vals.get("phone")).strip():
        raise RuleError("Please enter the customer's name and phone number.")
    data = {k: vals.get(k) for k in ("contact_name", "phone", "email", "street", "city", "requested_kw",
                                     "system_type", "subsidy_requested", "monthly_bill", "monthly_units", "state",
                                     "roof_area_sqft", "notes", "discom", "consumer_no", "preferred_date",
                                     "preferred_slot") if vals.get(k) is not None}
    data.update({"channel": channel, "stage": "new", "customer_id": customer_id,
                 "salesperson_id": vals.get("salesperson_id") or pick_salesperson(db),
                 "next_action": "Call within 2 hours: screen roof, bill and grid",
                 "next_action_due": today(), "created_at": now()})
    data["system_type"] = "off_grid" if data.get("system_type") == "off_grid" else "on_grid"
    data["subsidy_requested"] = 1 if data.get("subsidy_requested") else 0
    data["ref"] = db.next_ref("lead", "ENQ-")
    lid = db.insert("leads", data)
    db.update("leads", lid, {"project_ref": project_ref(data["created_at"], lid)})
    db.note("lead", lid, "Enquiry received (%s)." % channel, actor_id)
    return lid


# Phone screening is complete when we know the roof area, the bill or units, and the grid is suitable.
SURVEY_SLOTS = [("morning", "Morning (9am–12pm)"), ("afternoon", "Afternoon (12–3pm)"), ("evening", "Evening (3–6pm)")]


def check_preferred_visit(day, slot):
    """(date, slot) for a survey request, or RuleError. Day: tomorrow up to 30 days ahead."""
    if not day and not slot:
        return None, None
    try:
        d = date.fromisoformat(str(day)[:10])
    except (TypeError, ValueError):
        raise RuleError("Choose the day you'd like the survey.")
    if not date.today() < d <= date.today() + timedelta(days=30):
        raise RuleError("Choose a day between tomorrow and 30 days from now.")
    if slot not in dict(SURVEY_SLOTS):
        raise RuleError("Choose a time slot.")
    return d.isoformat(), slot


def project_ref(created_at, lead_id):
    """One ID for the customer's whole journey (enquiry, survey, quote, order, job, warranty, repairs)."""
    return "SP-%s-%05d" % (str(created_at)[2:4], lead_id)


SLOT_TIMES = {"morning": "10:00:00", "afternoon": "13:00:00", "evening": "16:00:00"}


def slot_of(survey_date):
    """morning / afternoon / evening for a visit time."""
    hour = (parse_dt(survey_date) or datetime(2000, 1, 1, 10)).hour
    return "morning" if hour < 12 else "afternoon" if hour < 15 else "evening"


def in_area(tech, city, state):
    """True if the technician covers this city or state (service area: comma-separated names)."""
    areas = [a.strip().lower() for a in (tech.get("service_area") or "").split(",") if a.strip()]
    return bool(areas) and any(a in ((city or "").lower(), (state or "").lower()) for a in areas)


def suggest_technicians(db, lead, day=None, slot=None, skip_survey=0):
    """Technicians for a survey or job, best first: covers the area, free in that slot, fewest open visits.
    skip_survey: the survey being rescheduled (it doesn't make its own technician busy)."""
    out = []
    for t in db.q("SELECT id, name, service_area FROM users WHERE role = 'technician' AND active = 1 ORDER BY name"):
        busy = []
        if day:
            for s in db.q("SELECT survey_date FROM surveys WHERE technician_id = ? AND state = 'scheduled' "
                          "AND substr(survey_date, 1, 10) = ? AND id != ?", t["id"], day, skip_survey or 0):
                if not slot or slot_of(s["survey_date"]) == slot:
                    busy.append("survey")
            if db.val("SELECT COUNT(*) FROM jobs j JOIN job_techs jt ON jt.job_id = j.id WHERE jt.user_id = ? "
                      "AND j.state != 'done' AND substr(j.scheduled_at, 1, 10) = ?", t["id"], day):
                busy.append("installation")
        load = (db.val("SELECT COUNT(*) FROM surveys WHERE technician_id = ? AND state = 'scheduled'", t["id"]) +
                db.val("SELECT COUNT(*) FROM jobs j JOIN job_techs jt ON jt.job_id = j.id WHERE jt.user_id = ? AND j.state != 'done'", t["id"]))
        out.append({"id": t["id"], "name": t["name"], "service_area": t["service_area"] or "",
                    "in_area": in_area(t, lead.get("city"), lead.get("state")), "busy": busy, "open_work": load})
    out.sort(key=lambda t: (not t["in_area"], bool(t["busy"]), t["open_work"], t["name"]))
    return out


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
def visit_time(survey_date, slot=None, allow_past=False):
    """The visit's local date-time from a day + slot (booking form) or a full date-time. Not in the past."""
    if survey_date and len(str(survey_date)) <= 10:   # a day + slot (from the booking form)
        if slot not in SLOT_TIMES:
            raise RuleError("Choose a time slot.")
        survey_date = "%s %s" % (str(survey_date)[:10], SLOT_TIMES[slot])
    when = parse_dt(survey_date)
    if not when:
        raise RuleError("Choose the day and time slot for the visit.")
    if when.date() < date.today() and not allow_past:   # allow_past: demo history only
        raise RuleError("The visit can't be in the past.")
    return when


# Move a booked (not yet visited) survey to another day / slot and/or another technician.
# The visit simply changes owner: it leaves the old technician's dashboard and appears on the new one's.
def reschedule_survey(db, survey, technician_id, survey_date, slot, actor_id):
    if survey["state"] != "scheduled":
        raise RuleError("Only a booked visit that hasn't happened yet can be rescheduled.")
    lead = db.get("leads", survey["lead_id"]) if survey["lead_id"] else None
    if lead and lead["stage"] in ("won", "lost"):
        raise RuleError("This enquiry is closed.")
    new_date = visit_time(survey_date, slot).strftime("%Y-%m-%d %H:%M:%S")
    if not technician_id or not is_active_role(db, technician_id, ("technician",)):
        raise RuleError("Choose an active technician for the visit.")
    technician_id = as_int(technician_id)
    if new_date == survey["survey_date"] and technician_id == survey["technician_id"]:
        raise RuleError("Pick a different day, time slot or technician.")
    old_tech = db.val("SELECT name FROM users WHERE id = ?", survey["technician_id"]) or "no technician"
    new_tech = db.val("SELECT name FROM users WHERE id = ?", technician_id)
    db.update("surveys", survey["id"], {"survey_date": new_date, "technician_id": technician_id})
    fmt = lambda v: parse_dt(v).strftime("%d %b %Y, %H:%M") if parse_dt(v) else "no date"
    msg = "Visit rescheduled to %s with %s (was %s with %s)." % (fmt(new_date), new_tech, fmt(survey["survey_date"]), old_tech)
    db.note("survey", survey["id"], msg, actor_id)
    if lead:
        db.note("lead", lead["id"], msg, actor_id)


def schedule_survey(db, lead, technician_id, survey_date, actor_id, slot=None, allow_past=False):
    """Sales has called the customer: confirm the booking (day + slot) and assign the technician.
    The visit can be booked on the call; screening details can be completed later by the technician."""
    if lead["stage"] in ("won", "lost"):
        raise RuleError("This enquiry is closed.")
    if lead["grid_suitable"] == "no":
        raise RuleError("The grid connection was marked unsuitable. Change it if that was a mistake.")
    when = visit_time(survey_date, slot, allow_past)
    survey_date = when.strftime("%Y-%m-%d %H:%M:%S")
    if not technician_id:
        raise RuleError("Choose the technician who will visit.")
    if not is_active_role(db, technician_id, ("technician",)):
        raise RuleError("Choose an active technician for the visit.")
    sid = db.insert("surveys", {
        "ref": db.next_ref("survey", "SRV-"), "lead_id": lead["id"], "technician_id": technician_id,
        "survey_date": survey_date, "state": "scheduled",
        "recommended_kw": lead["requested_kw"] or lead_recommended_kw(lead),
        "usable_area_sqft": lead["roof_area_sqft"], "created_at": now()})
    db.update("leads", lead["id"], {"booking_confirmed_at": now(),
                                    "stage": "survey" if lead["stage"] in ("new", "contacted") else lead["stage"],
                                    "next_action": None, "next_action_due": None})
    tech = db.get("users", technician_id)
    db.note("lead", lead["id"], "Booking confirmed with the customer: roof survey on %s, technician %s." % (
        when.strftime("%d %b %Y, %H:%M"), tech["name"]), actor_id)
    return sid


# Technician (or Sales) marks the visit done; needs at least the roof direction and area.
# ------------------------------------------------------------ site survey form
# key: (section, kind, options or (min, max), required). Kinds: choice, multi, num, bool, text.
# Contact details, address, bill and consumer number already live on the enquiry, so they're not repeated.
SURVEY_FIELDS_SPEC = {
    # 1 Roof
    "property_type": ("roof", "choice", ["house", "apartment", "commercial", "industrial"], True),
    "ownership": ("roof", "choice", ["owned", "rented", "society"], True),
    "roof_condition": ("roof", "choice", ["good", "average", "poor"], True),
    "roof_azimuth_deg": ("roof", "num", (0, 360), False),   # exact facing, degrees from north (90 = east, 180 = south)
    "roof_length_m": ("roof", "num", (0, 500), False),
    "roof_width_m": ("roof", "num", (0, 500), False),
    "roof_height_m": ("roof", "num", (0, 200), True),
    "parapet_height_m": ("roof", "num", (0, 5), False),
    "roof_defects": ("roof", "multi", ["cracks", "leakage", "dampness", "water_stagnation", "rusted_sheets", "loose_tiles"], False),
    "obstacles": ("roof", "multi", ["water_tank", "staircase_room", "ac_units", "dish_antenna", "solar_heater", "chimney", "skylight"], False),
    # 2 Shade
    "shade_morning": ("shade", "bool", None, False),
    "shade_midday": ("shade", "bool", None, False),
    "shade_afternoon": ("shade", "bool", None, False),
    "shade_sources": ("shade", "multi", ["trees", "buildings", "water_tank", "walls", "poles", "towers"], False),
    "future_shading": ("shade", "bool", None, False),
    # 3 Electrical
    "discom": ("electrical", "text", 80, False),
    "consumer_no": ("electrical", "text", 40, False),
    "phase": ("electrical", "choice", ["single", "three"], True),
    "sanctioned_load_kw": ("electrical", "num", (0, 1000), True),
    "meter_type": ("electrical", "choice", ["digital", "smart", "prepaid", "electromechanical"], False),
    "net_meter_space": ("electrical", "bool", None, True),
    "db_condition": ("electrical", "choice", ["good", "needs_upgrade"], True),
    "db_spare_way": ("electrical", "bool", None, True),
    "existing_earth_pits": ("electrical", "num", (0, 20), False),
    "earth_resistance_ohm": ("electrical", "num", (0, 1000), False),
    "lightning_protection": ("electrical", "bool", None, False),
    "existing_equipment": ("electrical", "multi", ["home_inverter_ups", "generator", "existing_solar", "ev_charger", "solar_water_heater"], False),
    # 4 Cabling & mounting (these become parts on the quote)
    "inverter_location": ("cabling", "choice", ["indoor_wall", "outdoor_wall", "utility_room"], True),
    "inverter_conditions_ok": ("cabling", "bool", None, False),
    "internet": ("cabling", "choice", ["wifi", "mobile", "ethernet", "none"], False),
    "dc_cable_m": ("cabling", "num", (1, 300), True),
    "ac_cable_m": ("cabling", "num", (1, 300), True),
    "earth_cable_m": ("cabling", "num", (1, 300), True),
    "conduit_needed": ("cabling", "bool", None, False),
    "mounting_type": ("cabling", "choice", ["rcc_anchored", "ballasted", "metal_clamp", "elevated"], True),
    "structure_height_m": ("cabling", "num", (0, 10), False),
    "wind_exposure": ("cabling", "choice", ["low", "medium", "high"], False),
    "waterproofing_needed": ("cabling", "bool", None, False),
    # 5 Battery (off-grid only)
    "backup_hours": ("battery", "num", (0, 48), False),
    "essential_load_w": ("battery", "num", (0, 50000), False),
    "battery_location_ok": ("battery", "bool", None, False),
    # 6 Site & safety
    "access": ("site", "choice", ["stairs", "ladder", "lift", "crane_needed"], True),
    "material_route_ok": ("site", "bool", None, False),
    "hazards": ("site", "multi", ["no_edge_protection", "fragile_roof", "overhead_lines", "slippery_surface"], False),
    "dust": ("site", "choice", ["low", "medium", "high"], False),
    "corrosion_risk": ("site", "choice", ["low", "medium", "high"], False),
    "monkey_bird_activity": ("site", "bool", None, False),
    # 8 Summary
    "structural_review": ("summary", "bool", None, False),
    "civil_work": ("summary", "bool", None, False),
    "electrical_work": ("summary", "bool", None, False),
    "customer_present": ("summary", "bool", None, False),
    "declaration": ("summary", "bool", None, True),
}
SURVEY_SECTIONS = [("roof", "Roof"), ("shade", "Shade"), ("electrical", "Electrical"), ("cabling", "Cabling & mounting"),
                   ("battery", "Battery"), ("site", "Site & safety"), ("summary", "Issues & summary")]
# Photos are taken while filling the section they prove: (category, label, required, section).
SURVEY_PHOTOS = [("roof", "Whole roof", True, "roof"), ("shadow_free", "Shadow-free area", True, "roof"),
                 ("meter", "Meter + nameplate", True, "electrical"), ("db", "Distribution board", True, "electrical"),
                 ("earthing", "Earth pit", False, "electrical"), ("inverter_spot", "Inverter location", True, "cabling"),
                 ("cable_route", "Cable route", False, "cabling"), ("access", "Roof access", False, "site"),
                 ("issue", "Problem found", False, "summary")]
ISSUE_TYPES = ["weak_structure", "insufficient_area", "heavy_shading", "roof_damage", "no_inverter_spot", "electrical_upgrade",
               "no_earthing", "cable_route", "meter_incompatible", "no_permission", "missing_documents", "unsafe_access", "other"]
SURVEY_RESULTS = [("feasible", "Feasible"), ("conditional", "Feasible with conditions"), ("not_feasible", "Not feasible")]


def survey_details(survey):
    try:
        return json.loads(survey.get("details") or "{}")
    except (TypeError, ValueError):
        return {}


def clean_survey_details(raw, old):
    """Keep only known fields with valid values; issues are a short list of typed rows."""
    out = dict(old)
    for key, (_sec, kind, opts, _req) in SURVEY_FIELDS_SPEC.items():
        if key not in raw:
            continue
        v = raw[key]
        if v in (None, ""):
            out.pop(key, None)
            continue
        if kind == "choice":
            if v not in opts:
                raise RuleError("Choose a valid option for %s." % _field_label(key))
        elif kind == "multi":
            if not isinstance(v, list) or any(x not in opts for x in v):
                raise RuleError("Invalid choices for %s." % _field_label(key))
        elif kind == "num":
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise RuleError("%s must be a number." % _field_label(key))
            if v != v or not opts[0] <= v <= opts[1]:
                raise RuleError("%s must be between %g and %g." % (_field_label(key), opts[0], opts[1]))
        elif kind == "bool":
            v = bool(v)
        elif kind == "text":
            v = str(v).strip()[:opts]
        out[key] = v
    if "issues" in raw:
        issues = []
        for i in (raw.get("issues") or [])[:20]:
            if not isinstance(i, dict) or i.get("type") not in ISSUE_TYPES or i.get("severity") not in ("critical", "high", "medium", "low"):
                raise RuleError("Each problem needs a type and a severity.")
            issues.append({"type": i["type"], "severity": i["severity"], "note": str(i.get("note") or "").strip()[:300]})
        out["issues"] = issues
    return out


# Names as the technician sees them on the form (anything not listed is spelled out from its key).
FIELD_LABELS = {"roof_height_m": "Height from ground (m)", "dc_cable_m": "DC cable run (m)", "ac_cable_m": "AC cable run (m)",
                "earth_cable_m": "Earthing run (m)", "earth_resistance_ohm": "Earth resistance (ohm)",
                "roof_azimuth_deg": "Facing (degrees)", "backup_hours": "Backup needed (hours)",
                "essential_load_w": "Essential load (W)", "phase": "Supply", "db_condition": "Distribution board",
                "db_spare_way": "Spare way in DB", "access": "Roof access", "property_type": "Property"}


def _field_label(key):
    """roof_height_m -> "Height from ground (m)" for messages."""
    if key in FIELD_LABELS:
        return FIELD_LABELS[key]
    for suf, unit in (("_m", " (m)"), ("_kw", " (kW)"), ("_ohm", " (ohm)"), ("_w", " (W)")):
        if key.endswith(suf):
            return key[:-len(suf)].replace("_", " ").capitalize() + unit
    return key.replace("_", " ").capitalize()


def survey_missing(db, survey, system_type=None):
    """What still has to be filled in before the visit can be submitted: [(section, label, key)]."""
    d = survey_details(survey)
    missing = []
    for col, label in (("roof_type", "Roof type"), ("roof_direction", "Roof facing"), ("usable_area_sqft", "Shadow-free area"),
                       ("recommended_kw", "Recommended kW")):
        if not survey.get(col):
            missing.append(("roof" if col != "recommended_kw" else "summary", label, col))
    for key, (sec, kind, _o, req) in SURVEY_FIELDS_SPEC.items():
        if req and (key not in d or (kind == "bool" and sec == "summary" and not d[key])):
            missing.append((sec, _field_label(key), key))
    if (system_type or "") == "off_grid":
        for key in ("backup_hours", "essential_load_w"):
            if key not in d:
                missing.append(("battery", _field_label(key), key))
    have = {r["note"] for r in db.q("SELECT note FROM attachments WHERE owner_type = 'survey' AND owner_id = ?", survey["id"])}
    for cat, label, req, sec in SURVEY_PHOTOS:
        if req and cat not in have:
            missing.append((sec, "Photo: %s" % label, "photo_" + cat))
    if not survey.get("result"):
        missing.append(("summary", "Survey result", "result"))
    return missing


def survey_parts(db, survey, kit):
    """Extra parts this roof needs beyond the standard package: [(product, qty, reason)].
    Cable runs measured on site replace the package's standard lengths when they are longer."""
    d = survey_details(survey)
    if not d:
        return []
    std = {r["code"]: r["qty"] for r in db.q("SELECT p.code, kl.qty FROM kit_lines kl JOIN products p ON p.id = kl.product_id "
                                            "WHERE kl.kit_id = ?", kit["id"])}
    out = []

    def add(code, qty, reason):
        p = db.one("SELECT * FROM products WHERE code = ? AND active = 1", code)
        qty = round(qty)
        if p and qty > 0:
            out.append((p, qty, reason))
    if d.get("dc_cable_m"):   # + and − runs, 10% slack
        add("CBL-DC4", d["dc_cable_m"] * 2 * 1.1 - std.get("CBL-DC4", 0), "DC run %g m" % d["dc_cable_m"])
    if d.get("ac_cable_m"):
        add("CBL-AC4", d["ac_cable_m"] * 1.1 - std.get("CBL-AC4", 0), "AC run %g m" % d["ac_cable_m"])
    if d.get("earth_cable_m"):
        add("ERT-CBL", d["earth_cable_m"] * 1.1, "earthing run %g m" % d["earth_cable_m"])
    if d.get("conduit_needed"):
        add("CND-25", ((d.get("dc_cable_m") or 0) + (d.get("ac_cable_m") or 0)) * 1.1, "conduit along cable routes")
    if d.get("mounting_type") == "elevated":
        add("STR-ELV", kit["kw"], "elevated structure%s" % (" %g m" % d["structure_height_m"] if d.get("structure_height_m") else ""))
    if d.get("mounting_type") == "metal_clamp":
        add("CLMP-MTL", kit["kw"], "metal-sheet roof")
    if d.get("waterproofing_needed") or d.get("mounting_type") == "rcc_anchored":
        add("WPF-KIT", 1, "anchors on RCC roof")
    return out


def check_survey_size(db, survey, system_type=None):
    """The recommended size must be one we sell and must fit the shadow-free area (about 100 sq ft per kW)."""
    kw = survey.get("recommended_kw") or 0
    area = survey.get("usable_area_sqft") or 0
    if area and area < 100:
        raise RuleError("The shadow-free area is only %g sq ft, too small for our smallest (1 kW) system, which needs "
                        "about 100 sq ft. Re-measure the roof, or set the survey result to Not feasible." % area)
    from .catalog import MAX_PACKAGE_KW, ensure_package
    if not 1 <= kw <= MAX_PACKAGE_KW:
        raise RuleError("This survey recommends %g kW. We quote rooftop systems from 1 to %d kW. Change Recommended size "
                        "(Issues & summary tab)." % (kw, MAX_PACKAGE_KW))
    if not ensure_package(db, kw, system_type):   # sizes without a package yet get one, built from the same parts
        raise RuleError("No package could be prepared for %g kW." % kw)
    if area and kw > area / 100.0 + 0.01:
        raise RuleError("The shadow-free area (%g sq ft) fits about %g kW, not %g kW. Lower Recommended size "
                        "or re-measure the roof." % (area, round(area / 100.0, 1), kw))


def survey_mark_done(db, survey, actor_id, strict=False):
    """strict (the technician's Submit): every required field and photo must be in."""
    if survey["state"] != "scheduled":
        raise RuleError("Only scheduled surveys can be marked visited.")
    if not (survey["roof_direction"] and survey["usable_area_sqft"]):
        raise RuleError("Record at least the roof direction and shadow-free area first.")
    if strict:
        lead = db.get("leads", survey["lead_id"]) or {}
        missing = survey_missing(db, survey, lead.get("system_type"))
        if missing:
            raise RuleError("Still to fill in: %s." % ", ".join(m[1] for m in missing[:8]) + (" …" if len(missing) > 8 else ""))
        if survey.get("result") != "not_feasible":
            check_survey_size(db, survey, lead.get("system_type"))
        if survey.get("result") == "not_feasible":
            db.update("surveys", survey["id"], {"state": "done"})
            db.note("survey", survey["id"], "Site visited: NOT feasible. Sales to contact the customer.", actor_id)
            return
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
def quote_from_survey(db, survey, actor, strict=False):
    """The technician (or Sales) turns a visited survey into the customer's quote. Building the
    quote approves the survey's recommended size; prices come from the catalogue."""
    if survey.get("result") == "not_feasible":
        raise RuleError("The survey says the site is not feasible, so no quote can be built. Submit the visit instead.")
    if survey["state"] == "scheduled":
        survey_mark_done(db, survey, actor["id"], strict=strict)
        survey = db.get("surveys", survey["id"])
    if survey["state"] not in ("done", "approved"):
        raise RuleError("Only a visited survey can be quoted.")
    if not survey["recommended_kw"]:
        raise RuleError("Set the recommended system size (kW) first.")
    check_survey_size(db, survey, db.val("SELECT system_type FROM leads WHERE id = ?", survey["lead_id"]))
    if db.val("SELECT COUNT(*) FROM orders WHERE lead_id = ? AND state != 'cancel'", survey["lead_id"]):
        raise RuleError("This customer already has a quotation. Open it from the enquiry.")
    if survey["state"] == "done":
        db.update("surveys", survey["id"], {"state": "approved"})
        db.update("leads", survey["lead_id"], {"requested_kw": survey["recommended_kw"]})
        db.note("survey", survey["id"], "Survey completed and quoted (%s kW)." % survey["recommended_kw"], actor["id"])
    oid = create_quote(db, db.get("leads", survey["lead_id"]), actor["id"])
    db.update("orders", oid, {"created_by": actor["id"]})
    send_quote(db, db.get("orders", oid), actor["id"])   # straight to the customer for confirmation
    return oid


def discount_needs_approval(db, order):
    """True if a line discount is above the limit and nobody has approved it yet."""
    limit = float(db.setting("discount_approval_pct", 5) or 5)
    big = db.val("SELECT MAX(discount) FROM order_lines WHERE order_id = ?", order["id"]) or 0
    return big > limit and order.get("approval_state") != "approved"


def full_discount_pct(db):
    return float(db.setting("full_upfront_discount_pct", 2) or 0)


def full_upfront_amount(db, order):
    """What the customer pays to settle the whole order upfront (with the upfront discount)."""
    return r2(order["amount_total"] * (1 - full_discount_pct(db) / 100.0))


def apply_full_discount(db, order, actor_id=None):
    """Add the 'paid in full upfront' discount line once, so the order total equals what was paid."""
    pct = full_discount_pct(db)
    if not pct or db.val("SELECT COUNT(*) FROM order_lines WHERE order_id = ? AND description LIKE 'Paid in full upfront%'", order["id"]):
        return
    untaxed, total = order["amount_untaxed"], order["amount_total"]
    rate = round((total - untaxed) / untaxed * 100, 4) if untaxed else 0
    db.insert("order_lines", {"order_id": order["id"], "description": "Paid in full upfront: %g%% off" % pct, "qty": 1,
                              "price_unit": -r2(untaxed * pct / 100.0), "tax_rate": rate})
    recompute_order(db, order["id"])
    db.note("order", order["id"], "Paid in full upfront: %g%% discount applied." % pct, actor_id)


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
    for part, qty, reason in survey_parts(db, survey, kit):   # what this particular roof needs on top
        db.insert("order_lines", {"order_id": oid, "product_id": part["id"], "description": "%s (site: %s)" % (part["name"], reason),
                                  "qty": qty, "price_unit": part["price"], "tax_rate": part["tax_rate"]})
    recompute_order(db, oid)
    db.update("leads", lead["id"], {"stage": "quoted"})
    db.note("lead", lead["id"], "Quotation prepared.", actor_id)
    db.note("order", oid, "Quotation prepared from the %s package." % kit["name"], actor_id)
    return oid


# Yearly generation and payback for an order: asks PVGIS (a free EU solar calculator)
# for the surveyed roof; if that fails (no internet), uses 1450 kWh per kW per year.
# httpx is the HTTP client library used to call other websites.
def _pvgis_aspect(survey, by_direction):
    """PVGIS wants 0 = south, -90 = east, 90 = west. Use the measured angle when the survey has one."""
    az = survey_details(survey or {}).get("roof_azimuth_deg") if survey else None
    if az is not None:
        return round(float(az) % 360 - 180)
    return by_direction.get((survey or {}).get("roof_direction") or "S", 0)


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
            "aspect": _pvgis_aspect(survey, aspect), "outputformat": "json"})
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
def check_quote_lines(db, order):
    if db.val("SELECT COUNT(*) FROM order_lines WHERE order_id = ? AND qty <= 0", order["id"]):
        raise RuleError("Every line needs a quantity above zero.")
    if (order["amount_total"] or 0) <= 0:
        raise RuleError("The quotation total is zero. Add the package before sending or confirming.")


def send_quote(db, order, actor_id):
    if order["state"] not in ("draft", "sent"):
        raise RuleError("Only quotations can be sent.")
    check_quote_lines(db, order)
    if discount_needs_approval(db, order):
        db.update("orders", order["id"], {"approval_state": "pending"})
        raise RuleError("The discount is above %s%%, so Sales or Admin must approve it before the quote goes to the customer. "
                        "It's now waiting for approval." % db.setting("discount_approval_pct", 5))
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
    check_quote_lines(db, order)
    if not claim(db, "orders", order["id"], ("draft", "sent"), "sale"):
        raise RuleError("This order was just confirmed by someone else.")
    data = {"state": "sale", "confirmed_at": now()}
    if accepted_by:
        data.update({"accepted_by": accepted_by, "accepted_at": now()})
    db.update("orders", order["id"], data)
    order = db.get("orders", order["id"])
    cust = db.get("customers", order["customer_id"])
    # delivery order for the warehouse (kit exploded into components)
    did = db.insert("deliveries", {"ref": db.next_ref("delivery", "DEL-"), "order_id": order["id"],
                                   "state": "waiting", "created_at": now()})
    for pid, qty in order_components(db, order["id"]):
        db.insert("delivery_lines", {"delivery_id": did, "product_id": pid, "qty": qty})
    # installation job on the crew schedule
    when = None   # installation date: pending until Sales schedules it (schedule_installation)
    label_type = "On-Grid" if order["system_type"] == "on_grid" else "Off-Grid"
    jid = db.insert("jobs", {"ref": db.next_ref("job", "JOB-"), "order_id": order["id"],
                             "customer_id": order["customer_id"], "kw_planned": order["kw"],
                             "scheduled_at": when, "state": "planned", "created_at": now(),
                             "notes": "Install %g kW %s – %s" % (order["kw"], label_type, cust["name"])})
    surveyor = db.val("SELECT technician_id FROM surveys WHERE id = ?", order["survey_id"]) if order["survey_id"] else None
    if surveyor and is_active_role(db, surveyor, ("technician",)):   # the technician who surveyed the roof installs it
        db.insert("job_techs", {"job_id": jid, "user_id": surveyor})
    # subsidy paperwork
    lead = db.get("leads", order["lead_id"]) if order["lead_id"] else None
    if lead and lead["subsidy_requested"] and order["system_type"] == "on_grid":  # PM Surya Ghar: grid-connected only
        db.insert("subsidies", {"ref": db.next_ref("subsidy", "SUB-"), "order_id": order["id"],
                                "customer_id": order["customer_id"], "kw": order["kw"],
                                "amount_expected": subsidy_expected(order["kw"], lead_state(db, order))})
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
    if order["state"] == "sale" and db.val("SELECT COUNT(*) FROM deliveries WHERE order_id = ? AND state IN ('done', 'delivered')", order["id"]):
        raise RuleError("A dispatched order can't be cancelled.")
    if order["state"] == "cancel":
        raise RuleError("This order is already cancelled.")
    if db.val("SELECT COUNT(*) FROM jobs WHERE order_id = ? AND state != 'planned'", order["id"]):
        raise RuleError("The crew has already started this installation, so it can't be cancelled here.")
    db.update("orders", order["id"], {"state": "cancel"})
    db.exec("DELETE FROM delivery_lines WHERE delivery_id IN (SELECT id FROM deliveries WHERE order_id = ? AND state NOT IN ('done', 'delivered'))", order["id"])
    db.exec("DELETE FROM deliveries WHERE order_id = ? AND state NOT IN ('done', 'delivered')", order["id"])
    db.exec("DELETE FROM job_techs WHERE job_id IN (SELECT id FROM jobs WHERE order_id = ? AND state = 'planned')", order["id"])
    db.exec("DELETE FROM jobs WHERE order_id = ? AND state = 'planned'", order["id"])
    db.exec("UPDATE subsidies SET state = 'rejected' WHERE order_id = ? AND state NOT IN ('disbursed', 'rejected')", order["id"])
    if order["lead_id"]:
        if order["state"] == "sale":   # a confirmed order was cancelled: the sale is lost
            db.exec("UPDATE leads SET stage = 'lost', lost_reason = 'Order cancelled' WHERE id = ?", order["lead_id"])
        elif not db.val("SELECT COUNT(*) FROM orders WHERE lead_id = ? AND state != 'cancel'", order["lead_id"]):
            # only a quotation was withdrawn: the enquiry goes back to "survey done", ready for a new quote
            db.exec("UPDATE leads SET stage = 'survey' WHERE id = ? AND stage = 'quoted'", order["lead_id"])
    paid = order_paid(db, order["id"])
    msg = "Order cancelled."
    if paid > 0:
        msg += " %s was received: arrange the refund, then void the payment(s)." % money(paid)
    db.note("order", order["id"], msg, actor_id)


# ---------------------------------------------------------- money: invoices
# Money received so far for an order (completed payments only).
def order_paid(db, order_id):
    return r2(db.val("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE order_id = ? AND state = 'done'", order_id))


# The advance required before dispatch: advance % (Settings) of the order total.
def advance_needed(db, order):
    pct = float(db.setting("advance_pct", 30) or 0)
    return r2(order["amount_total"] * pct / 100.0)


# How much of the advance is still missing (never below 0).
def payment_required(db):
    """Settings: payment_required. While "0" the payment step is skipped: the customer's acceptance
    confirms the order and the warehouse can ship without an advance."""
    return str(db.setting("payment_required", "0")) == "1"


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
    iid = db.insert("invoices", {"ref": db.next_ref("invoice", "INV-"), "order_id": order["id"],
                                 "customer_id": order["customer_id"], "kind": kind, "amount_untaxed": untaxed,
                                 "amount_tax": tax, "amount_total": r2(amount), "date": today()})
    return iid


def invoice_url(db, inv):
    """Link the customer opens (and can print / save as PDF). Order invoices carry the order's secret
    token so they open from an email; service invoices open from the signed-in portal."""
    token = db.val("SELECT access_token FROM orders WHERE id = ?", inv["order_id"]) if inv.get("order_id") else None
    return "/print/invoice/%s%s" % (inv["id"], "?token=%s" % token if token else "")


def email_invoice(db, iid, note=None):
    """Queue the invoice email to the customer (only when they have an email address)."""
    inv = db.get("invoices", iid)
    cust = db.get("customers", inv["customer_id"]) if inv else None
    if not cust or not cust.get("email"):
        return
    balance = r2(inv["amount_total"] - inv["amount_paid"])
    lines = ["Hi %s," % cust["name"],
             "Your %s %s for %s is ready." % (INVOICE_KIND.get(inv["kind"], "invoice").lower(), inv["ref"], money(inv["amount_total"])),
             ("It is fully paid. Thank you!" if balance <= 0.5 else "Amount still to pay: %s." % money(balance))]
    if note:
        lines.append(note)
    html = mailer.branded(db, "Invoice %s" % inv["ref"], lines, "View invoice", frontend(db) + invoice_url(db, inv))
    mailer.queue(db, cust["email"], "Invoice %s – %s" % (inv["ref"], db.setting("company_name") or "SunPower"), html)


INVOICE_KIND = {"advance": "Advance receipt", "final": "Tax invoice", "service": "Service invoice"}


# Invoice whatever part of the order hasn't been invoiced yet.
def final_invoice(db, order, actor_id):
    if order["state"] != "sale":
        raise RuleError("Only confirmed orders can be invoiced.")
    billed = r2(db.val("SELECT COALESCE(SUM(amount_total), 0) FROM invoices WHERE order_id = ? AND state != 'cancel' "
                       "AND kind != 'service'", order["id"]))
    rest = r2(order["amount_total"] - billed)
    if rest <= 0.5:
        raise RuleError("The full order value is already invoiced.")
    iid = create_invoice(db, order, "final", rest)
    allocate_payments(db, order["id"])
    email_invoice(db, iid, "You can pay the balance online from your SunPower account.")
    db.note("order", order["id"], "Final invoice %s issued for %s." % (
        db.val("SELECT ref FROM invoices WHERE id = ?", iid), money(rest)), actor_id)
    return iid


# Mark invoices paid using the money received, oldest invoice first.
def allocate_payments(db, order_id):
    """Spread the order's received money over its invoices, oldest first."""
    pool = order_paid(db, order_id)
    for inv in db.q("SELECT * FROM invoices WHERE order_id = ? AND state != 'cancel' AND kind != 'service' ORDER BY id",
                    order_id):
        paid = min(pool, inv["amount_total"])
        pool = r2(pool - paid)
        db.update("invoices", inv["id"], {"amount_paid": r2(paid),
                                          "state": "paid" if paid + 0.5 >= inv["amount_total"] else "posted"})


# Record money received for an order (cash, bank, UPI, online...).
# Creates an advance invoice if needed, and confirms a quotation automatically once the advance is paid.
def record_payment(db, order, amount, method, actor_id=None, provider_ref=None, purpose="advance", cap=True):
    """Money received for an order. A payment without an open invoice gets an
    advance invoice (marked paid). An online payment of the advance on a sent
    quotation confirms the order."""
    amount = r2(amount)
    if amount <= 0:
        raise RuleError("Enter an amount above zero.")
    if order["state"] == "cancel":
        raise RuleError("This order is cancelled.")
    was_due = advance_due(db, order) > 0 or order["state"] != "sale"  # remember: was the advance still missing before this payment?
    balance = r2(order["amount_total"] - order_paid(db, order["id"]))
    if cap and amount > balance + 1:   # staff typing an amount; online payments already happened at the bank
        raise RuleError("That's more than the %s still owed on %s." % (money(max(balance, 0)), order["ref"]))
    open_amount = r2(db.val("SELECT COALESCE(SUM(amount_total - amount_paid), 0) FROM invoices "
                            "WHERE order_id = ? AND state = 'posted' AND kind != 'service'", order["id"]))
    pid = db.insert("payments", {"ref": db.next_ref("payment", "PAY-"), "order_id": order["id"],
                                 "customer_id": order["customer_id"], "amount": amount, "method": method,
                                 "provider_ref": provider_ref, "state": "done", "purpose": purpose,
                                 "date": now(), "created_by": actor_id})
    if purpose == "full":   # paid everything upfront: the discount line makes the total match
        apply_full_discount(db, order, actor_id)
        order = db.get("orders", order["id"])
        open_amount = r2(db.val("SELECT COALESCE(SUM(amount_total - amount_paid), 0) FROM invoices "
                                "WHERE order_id = ? AND state = 'posted' AND kind != 'service'", order["id"]))
    new_invoice = None
    if amount > open_amount + 0.5:
        new_invoice = create_invoice(db, order, "advance" if purpose == "advance" else "final", r2(amount - open_amount))
    allocate_payments(db, order["id"])
    if new_invoice:
        email_invoice(db, new_invoice, "We received your payment of %s. Thank you!" % money(amount))
    else:   # paid an open invoice: send its updated copy
        last = db.val("SELECT id FROM invoices WHERE order_id = ? AND state != 'cancel' AND kind != 'service' ORDER BY id DESC LIMIT 1",
                      order["id"])
        if last:
            email_invoice(db, last, "We received your payment of %s. Thank you!" % money(amount))
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
    ready = advance_due(db, order) == 0 or not payment_required(db)
    db.exec("UPDATE deliveries SET state = ? WHERE order_id = ? AND state IN ('waiting', 'ready')",
            "ready" if ready else "waiting", order_id)


# -------------------------------------------------------------------- stock
# Add stock: serial-tracked items need one serial per unit; others just a quantity.
def receive_stock(db, product, qty, serials, actor_id, note=None):
    qty = as_float(qty, "quantity")
    names = [text(s).strip() for s in as_list(serials) if text(s).strip()]
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
    """Dispatch: advance paid (when payments are on), stock available, the unique serial / batch of
    every tracked unit. Warranties start later, when the installation is completed (job_finish)."""
    if delivery["state"] in ("done", "delivered"):
        raise RuleError("Already shipped.")
    order = db.get("orders", delivery["order_id"])
    if order["state"] != "sale":
        raise RuleError("%s is not a confirmed order." % order["ref"])
    if not claim(db, "deliveries", delivery["id"], ("waiting", "ready", "packed"), "done"):
        raise RuleError("This kit was just shipped by someone else.")
    due = advance_due(db, order) if payment_required(db) else 0
    if due > 0 and not (override and actor["role"] == "director"):  # only the Director may dispatch without the advance
        raise RuleError("%s cannot be dispatched yet: %s%% advance (%s) is required, %s received so far." % (
            order["ref"], db.setting("advance_pct"), money(advance_needed(db, order)), money(order_paid(db, order["id"]))))
    lines = db.q("SELECT dl.*, p.name, p.tracking, p.qty_on_hand, p.warranty_months, p.cost FROM delivery_lines dl "
                 "JOIN products p ON p.id = dl.product_id WHERE dl.delivery_id = ?", delivery["id"])
    plan = []
    for l in lines:
        names = [text(s).strip() for s in as_list(serials_by_line.get(str(l["id"])) or serials_by_line.get(l["id"]))
                 if text(s).strip()]
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
            started.append(name)
    db.update("deliveries", delivery["id"], {"state": "done", "date_done": now(), "done_by": actor["id"]})
    msg = "Kit dispatched."
    if started:
        msg += " Serial / batch numbers: %s. Their warranty starts when the installation is completed." % ", ".join(started)
    db.note("delivery", delivery["id"], msg, actor["id"])
    db.note("order", order["id"], msg, actor["id"])
    return started


def pack_delivery(db, delivery, actor):
    """Warehouse: the kit is packed and waiting for the vehicle (only once the advance is paid)."""
    if delivery["state"] == "waiting":
        raise RuleError("The advance isn't paid yet, so this kit can't be packed.")
    if not claim(db, "deliveries", delivery["id"], ("ready",), "packed"):
        raise RuleError("This kit is already packed or shipped.")
    db.update("deliveries", delivery["id"], {"packed_at": now()})
    db.note("delivery", delivery["id"], "Kit packed.", actor["id"])
    db.note("order", delivery["order_id"], "Kit packed at the warehouse.", actor["id"])


def deliver_delivery(db, delivery, actor, note=None):
    """The kit reached the customer's site."""
    if not claim(db, "deliveries", delivery["id"], ("done",), "delivered"):
        raise RuleError("Only a shipped kit can be marked delivered.")
    db.update("deliveries", delivery["id"], {"delivered_at": now()})
    msg = "Kit delivered to the site." + (" %s" % note if note else "")
    db.note("delivery", delivery["id"], msg, actor["id"])
    db.note("order", delivery["order_id"], msg, actor["id"])


def components_of(db, product_id, qty):
    """[(product_id, qty)] a line really takes from the shelves: a package becomes its components,
    services take nothing, anything else is itself."""
    prod = db.get("products", product_id)
    if not prod or prod["is_service"]:
        return []
    if prod["is_kit"]:
        return [(kl["product_id"], kl["qty"] * qty) for kl in db.q("SELECT * FROM kit_lines WHERE kit_id = ?", product_id)]
    return [(product_id, qty)]


def order_components(db, order_id):
    out = []
    for line in db.q("SELECT product_id, qty FROM order_lines WHERE order_id = ? AND product_id IS NOT NULL", order_id):
        out += components_of(db, line["product_id"], line["qty"])
    return out


def survey_demand(db):
    """What visited surveys will need before any order is confirmed (the earliest demand tier).
    Uses the draft quote when there is one (it may have been edited), else the package for the
    recommended size plus the parts the survey measured. Confirmed orders are counted by their delivery instead."""
    rows = db.q("SELECT s.*, l.contact_name, l.city, l.ref AS lead_ref, l.system_type, l.requested_kw, u.name AS technician "
                "FROM surveys s JOIN leads l ON l.id = s.lead_id LEFT JOIN users u ON u.id = s.technician_id "
                "WHERE s.state IN ('done', 'approved') AND COALESCE(s.result, '') != 'not_feasible' AND l.stage != 'lost' "
                "AND NOT EXISTS (SELECT 1 FROM orders o WHERE o.lead_id = l.id AND o.state = 'sale') ORDER BY s.id")
    out = []
    for s in rows:
        quote = db.one("SELECT id, ref FROM orders WHERE lead_id = ? AND state IN ('draft', 'sent') ORDER BY id DESC LIMIT 1",
                       s["lead_id"])
        items, problem = {}, None
        if quote:
            parts = order_components(db, quote["id"])
        else:
            kit = package_for(db, s["recommended_kw"] or s["requested_kw"], s["system_type"])
            if not kit:
                problem = "No package for %s kW" % (s["recommended_kw"] or s["requested_kw"] or "?")
                parts = []
            else:
                parts = components_of(db, kit["id"], 1) + [(p["id"], q) for p, q, _r in survey_parts(db, s, kit)]
        for pid, q in parts:
            items[pid] = items.get(pid, 0) + q
        out.append({"survey_id": s["id"], "ref": s["ref"], "lead_ref": s["lead_ref"], "customer": s["contact_name"],
                    "city": s["city"], "kw": s["recommended_kw"], "system_type": s["system_type"], "state": s["state"],
                    "technician": s["technician"], "quote": quote, "problem": problem, "items": items})
    return out


def adjust_stock(db, product, counted, reason, actor_id):
    """Correct the count after a stock check (damage, loss, miscount). Serial-tracked items are
    corrected unit by unit instead (scrap_serial), so every serial stays accounted for."""
    if product["is_kit"] or product["is_service"]:
        raise RuleError("Packages and services have no stock of their own.")
    if product["tracking"] == "serial":
        raise RuleError("For serial-numbered items, remove the exact unit from the serial list instead.")
    counted = as_float(counted, "counted quantity")
    if counted < 0:
        raise RuleError("The count can't be below zero.")
    reason = text(reason).strip()[:200]
    if not reason:
        raise RuleError("Say why the stock is being corrected.")
    change = counted - product["qty_on_hand"]
    if not change:
        raise RuleError("That's already the stock on hand.")
    db.update("products", product["id"], {"qty_on_hand": counted})
    db.insert("stock_moves", {"product_id": product["id"], "qty": change, "kind": "adjust", "note": reason,
                              "user_id": actor_id, "date": now()})
    return change


def scrap_serial(db, serial, reason, actor_id):
    """Take one serial-numbered unit out of stock (damaged, lost, returned to supplier)."""
    if serial["state"] != "in_stock":
        raise RuleError("Only units still in the warehouse can be removed.")
    reason = text(reason).strip()[:200]
    if not reason:
        raise RuleError("Say why this unit is being removed.")
    if not claim(db, "serials", serial["id"], ("in_stock",), "scrapped"):
        raise RuleError("This unit was just changed by someone else.")
    db.exec("UPDATE products SET qty_on_hand = MAX(qty_on_hand - 1, 0) WHERE id = ?", serial["product_id"])
    db.insert("stock_moves", {"product_id": serial["product_id"], "qty": -1, "kind": "adjust",
                              "note": "Serial %s removed: %s" % (serial["name"], reason), "user_id": actor_id, "date": now()})


def reserved_stock(db):
    """{product_id: qty} held for paid orders not yet shipped (ready or packed)."""
    return {r["product_id"]: r["q"] for r in db.q(
        "SELECT dl.product_id, SUM(dl.qty) AS q FROM delivery_lines dl JOIN deliveries d ON d.id = dl.delivery_id "
        "WHERE d.state IN ('ready', 'packed') GROUP BY dl.product_id")}


def unpaid_demand(db):
    """{product_id: qty} for confirmed orders still waiting for their advance."""
    return {r["product_id"]: r["q"] for r in db.q(
        "SELECT dl.product_id, SUM(dl.qty) AS q FROM delivery_lines dl JOIN deliveries d ON d.id = dl.delivery_id "
        "WHERE d.state = 'waiting' GROUP BY dl.product_id")}


# --------------------------------------------------------------------- jobs
# Technician starts the installation on site.
def schedule_installation(db, job, when, actor):
    """Sales (or the Director) sets or moves the installation date of a job that hasn't started."""
    if job["state"] != "planned":
        raise RuleError("This installation has already started, so its date can't change.")
    when = as_local_datetime(when, "installation date")
    if not when:
        raise RuleError("Choose the installation date and time.")
    if when[:10] < today():
        raise RuleError("The installation can't be scheduled in the past.")
    first = not job["scheduled_at"]
    db.update("jobs", job["id"], {"scheduled_at": when})
    msg = "Installation %s for %s." % ("scheduled" if first else "moved", when[:16])
    db.note("job", job["id"], msg, actor["id"])
    db.note("order", job["order_id"], msg, actor["id"])
    cust = db.get("customers", job["customer_id"])
    if cust and cust.get("email"):
        html = mailer.branded(db, "Your installation date", [
            "Hi %s," % cust["name"],
            "Your solar installation is %s for %s. Our crew will call you before arriving." % (
                "booked" if first else "now", datetime.strptime(when[:16], "%Y-%m-%d %H:%M").strftime("%d %b %Y at %H:%M"))],
            "Track my installation", frontend(db) + "/account")
        mailer.queue(db, cust["email"], "Installation date – %s" % (db.setting("company_name") or "SunPower"), html)


def job_start(db, job, actor_id):
    if job["state"] == "done":
        raise RuleError("This job is already completed.")
    if db.val("SELECT state FROM orders WHERE id = ?", job["order_id"]) != "sale":
        raise RuleError("This order is not active, so the job can't start.")
    if not job["scheduled_at"]:
        raise RuleError("Sales hasn't scheduled this installation yet.")
    if job["scheduled_at"][:10] > today():
        raise RuleError("This installation is scheduled for %s. It can start on that day." % job["scheduled_at"][:10])
    if not db.val("SELECT COUNT(*) FROM deliveries WHERE order_id = ? AND state IN ('done', 'delivered')", job["order_id"]):
        raise RuleError("The kit hasn't been shipped yet, so the installation can't start.")
    db.update("jobs", job["id"], {"state": "in_progress", "site_start": job["site_start"] or now()})
    db.note("job", job["id"], "Work started on site.", actor_id)


# Finish an installation. Refused until: checklist complete, a roof photo,
# the installed kW, the customer's signature and the kit dispatched. Then logs
# each technician's hours (labour cost) and emails the certificate link.
def job_finish(db, job, actor, allow_early=False):
    """allow_early: demo data only (installations recorded after the fact)."""
    if not allow_early and job["state"] == "planned" and job["scheduled_at"] and job["scheduled_at"][:10] > today():
        raise RuleError("This installation is scheduled for %s. It can be completed from that day." % job["scheduled_at"][:10])
    missing = [lbl for f, lbl in CHECKLIST if not job[f]]
    if missing:
        raise RuleError("Checklist incomplete: %s." % ", ".join(missing))
    if not db.val("SELECT COUNT(*) FROM attachments WHERE owner_type = 'job' AND owner_id = ?", job["id"]):
        raise RuleError("Upload at least one photo of the finished roof.")
    if not job["kw_confirmed"]:
        raise RuleError("Confirm the installed system size (kW).")
    if not job["signature"]:
        raise RuleError("The homeowner must sign to accept the work.")
    if not db.val("SELECT COUNT(*) FROM deliveries WHERE order_id = ? AND state IN ('done', 'delivered')", job["order_id"]):
        raise RuleError("The kit hasn't been dispatched yet.")
    if not claim(db, "jobs", job["id"], ("planned", "in_progress"), "done"):
        raise RuleError("This job was just completed.")
    end = now()
    start = job["site_start"] or end
    hours = max((parse_dt(end) - parse_dt(start)).total_seconds() / 3600.0, 0.25)  # time on site in hours, at least a quarter hour
    db.update("jobs", job["id"], {"state": "done", "site_start": start, "site_end": end,
                                  "signed_on": job["signed_on"] or end})
    started = start_warranties(db, db.get("orders", job["order_id"]), end[:10])
    ordr = db.get("orders", job["order_id"])
    billed = r2(db.val("SELECT COALESCE(SUM(amount_total), 0) FROM invoices WHERE order_id = ? AND state != 'cancel' "
                       "AND kind != 'service'", ordr["id"]))
    if ordr["amount_total"] - billed > 0.5:   # installed: invoice whatever hasn't been invoiced yet
        final_invoice(db, ordr, actor["id"])
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
    db.note("job", job["id"], "Installation completed and accepted by %s.%s" % (
        job["signed_by"] or cust["name"], " Warranty started for %d units." % started if started else ""), actor["id"])
    db.note("order", job["order_id"], "Installation completed (%s)." % job["ref"], actor["id"])


def start_warranties(db, order, start):
    """Every unit delivered for the order (by its unique serial / batch) gets its warranty from `start`
    (the installation day). Returns how many started."""
    n = 0
    # Read the numbers from this order's own delivery lines: a panel batch can be shared by several orders.
    units = []
    for l in db.q("SELECT dl.serials, dl.product_id, dl.delivery_id, p.warranty_months FROM delivery_lines dl "
                  "JOIN deliveries d ON d.id = dl.delivery_id JOIN products p ON p.id = dl.product_id "
                  "WHERE d.order_id = ? AND d.state IN ('done', 'delivered') AND dl.serials IS NOT NULL", order["id"]):
        for name in json.loads(l["serials"] or "[]"):
            sid = db.val("SELECT id FROM serials WHERE name = ? AND product_id = ?", name, l["product_id"])
            if sid:
                units.append((sid, l))
    for sid, l in units:
        if not l["warranty_months"] or db.one("SELECT id FROM warranties WHERE serial_id = ? AND customer_id = ?",
                                              sid, order["customer_id"]):
            continue
        db.insert("warranties", {"serial_id": sid, "product_id": l["product_id"], "customer_id": order["customer_id"],
                                 "order_id": order["id"], "delivery_id": l["delivery_id"], "start_date": start,
                                 "months": l["warranty_months"],
                                 "end_date": add_months(date.fromisoformat(start), l["warranty_months"]).isoformat()})
        n += 1
    return n


# ------------------------------------------------------------------ tickets
# True if the warranty covers that day (dates as "YYYY-MM-DD" text compare correctly).
def warranty_active_on(w, day):
    return bool(w and w["start_date"] <= day <= w["end_date"])


# Create a service request. If a serial is given, links its product, order and warranty.
def create_ticket(db, customer_id, description, actor_id=None, serial_id=None, fault_code=None,
                  channel="phone", technician_id=None):
    description = text(description).strip()
    if len(description) < 10:
        raise RuleError("Please describe the problem in a few words (at least 10 characters).")
    if technician_id and not is_active_role(db, technician_id, ("technician",)):
        raise RuleError("Choose an active technician.")
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
    for part in db.q("SELECT tl.*, p.name, p.qty_on_hand FROM ticket_lines tl JOIN products p ON p.id = tl.product_id "
                     "WHERE tl.ticket_id = ?", ticket["id"]):
        if part["qty_on_hand"] < part["qty"]:
            raise RuleError("Not enough %s in stock for this repair (%g needed, %g available)." % (
                part["name"], part["qty"], part["qty_on_hand"]))
    for part in db.q("SELECT * FROM ticket_lines WHERE ticket_id = ?", ticket["id"]):   # spare parts leave the warehouse
        db.exec("UPDATE products SET qty_on_hand = qty_on_hand - ? WHERE id = ?", part["qty"], part["product_id"])
        db.insert("stock_moves", {"product_id": part["product_id"], "qty": -part["qty"], "kind": "repair",
                                  "note": "Repair %s" % ticket["ref"], "user_id": actor_id, "date": now()})
    if not amounts["under_warranty"] and amounts["customer_charge"] and not ticket["invoice_id"]:
        untaxed = amounts["customer_charge"]
        tax = r2(untaxed * GST_SERVICE / 100.0)
        iid = db.insert("invoices", {"ref": db.next_ref("invoice", "INV-"), "ticket_id": ticket["id"],
                                     "order_id": ticket["order_id"], "customer_id": ticket["customer_id"],
                                     "kind": "service", "amount_untaxed": untaxed, "amount_tax": tax,
                                     "amount_total": r2(untaxed + tax), "date": today()})
        email_invoice(db, iid)
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
        "SELECT COUNT(*) FROM deliveries WHERE order_id = ? AND state NOT IN ('done', 'delivered')", oid)
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
    ref = db.next_ref("payment", "PAY-")
    rz = None
    if mode == "razorpay":   # ask Razorpay first, so a failure leaves no half-made payment behind
        try:
            r = httpx.post("https://api.razorpay.com/v1/orders", timeout=15,
                           auth=(db.setting("razorpay_key_id"), db.setting("razorpay_key_secret")),
                           json={"amount": int(round(amount * 100)), "currency": "INR",
                                 "receipt": ref, "notes": {"order": order["ref"]}})
            r.raise_for_status()
            rz = r.json()
        except Exception:
            raise RuleError("The payment service isn't reachable right now. Please try again in a minute.")
    pid = db.insert("payments", {"ref": ref, "order_id": order["id"], "provider_ref": rz["id"] if rz else None,
                                 "customer_id": order["customer_id"], "amount": amount, "method": mode,
                                 "state": "pending", "purpose": purpose, "date": now(), "created_by": user_id})
    out = {"payment_id": pid, "mode": mode, "amount": amount, "currency": "INR",
           "description": "%s %s" % ("Advance for" if purpose == "advance" else "Payment for", order["ref"])}
    if rz:
        out["razorpay"] = {"key": db.setting("razorpay_key_id"), "order_id": rz["id"],
                           "name": db.setting("company_name")}
    return out


# The bank confirmed a pending payment: record it as received (via record_payment).
def complete_online_payment(db, payment, provider_ref=None, actor_id=None):
    if payment["state"] == "done":
        return payment["id"]
    # Claim it first: if the bank confirmation arrives twice (double click, two tabs, a retry),
    # only one request may turn this pending payment into money received.
    if db.exec("DELETE FROM payments WHERE id = ? AND state = 'pending'", payment["id"]).rowcount != 1:
        raise RuleError("This payment was already completed.")
    order = db.get("orders", payment["order_id"])
    return record_payment(db, order, payment["amount"], payment["method"], actor_id,
                          provider_ref=provider_ref or payment["provider_ref"], purpose=payment["purpose"], cap=False)


# Check that a payment confirmation really came from Razorpay: Razorpay signs
# "order_id|payment_id" with our secret key (HMAC-SHA256); we recompute and compare.
def verify_razorpay_signature(db, razorpay_order_id, razorpay_payment_id, signature):
    import hashlib
    import hmac
    secret = (db.setting("razorpay_key_secret") or "").encode()
    expected = hmac.new(secret, ("%s|%s" % (razorpay_order_id, razorpay_payment_id)).encode(), hashlib.sha256).hexdigest()
    return bool(secret) and hmac.compare_digest(expected, signature or "")



# ------------------------------------------------------- customer tracker
def enquiry_progress(lead, survey):
    """What a customer sees for an enquiry: an honest status, the next step and
    dated milestones. Only marks a step done when it really happened."""
    stage = lead["stage"]
    sstate = survey["state"] if survey else None
    contacted = stage != "new" or bool(survey) or bool(lead.get("booking_confirmed_at"))
    booked = bool(survey) and sstate in ("scheduled", "done", "approved")
    visited = sstate in ("done", "approved")
    when = survey["survey_date"] if survey else None
    if stage == "lost":
        status, nxt = "Closed", "This enquiry is closed. Book a new survey any time."
    elif sstate == "rejected":
        status, nxt = "Roof not suitable", "Our team found the roof unsuitable. An advisor will call to explain the options."
    elif sstate == "approved":
        status, nxt = "Preparing your quotation", "Your quotation will appear here once it is ready."
    elif sstate == "done":
        status, nxt = "Survey completed", "We are reviewing the survey before preparing your quotation."
    elif sstate == "scheduled":
        status = "Survey booked" + (" · %s" % when[:10] if when else "")
        nxt = "A technician will visit to measure your roof" + (" on %s." % when[:10] if when else ". We'll confirm the date.")
    elif contacted:
        status, nxt = "Survey to be booked", "An advisor has spoken to you and will book your free roof survey."
    else:
        status = "Awaiting confirmation call"
        pref = ""
        if lead.get("preferred_date"):
            pref = " for %s (%s)" % (lead["preferred_date"], dict(SURVEY_SLOTS).get(lead.get("preferred_slot"), "any time"))
        nxt = "Our team will call you within two working hours to confirm your survey%s." % pref
    steps = [
        {"label": "Enquiry received", "done": True, "date": lead["created_at"]},
        {"label": "Booking confirmed", "done": contacted, "date": lead.get("booking_confirmed_at")},
        {"label": "Technician assigned", "done": booked, "date": when if booked else None},
        {"label": "Survey done", "done": visited},
        {"label": "Quotation", "done": False},
    ]
    return {"status": status, "next": nxt, "steps": steps, "closed": stage == "lost" or sstate == "rejected"}
