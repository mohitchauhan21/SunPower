"""Master data: components, the 10 packages (1-5 kW, on/off-grid), the
installation service, and company defaults.

WHAT THIS FILE DOES
  Holds the fixed starting data of the business and writes it into the database
  the first time the app starts (seed_catalog, seed_settings, called from
  main.bootstrap). After that, the Director changes prices, warranty months and
  settings from the website; this file is not read again for those.

WHO USES IT
  main.py (start-up), rules.py (GST rates, installation product code),
  seed.py (technician pay rates), routers/staff_ops.py (categories for new products).
"""
import math                       # math.ceil = round up to the next whole number

PANEL_W = 540                     # watts per solar panel (a 540 W panel)

# category -> (label, default warranty months). 240 months = 20 years.
CATEGORIES = {
    "panel": ("Solar panels", 240),
    "inverter": ("Inverters", 24),
    "battery": ("Batteries", 24),
    "controller": ("Charge controllers", 24),
    "bos": ("Balance of system", 0),          # "balance of system": cables, boxes, structure...
    "kit": ("Solar packages", 0),
    "service": ("Services", 0),
}

# code, name, category, tracking, cost, price
# tracking: "serial" = every unit has its own serial number (inverter, battery, controller),
#           "lot" = tracked by batch (panels), "none" = just counted (cables, boxes).
COMPONENTS = [
    ("PNL-540", "Solar Panel 540W Mono PERC", "panel", "lot", 11500, 14500),
    ("MPPT-60", "MPPT Charge Controller 60A", "controller", "serial", 4200, 5800),
    ("BAT-150", "Tubular Battery 150Ah 12V", "battery", "serial", 11000, 14000),
    ("STR-1KW", "GI Mounting Structure (per kW)", "bos", "none", 4500, 6000),
    ("DCDB-1", "DC Distribution Box (DCDB)", "bos", "none", 1800, 2500),
    ("ACDB-1", "AC Distribution Box (ACDB)", "bos", "none", 1600, 2200),
    ("MC4-PR", "MC4 Connector Pair", "bos", "none", 90, 150),
    ("CBL-DC4", "DC Solar Cable 4 sq mm (m)", "bos", "none", 45, 70),
    ("CBL-AC4", "AC Cable 4 sq mm (m)", "bos", "none", 55, 80),
    ("ERT-KIT", "Earthing Kit (chemical, 2 m)", "bos", "none", 1400, 2000),
    ("LA-1", "Lightning Arrester", "bos", "none", 1200, 1800),
]
# Inverter cost by size in kW (one inverter per package, sized to the package).
INVERTER_COST = {1: 9000, 2: 14000, 3: 19000, 4: 24000, 5: 28000}

GST_GOODS = 12.0     # solar kits and components
GST_SERVICE = 18.0   # installation and repair labour

INSTALL_CODE = "SRV-INSTALL"          # product code of the installation service line on every quote
INSTALL_PRICE_PER_KW = 5000           # installation price per kW (before GST)

# Company settings written on first start. All values are text (the settings
# table stores text). The Director edits them in Business -> Settings.
DEFAULT_SETTINGS = {
    "company_name": "SunPower Solutions",
    "company_phone": "+91 79 4000 5000",
    "company_email": "hello@sunpower.example",
    "company_address": "12 Solar Park Road, SG Highway, Ahmedabad 380054",
    "company_gstin": "24ABCDE1234F1Z5",
    "frontend_url": "http://localhost:5173",       # used to build links in emails
    "advance_pct": "30",                           # % to pay before the kit can be dispatched
    "quote_valid_days": "15",
    "labour_rate": "500",                          # ₹ per hour for repairs
    # Two text pieces next to each other inside (...) are joined into one string by Python.
    "quote_note": ("Prices are exclusive of GST, which is shown separately. The price covers the "
                   "complete kit, installation, net-metering paperwork and subsidy filing by "
                   "SunPower. Warranty: panels 20 years; inverter, batteries and charge "
                   "controller 2 years, starting on the delivery date."),
    "smtp_enabled": "0", "smtp_host": "smtp.gmail.com", "smtp_port": "587",   # outgoing email (off)
    "smtp_user": "", "smtp_password": "", "smtp_from": "",
    "google_client_id": "", "google_client_secret": "",                         # Google sign-in
    "razorpay_key_id": "", "razorpay_key_secret": "",                           # online payments
    "test_payments": "1",                                                       # allow test cards
    "ai_url": "http://localhost:8000",
}

