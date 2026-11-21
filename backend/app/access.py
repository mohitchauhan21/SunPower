"""Who can open what. Enforced on the server for every staff endpoint; the
website builds its module navigation from the same table.

rw = read & change, r = read only, own = only records assigned to them.
"""
from fastapi import HTTPException

ACCESS = {
    "dashboard": {"director": "rw", "sales": "r", "warehouse": "r", "technician": "r", "support": "r"},
    "leads": {"director": "rw", "sales": "rw", "support": "r"},
    "surveys": {"director": "rw", "sales": "rw", "support": "r", "technician": "own"},
    "orders": {"director": "rw", "sales": "rw", "support": "r", "warehouse": "r"},
    "deliveries": {"director": "rw", "warehouse": "rw", "sales": "r"},
    "stock": {"director": "rw", "warehouse": "rw", "sales": "r", "support": "r", "technician": "r"},
    "jobs": {"director": "rw", "sales": "r", "warehouse": "r", "support": "r", "technician": "own"},
    "tickets": {"director": "rw", "support": "rw", "sales": "r", "technician": "own"},
    "warranties": {"director": "r", "sales": "r", "warehouse": "r", "support": "r", "technician": "own"},
    "customers": {"director": "r", "sales": "r", "support": "r"},
    "subsidies": {"director": "rw", "sales": "rw", "support": "r"},
    "insights": {"director": "rw"},
    "reports": {"director": "rw"},
    "settings": {"director": "rw"},
}

# Website modules, in navigation order
MODULES = [
    ("dashboard", "Today", "/app"),
    ("leads", "Enquiries", "/app/enquiries"),
    ("surveys", "Surveys", "/app/surveys"),
    ("orders", "Quotes & orders", "/app/orders"),
    ("deliveries", "Dispatch", "/app/dispatch"),
    ("stock", "Stock", "/app/stock"),
    ("jobs", "Installations", "/app/jobs"),
    ("tickets", "Requests", "/app/service"),
    ("warranties", "Warranties", "/app/warranties"),
    ("customers", "Customers", "/app/customers"),
    ("subsidies", "Subsidy", "/app/subsidy"),
    ("insights", "Insights", "/app/insights"),
    ("reports", "Reports", "/app/reports"),
    ("settings", "Settings", "/app/settings"),
]


def level(user, area):
    return ACCESS.get(area, {}).get(user["role"])


def can_read(user, area):
    return level(user, area) is not None


def can_write(user, area):
    return level(user, area) in ("rw", "own")


def need(user, area, write=False):
    lvl = level(user, area)
    if not lvl or (write and lvl == "r"):
        raise HTTPException(403, "You don't have access to this.")
    return lvl


def modules_for(user):
    return [{"key": k, "label": l, "path": p, "level": level(user, k)}
            for k, l, p in MODULES if can_read(user, k)]
