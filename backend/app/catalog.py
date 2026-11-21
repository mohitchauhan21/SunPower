"""Master data: components, the 10 packages (1-5 kW, on/off-grid), the
installation service, and company defaults."""
import math

PANEL_W = 540

# category -> (label, default warranty months)
CATEGORIES = {
    "panel": ("Solar panels", 240),
    "inverter": ("Inverters", 24),
    "battery": ("Batteries", 24),
    "controller": ("Charge controllers", 24),
    "bos": ("Balance of system", 0),
    "kit": ("Solar packages", 0),
    "service": ("Services", 0),
}

# code, name, category, tracking, cost, price
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
INVERTER_COST = {1: 9000, 2: 14000, 3: 19000, 4: 24000, 5: 28000}

GST_GOODS = 12.0     # solar kits and components
GST_SERVICE = 18.0   # installation and repair labour

INSTALL_CODE = "SRV-INSTALL"
INSTALL_PRICE_PER_KW = 5000

DEFAULT_SETTINGS = {
    "company_name": "SunPower Solutions",
    "company_phone": "+91 79 4000 5000",
    "company_email": "hello@sunpower.example",
    "company_address": "12 Solar Park Road, SG Highway, Ahmedabad 380054",
    "company_gstin": "24ABCDE1234F1Z5",
    "frontend_url": "http://localhost:5173",
    "advance_pct": "30",
    "quote_valid_days": "15",
    "labour_rate": "500",
    "quote_note": ("Prices are exclusive of GST, which is shown separately. The price covers the "
                   "complete kit, installation, net-metering paperwork and subsidy filing by "
                   "SunPower. Warranty: panels 20 years; inverter, batteries and charge "
                   "controller 2 years, starting on the delivery date."),
    "smtp_enabled": "0", "smtp_host": "smtp.gmail.com", "smtp_port": "587",
    "smtp_user": "", "smtp_password": "", "smtp_from": "",
    "google_client_id": "", "google_client_secret": "",
    "razorpay_key_id": "", "razorpay_key_secret": "",
    "test_payments": "1",
    "ai_url": "http://localhost:8000",
}

TECH_RATES = [220, 260, 300, 340, 380]


def kit_lines(kw, system_type):
    panels = math.ceil(kw * 1000 / PANEL_W)
    lines = [("PNL-540", panels), ("INV-%sKW" % kw, 1), ("MPPT-60", 1), ("STR-1KW", kw),
             ("DCDB-1", 1), ("ACDB-1", 1), ("MC4-PR", 2 + panels // 2), ("CBL-DC4", 20 + 5 * kw),
             ("CBL-AC4", 15 + 2 * kw), ("ERT-KIT", 3), ("LA-1", 1)]
    if system_type == "off_grid":
        lines.append(("BAT-150", 2 * kw))
    return lines


def seed_catalog(db):
    """Create components, inverters, packages and the installation service once."""
    if db.val("SELECT COUNT(*) FROM products"):
        return
    ids = {}
    for code, name, cat, tracking, cost, price in COMPONENTS:
        ids[code] = db.insert("products", {
            "code": code, "name": name, "category": cat, "tracking": tracking, "cost": cost,
            "price": price, "tax_rate": GST_GOODS, "warranty_months": CATEGORIES[cat][1],
            "min_qty": 20 if cat == "panel" else 5})
    for kw, cost in INVERTER_COST.items():
        code = "INV-%sKW" % kw
        ids[code] = db.insert("products", {
            "code": code, "name": "Solar Inverter %s kW (Hybrid)" % kw, "category": "inverter",
            "tracking": "serial", "cost": cost, "price": round(cost * 1.3, -2), "tax_rate": GST_GOODS,
            "warranty_months": 24, "min_qty": 3})
    for system_type in ("on_grid", "off_grid"):
        label = "On-Grid" if system_type == "on_grid" else "Off-Grid"
        for kw in range(1, 6):
            lines = kit_lines(kw, system_type)
            cost = sum(db.val("SELECT cost FROM products WHERE id = ?", ids[c]) * q for c, q in lines)
            kit = db.insert("products", {
                "code": "KIT-%s-%sKW" % ("ON" if system_type == "on_grid" else "OFF", kw),
                "name": "%s Solar System %s kW" % (label, kw), "category": "kit", "tracking": "none",
                "cost": cost, "price": round(cost * 1.22, -3), "tax_rate": GST_GOODS,
                "is_kit": 1, "kw": kw, "system_type": system_type})
            for code, qty in lines:
                db.insert("kit_lines", {"kit_id": kit, "product_id": ids[code], "qty": qty})
    db.insert("products", {
        "code": INSTALL_CODE, "name": "Solar Installation & Commissioning (per kW)",
        "category": "service", "cost": 0, "price": INSTALL_PRICE_PER_KW, "tax_rate": GST_SERVICE,
        "is_service": 1})


def seed_settings(db):
    for k, v in DEFAULT_SETTINGS.items():
        if db.setting(k) is None:
            db.set_setting(k, v)
