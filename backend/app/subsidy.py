"""PM Surya Ghar subsidy by state / UT (from India_PM_Surya_Ghar_State_Wise_Subidy_Rates.xlsx,
researched 22-Nov-2026).

CENTRAL subsidy (CFA) is official (MNRE):
  general states/UTs: Rs 30,000/kW for the first 2 kW + Rs 18,000 for the 3rd kW (max Rs 78,000)
  special-category:   Rs 33,000/kW for the first 2 kW + Rs 19,800 for the 3rd kW (max Rs 85,800)
  No extra central subsidy above 3 kW for a household.

STATE TOP-UPS are only "reported" in the sheet (not confirmed from an official
notification), so they are never added automatically: the customer can switch
them on, and the website labels them "reported, verify with your DISCOM".
"""

RATES = {"general": (30000, 18000), "special": (33000, 19800)}   # per kW for kW 1-2, for the 3rd kW
CENTRAL_CAP_KW = 3
DEFAULT_STATE = "Gujarat"
SHEET_DATE = "22 Nov 2026"

# name, category, top-up rule (or None), top-up note from the sheet
# top-up rule: {"per_kw": x, "max": y} or {"tiers": {kW: amount}} (amount for that size and above)
STATES = [
    ("Andhra Pradesh", "general", None, "Reported targeted SC/ST district drives; not universal"),
    ("Arunachal Pradesh", "special", None, "No universal top-up verified"),
    ("Assam", "special", {"per_kw": 15000, "max": 45000}, "Reported ₹15,000/kW, max ₹45,000; availability unclear"),
    ("Bihar", "general", {"per_kw": 10000, "max": 20000}, "Reported ₹10,000/kW, max ₹20,000; needs verification"),
    ("Chhattisgarh", "general", {"tiers": {1: 15000, 2: 30000}}, "Reported ₹15,000 (1 kW), ₹30,000 (2 kW+)"),
    ("Goa", "general", None, "Reported cost-based incentive; amount not verified"),
    ("Gujarat", "general", None, "No universal state capital subsidy; regulatory-charge relief reported"),
    ("Haryana", "general", None, "Targeted schemes for eligible income groups; amounts vary"),
    ("Himachal Pradesh", "special", None, "No additional universal top-up verified"),
    ("Jharkhand", "general", None, "Reported income-limited top-up; not verified"),
    ("Karnataka", "general", None, "No universal additional top-up verified"),
    ("Kerala", "general", None, "No universal additional top-up verified"),
    ("Madhya Pradesh", "general", None, "No universal additional top-up verified"),
    ("Maharashtra", "general", None, "Targeted MSEDCL schemes reported (SMART); not universal"),
    ("Manipur", "special", None, "No universal top-up verified"),
    ("Meghalaya", "special", None, "No universal top-up verified"),
    ("Mizoram", "special", None, "No universal top-up verified"),
    ("Nagaland", "special", None, "No universal top-up verified"),
    ("Odisha", "general", None, "Reported additional amounts vary across sources"),
    ("Punjab", "general", None, "No universal state top-up identified"),
    ("Rajasthan", "general", None, "Reported ₹17,000 only for eligible Mukhyamantri Nishulk Bijli Yojana beneficiaries"),
    ("Sikkim", "special", None, "No universal top-up verified"),
    ("Tamil Nadu", "general", {"tiers": {1: 5000, 2: 10000, 3: 22000}}, "Reported tiered top-up (₹5,000 / ₹10,000 / ₹22,000)"),
    ("Telangana", "general", None, "Reported top-up claims; not verified"),
    ("Tripura", "special", None, "No universal top-up verified"),
    ("Uttar Pradesh", "general", {"per_kw": 15000, "max": 30000}, "Reported ₹15,000/kW up to ₹30,000 via UPNEDA"),
    ("Uttarakhand", "special", None, "No universal top-up; earlier state support reportedly discontinued"),
    ("West Bengal", "general", None, "Reported tiered top-up; eligibility needs verification"),
    ("Andaman & Nicobar Islands", "special", None, "No universal top-up verified"),
    ("Chandigarh", "general", None, "Proposed top-up reported; approval not confirmed"),
    ("Dadra & Nagar Haveli and Daman & Diu", "general", None, "No universal top-up verified"),
    ("Delhi", "general", None, "Reported 2026 top-up revisions; amount needs official confirmation"),
    ("Jammu & Kashmir", "special", {"per_kw": 3000, "max": 9000}, "Reported UT top-up ₹3,000/kW"),
    ("Ladakh", "special", None, "Reported local assistance; not verified"),
    ("Lakshadweep", "special", None, "No universal top-up verified"),
    ("Puducherry", "general", {"per_kw": 9000, "max": 27000}, "Reported UT top-up ₹9,000–₹10,000/kW (lower figure used)"),
]
BY_NAME = {s[0].lower(): s for s in STATES}


def state_row(state):
    return BY_NAME.get((state or DEFAULT_STATE).strip().lower()) or BY_NAME[DEFAULT_STATE.lower()]


def central(kw, category="general"):
    """Central subsidy for a household system of `kw` (capped at 3 kW)."""
    first, third = RATES.get(category, RATES["general"])
    kw = max(min(kw or 0, CENTRAL_CAP_KW), 0)
    return round(first * min(kw, 2) + third * max(kw - 2, 0))


def topup(kw, rule):
    if not rule or not kw:
        return 0
    if "per_kw" in rule:
        return round(min(rule["per_kw"] * kw, rule["max"]))
    tiers = [amount for size, amount in sorted(rule["tiers"].items()) if kw >= size]
    return tiers[-1] if tiers else 0


def subsidy_for(kw, state=None, include_topup=False):
    """{central, topup, total, category, state} for a system size in a state."""
    name, category, rule, _note = state_row(state)
    c = central(kw, category)
    t = topup(kw, rule) if include_topup else 0
    return {"state": name, "category": category, "central": c, "topup": t, "total": c + t,
            "topup_available": topup(kw, rule)}


def average_central(kw):
    """Average central subsidy across all states/UTs (used on the home page)."""
    return round(sum(central(kw, s[1]) for s in STATES) / len(STATES))


def states_payload():
    return {
        "default": DEFAULT_STATE, "researched": SHEET_DATE,
        "rates": {k: {"per_kw": v[0], "third_kw": v[1], "max": central(3, k)} for k, v in RATES.items()},
        "states": [{"name": n, "category": c, "topup": r, "note": note} for n, c, r, note in STATES],
        "average": {str(kw): average_central(kw) for kw in range(1, 11)},
    }