# Hourly pay rates (₹) given to the demo technicians in turn (seed.py).
TECH_RATES = [220, 260, 300, 340, 380]


def kit_lines(kw, system_type):
    """The parts list of one package: [(component code, quantity), ...].

    Example: 3 kW needs ceil(3000 / 540) = 6 panels. Off-grid packages also get
    two 150 Ah batteries per kW. // is whole-number division (7 // 2 == 3).
    """
    panels = math.ceil(kw * 1000 / PANEL_W)
    lines = [("PNL-540", panels), ("INV-%sKW" % kw, 1), ("MPPT-60", 1), ("STR-1KW", kw),
             ("DCDB-1", 1), ("ACDB-1", 1), ("MC4-PR", 2 + panels // 2), ("CBL-DC4", 20 + 5 * kw),
             ("CBL-AC4", 15 + 2 * kw), ("ERT-KIT", 3), ("LA-1", 1)]
    if system_type == "off_grid":
        lines.append(("BAT-150", 2 * kw))
    return lines


def seed_catalog(db):
    """Create components, inverters, packages and the installation service once."""
    if db.val("SELECT COUNT(*) FROM products"):    # products already there: never seed twice
        return
    ids = {}                                       # component code -> its new product id
    for code, name, cat, tracking, cost, price in COMPONENTS:   # unpack each tuple into 6 names
        ids[code] = db.insert("products", {
            "code": code, "name": name, "category": cat, "tracking": tracking, "cost": cost,
            "price": price, "tax_rate": GST_GOODS, "warranty_months": CATEGORIES[cat][1],
            "min_qty": 20 if cat == "panel" else 5})          # "x if condition else y"
    for kw, cost in INVERTER_COST.items():         # .items() gives (key, value) pairs
        code = "INV-%sKW" % kw
        ids[code] = db.insert("products", {
            "code": code, "name": "Solar Inverter %s kW (Hybrid)" % kw, "category": "inverter",
            # round(x, -2) rounds to the nearest hundred (selling price = cost + 30%)
            "tracking": "serial", "cost": cost, "price": round(cost * 1.3, -2), "tax_rate": GST_GOODS,
            "warranty_months": 24, "min_qty": 3})
    # The 10 packages: on-grid and off-grid, 1 to 5 kW each. range(1, 6) = 1, 2, 3, 4, 5.
    for system_type in ("on_grid", "off_grid"):
        label = "On-Grid" if system_type == "on_grid" else "Off-Grid"
        for kw in range(1, 6):
            lines = kit_lines(kw, system_type)
            # Package cost = sum of (component cost x quantity) over its parts list.
            cost = sum(db.val("SELECT cost FROM products WHERE id = ?", ids[c]) * q for c, q in lines)
            kit = db.insert("products", {
                "code": "KIT-%s-%sKW" % ("ON" if system_type == "on_grid" else "OFF", kw),
                "name": "%s Solar System %s kW" % (label, kw), "category": "kit", "tracking": "none",
                # price = cost + 22%, rounded to the nearest thousand
                "cost": cost, "price": round(cost * 1.22, -3), "tax_rate": GST_GOODS,
                "is_kit": 1, "kw": kw, "system_type": system_type})
            for code, qty in lines:                # remember which parts make up this package
                db.insert("kit_lines", {"kit_id": kit, "product_id": ids[code], "qty": qty})
    db.insert("products", {
        "code": INSTALL_CODE, "name": "Solar Installation & Commissioning (per kW)",
        "category": "service", "cost": 0, "price": INSTALL_PRICE_PER_KW, "tax_rate": GST_SERVICE,
        "is_service": 1})


def seed_settings(db):
    """Write each default setting that doesn't exist yet (existing values are kept)."""
    for k, v in DEFAULT_SETTINGS.items():
        if db.setting(k) is None:
            db.set_setting(k, v)
