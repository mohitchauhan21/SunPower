"""Who can open what. Enforced on the server for every staff endpoint; the
website builds its module navigation from the same table.

rw = read & change, r = read only, own = only records assigned to them.

Create / read / update follow ACCESS. Delete is stricter and listed separately in
DELETE: only these roles may remove records, and every delete endpoint also
refuses when removing the record would break history (e.g. a confirmed order).
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
    "warranties": {"director": "rw", "sales": "r", "warehouse": "r", "support": "r", "technician": "own"},
    "customers": {"director": "rw", "sales": "rw", "support": "rw"},
    "subsidies": {"director": "rw", "sales": "rw", "support": "r"},
    "insights": {"director": "rw"},
    "reports": {"director": "rw"},
    "settings": {"director": "rw"},
}

# Who may delete (or void / retire) records in each area.
DELETE = {
    "leads": ("director", "sales"),        # enquiries without a confirmed order
    "surveys": ("director", "sales"),      # surveys not used by a quote
    "orders": ("director", "sales"),       # draft / sent quotations only (confirmed: cancel instead)
    "customers": ("director",),            # customers with no orders, enquiries or requests
    "subsidies": ("director",),
    "stock": ("director",),                # retire a product (kept for history, hidden from lists)
    "jobs": ("director",),                 # planned jobs with no hours logged
    "tickets": ("director", "support"),    # requests with no invoice
    "money": ("director",),                # void a payment, cancel an unpaid invoice
    "users": ("director",),                # staff accounts are switched off, never erased
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


def can_delete(user, area):
    return user["role"] in DELETE.get(area, ())


def need_delete(user, area):
    if not can_delete(user, area):
        raise HTTPException(403, "You don't have permission to delete this.")


def modules_for(user):
    return [{"key": k, "label": l, "path": p, "level": level(user, k), "delete": can_delete(user, k)}
            for k, l, p in MODULES if can_read(user, k)]
