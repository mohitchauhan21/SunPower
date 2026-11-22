"""Printable documents: quotation, installation certificate, director report.

They are plain HTML pages styled for A4; the browser's "Save as PDF" makes the
PDF (no wkhtmltopdf needed). Quotes and certificates are opened with the
order's secret token (sent to the customer) or by signed-in staff; the report
is for the Director only.
"""
from datetime import datetime, timezone
from html import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from .. import rules
from ..db import get_db
from ..security import STAFF, session_user
from .staff_admin import dashboard_data

router = APIRouter(prefix="/print")

CSS = """
*{box-sizing:border-box}body{font-family:-apple-system,'Segoe UI',Inter,Arial,sans-serif;color:#1d1d1f;margin:0;
background:#f5f5f7;font-size:13px;line-height:1.45}.page{background:#fff;width:210mm;min-height:297mm;margin:16px auto;
padding:18mm 16mm}.head{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:2px solid #1d1d1f;
padding-bottom:12px;margin-bottom:18px}.brand{font-size:20px;font-weight:700;letter-spacing:-.02em}.brand span{color:#e8740c}
.muted{color:#6e6e73}h1{font-size:22px;margin:0 0 4px;letter-spacing:-.02em}h2{font-size:15px;margin:22px 0 8px}
table{width:100%;border-collapse:collapse;margin:6px 0}th{text-align:left;font-weight:600;font-size:11px;color:#6e6e73;
border-bottom:1px solid #d2d2d7;padding:6px 8px}td{padding:7px 8px;border-bottom:1px solid #ececf0;vertical-align:top}
.num{text-align:right;font-variant-numeric:tabular-nums}.tot td{font-weight:600}.grand td{font-size:15px;font-weight:700;
border-top:2px solid #1d1d1f}.box{border:1px solid #f0b400;background:#fffaf0;border-radius:8px;padding:12px 14px;margin-top:16px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:6px 24px}.sig{margin-top:40px;display:flex;justify-content:space-between}
.sig img{max-height:70px}.bad{color:#d70015}.bar{position:sticky;top:0;background:#1d1d1f;color:#fff;text-align:center;padding:10px}
.bar button{font:inherit;background:#fff;border:0;border-radius:999px;padding:6px 16px;margin-left:10px;cursor:pointer}
@media screen and (max-width:840px){.page{width:auto;min-height:0;margin:0;padding:20px 16px}.grid{grid-template-columns:1fr}table{display:block;overflow-x:auto}}@media print{body{background:#fff}.page{margin:0;width:auto;min-height:auto}.bar{display:none}}
"""


def _page(db, title, body):
    company = escape(db.setting("company_name", "SunPower"))
    return HTMLResponse(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><title>%s</title><style>%s</style></head><body>"
        "<div class='bar'>%s <button onclick='window.print()'>Print / Save as PDF</button></div>"
        "<div class='page'><div class='head'><div><div class='brand'>☀ Sun<span>Power</span></div>"
        "<div class='muted'>%s<br>%s<br>%s · %s<br>GSTIN %s</div></div><div style='text-align:right'>%s</div></div>%s</div>"
        "</body></html>" % (escape(title), CSS, escape(title), company, escape(db.setting("company_address", "")),
                             escape(db.setting("company_phone", "")), escape(db.setting("company_email", "")),
                             escape(db.setting("company_gstin", "")), "", body))


def _order_access(db, request, order_id, token, staff_areas=("orders",)):
    import hmac
    from ..access import can_read
    o = db.get("orders", order_id)
    if not o:
        raise HTTPException(404, "Not found.")
    user = session_user(db, request)
    token_ok = bool(token and o["access_token"] and hmac.compare_digest(str(token), o["access_token"]))
    staff_ok = bool(user and user["role"] in STAFF and any(can_read(user, a) for a in staff_areas))
    owner_ok = bool(user and user["role"] == "customer" and user.get("customer_id") == o["customer_id"]
                    and o["state"] != "draft")
    ok = token_ok or staff_ok or owner_ok
    if not ok:
        raise HTTPException(403, "This link is not valid.")
    return o


def _lt(v, with_time=True):
    """Stored UTC time -> the server's local time for printing ("21 Nov 2026, 14:30")."""
    if not v:
        return ""
    try:
        dt = datetime.strptime(str(v)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone()
    except ValueError:
        return str(v)[:16]
    return dt.strftime("%d %b %Y, %H:%M" if with_time else "%d %b %Y")


def _day(v):
    """"2026-11-08" -> "08 Nov 2026"."""
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").strftime("%d %b %Y")
    except ValueError:
        return str(v or "")


def _m(v):
    return escape(rules.money(v))


@router.get("/quote/{order_id}")
def quote(order_id: int, request: Request, token: str = "", db=Depends(get_db)):
    o = _order_access(db, request, order_id, token)
    c = db.get("customers", o["customer_id"])
    lines = db.q("SELECT * FROM order_lines WHERE order_id = ? ORDER BY id", o["id"])
    lead = db.get("leads", o["lead_id"]) if o["lead_id"] else None
    subsidy = (rules.subsidy_expected(o["kw"], rules.lead_state(db, o))
               if lead and lead["subsidy_requested"] and o["system_type"] == "on_grid" else 0)
    rows = "".join(
        "<tr><td>%s</td><td class='num'>%g</td><td class='num'>%s</td><td class='num'>%s</td><td class='num'>%g%%</td>"
        "<td class='num'>%s</td></tr>" % (escape(l["description"] or ""), l["qty"], _m(l["price_unit"]),
                                         ("%g%%" % l["discount"]) if l["discount"] else "–", l["tax_rate"], _m(l["subtotal"]))
        for l in lines)
    title = ("Quotation" if o["state"] in ("draft", "sent") else "Order") + " " + o["ref"]
    if lead and lead.get("project_ref"):
        title += " · Project " + lead["project_ref"]
    est = ""
    if o["est_kwh_year"]:
        est = ("<div class='box'><b>Your solar system at a glance</b><div class='grid' style='margin-top:8px'>"
               "<div>System size</div><div><b>%g kW %s</b></div><div>Estimated generation</div><div><b>%s kWh / year</b></div>"
               "<div>Estimated savings</div><div><b>%s / year</b></div>%s<div>Estimated payback</div><div><b>%.1f years</b></div>"
               "</div><div class='muted' style='margin-top:6px'>Source: %s</div></div>") % (
            o["kw"], "On-Grid" if o["system_type"] == "on_grid" else "Off-Grid", "{:,.0f}".format(o["est_kwh_year"]),
            _m(o["est_savings_year"]),
            ("<div>PM Surya Ghar subsidy (paid to you)</div><div><b>%s</b></div><div>Your cost after subsidy</div>"
             "<div><b>%s</b></div>" % (_m(subsidy), _m(o["amount_total"] - subsidy))) if subsidy else "",
            (o["amount_total"] - subsidy) / o["est_savings_year"] if o["est_savings_year"] else 0, escape(o["est_source"] or ""))
    body = ("<h1>%s</h1><div class='grid'><div><span class='muted'>Customer</span><br><b>%s</b><br>%s<br>%s %s</div>"
            "<div><span class='muted'>Date</span> %s<br><span class='muted'>Valid until</span> %s<br>"
            "<span class='muted'>Advance to book</span> %s%% (%s)</div></div>"
            "<table><thead><tr><th>Description</th><th class='num'>Qty</th><th class='num'>Unit price</th>"
            "<th class='num'>Disc.</th><th class='num'>GST</th><th class='num'>Amount</th></tr></thead><tbody>%s"
            "<tr class='tot'><td colspan='5' class='num'>Subtotal</td><td class='num'>%s</td></tr>"
            "<tr class='tot'><td colspan='5' class='num'>GST</td><td class='num'>%s</td></tr>"
            "<tr class='grand'><td colspan='5' class='num'>Total</td><td class='num'>%s</td></tr></tbody></table>%s"
            "<p class='muted' style='margin-top:18px'>%s</p>%s") % (
        escape(title), escape(c["name"]), escape(c.get("street") or ""), escape(c.get("city") or ""), escape(c.get("phone") or ""),
        _lt(o["date_order"], False), o["valid_until"] or "–", escape(db.setting("advance_pct", "30")),
        _m(rules.advance_needed(db, o)), rows, _m(o["amount_untaxed"]), _m(o["amount_tax"]), _m(o["amount_total"]), est,
        escape(o["note"] or ""),
        ("<p><b>Accepted by %s</b> on %s</p>" % (escape(o["accepted_by"]), _lt(o["accepted_at"]))) if o["accepted_by"] else "")
    return _page(db, title, body)


def _words(n):
    """Rupees in words, Indian numbering (lakh, crore): 175400 -> "One lakh seventy-five thousand four hundred"."""
    ones = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
            "seventeen eighteen nineteen").split()
    tens = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()

    def two(x):
        return ones[x] if x < 20 else tens[x // 10] + ("-" + ones[x % 10] if x % 10 else "")

    def three(x):
        return (ones[x // 100] + " hundred" + (" " + two(x % 100) if x % 100 else "")) if x >= 100 else two(x)
    n = int(round(n))
    if n == 0:
        return "Zero"
    parts = []
    for size, name in ((10000000, "crore"), (100000, "lakh"), (1000, "thousand")):
        if n >= size:
            q = n // size
            parts.append("%s %s" % (three(q) if q < 1000 else _words(q).lower(), name))
            n %= size
    if n:
        parts.append(three(n))
    out = " ".join(parts)
    return out[0].upper() + out[1:]


@router.get("/invoice/{invoice_id}")
def invoice(invoice_id: int, request: Request, token: str = "", db=Depends(get_db)):
    """GST invoice for the customer (advance receipt, final tax invoice or service invoice)."""
    from ..subsidy import GST_CODES, GST_CODE_OF
    inv = db.get("invoices", invoice_id)
    if not inv:
        raise HTTPException(404, "Not found.")
    o = None
    if inv["order_id"]:
        o = _order_access(db, request, inv["order_id"], token, staff_areas=("orders", "tickets"))
    else:
        from ..access import can_read
        user = session_user(db, request)
        if not (user and ((user["role"] in STAFF and can_read(user, "tickets"))
                          or (user["role"] == "customer" and user.get("customer_id") == inv["customer_id"]))):
            raise HTTPException(403, "This link is not valid.")
    c = db.get("customers", inv["customer_id"])
    kind = rules.INVOICE_KIND.get(inv["kind"], "Invoice")
    title = "%s %s" % (kind, inv["ref"])
    # Place of supply: same state as our GSTIN -> CGST + SGST, another state -> IGST.
    ours = GST_CODES.get((db.setting("company_gstin") or "")[:2])
    theirs = (rules.lead_state(db, o) if o else None) or c.get("state") or ours
    same = (theirs or "").lower() == (ours or "").lower()
    code = GST_CODE_OF.get((theirs or "").lower(), "")
    tax = inv["amount_tax"]
    if same:
        half = rules.r2(tax / 2)
        tax_rows = ("<tr><td colspan='3' class='num'>CGST</td><td class='num'>%s</td></tr>"
                    "<tr><td colspan='3' class='num'>SGST</td><td class='num'>%s</td></tr>") % (_m(half), _m(tax - half))
    else:
        tax_rows = "<tr><td colspan='3' class='num'>IGST</td><td class='num'>%s</td></tr>" % _m(tax)
    project = db.val("SELECT project_ref FROM leads WHERE id = ?", o["lead_id"]) if o and o["lead_id"] else None
    detail = ""
    if inv["kind"] == "service":
        t = db.one("SELECT ref FROM tickets WHERE id = ?", inv["ticket_id"]) if inv["ticket_id"] else None
        desc = "Service visit and repair%s" % (" · request %s" % t["ref"] if t else "")
    elif inv["kind"] == "advance":
        desc = "Advance against order %s · %g kW %s rooftop solar system" % (
            o["ref"], o["kw"] or 0, "On-Grid" if o["system_type"] == "on_grid" else "Off-Grid")
    else:
        desc = "Order %s%s" % (o["ref"], " (balance)" if db.val(
            "SELECT COUNT(*) FROM invoices WHERE order_id = ? AND id < ? AND state != 'cancel' AND kind != 'service'",
            o["id"], inv["id"]) else "")
        lines = db.q("SELECT * FROM order_lines WHERE order_id = ? ORDER BY id", o["id"])
        earlier = db.q("SELECT ref, kind, amount_total FROM invoices WHERE order_id = ? AND id < ? AND state != 'cancel' "
                       "AND kind != 'service' ORDER BY id", o["id"], inv["id"])
        rows = "".join(
            "<tr><td>%s</td><td class='num'>%g</td><td class='num'>%s</td><td class='num'>%g%%</td><td class='num'>%s</td></tr>" % (
                escape(l["description"] or ""), l["qty"], _m(l["price_unit"]), l["tax_rate"], _m(l["subtotal"])) for l in lines)
        less = "".join("<tr><td colspan='4' class='num'>Less %s %s</td><td class='num'>− %s</td></tr>" % (
            escape(rules.INVOICE_KIND.get(e["kind"], "invoice").lower()), escape(e["ref"]), _m(e["amount_total"])) for e in earlier)
        detail = ("<h2>Order %s</h2><table><thead><tr><th>Description</th><th class='num'>Qty</th><th class='num'>Rate</th>"
                  "<th class='num'>GST</th><th class='num'>Amount</th></tr></thead><tbody>%s"
                  "<tr class='tot'><td colspan='4' class='num'>Order total (incl. GST)</td><td class='num'>%s</td></tr>%s"
                  "</tbody></table>") % (escape(o["ref"]), rows, _m(o["amount_total"]), less)
    balance = rules.r2(inv["amount_total"] - inv["amount_paid"])
    who = "<span class='muted'>Bill to</span><br><b>%s</b><br>%s<br>%s%s<br>%s" % (
        escape(c["name"]), escape(c.get("street") or ""), escape(c.get("city") or ""),
        (", " + escape(theirs)) if theirs else "", escape(c.get("phone") or ""))
    meta = "<span class='muted'>Invoice no.</span> <b>%s</b><br><span class='muted'>Date</span> %s<br>%s%s" \
           "<span class='muted'>Place of supply</span> %s%s" % (
               escape(inv["ref"]), escape(_day(inv["date"])),
               ("<span class='muted'>Order</span> %s<br>" % escape(o["ref"])) if o else "",
               ("<span class='muted'>Project</span> %s<br>" % escape(project)) if project else "",
               escape(theirs or "-"), (" (%s)" % code) if code else "")
    table = ("<h2>This invoice</h2><table><thead><tr><th>Description</th><th class='num'>Taxable value</th>"
             "<th class='num'>GST</th><th class='num'>Amount</th></tr></thead><tbody>"
             "<tr><td>%s</td><td class='num'>%s</td><td class='num'>%s</td><td class='num'>%s</td></tr>%s"
             "<tr class='grand'><td colspan='3' class='num'>Total</td><td class='num'>%s</td></tr></tbody></table>") % (
        escape(desc), _m(inv["amount_untaxed"]), _m(tax), _m(inv["amount_total"]), tax_rows, _m(inv["amount_total"]))
    paid = ("<div class='box'><div class='grid'><div>Paid</div><div><b>%s</b></div><div>Balance due</div>"
            "<div><b class='%s'>%s</b></div></div>%s</div>") % (
        _m(inv["amount_paid"]), "bad" if balance > 0.5 else "", _m(max(balance, 0)),
        "<div class='muted' style='margin-top:6px'>Pay the balance online from your SunPower account.</div>" if balance > 0.5 else "")
    note = ("GST at 18% on services." if inv["kind"] == "service"
            else "GST is charged at the rates on the order (5% on solar equipment, 18% on installation services).")
    body = ("%s<h1>%s</h1><div class='grid'><div>%s</div><div>%s</div></div>%s%s"
            "<p><span class='muted'>Amount in words:</span> <b>%s rupees only</b></p>%s"
            "<p class='muted' style='margin-top:24px'>This is a computer-generated invoice. %s</p>") % (
        "<p class='bad'><b>CANCELLED</b></p>" if inv["state"] == "cancel" else "",
        escape(title), who, meta, detail, table, _words(inv["amount_total"]), paid, note)
    return _page(db, title, body)


@router.get("/certificate/{job_id}")
def certificate(job_id: int, request: Request, token: str = "", db=Depends(get_db)):
    j = db.get("jobs", job_id)
    if not j:
        raise HTTPException(404, "Not found.")
    o = _order_access(db, request, j["order_id"], token, staff_areas=("orders", "jobs"))
    if j["state"] != "done":
        raise HTTPException(400, "The installation isn't completed yet.")
    c = db.get("customers", o["customer_id"])
    crew = ", ".join(r["name"] for r in db.q("SELECT u.name FROM job_techs jt JOIN users u ON u.id = jt.user_id WHERE jt.job_id = ?", job_id))
    ws = db.q("SELECT w.*, p.name AS product, s.name AS serial FROM warranties w JOIN products p ON p.id = w.product_id "
              "JOIN serials s ON s.id = w.serial_id WHERE w.order_id = ? ORDER BY p.category, s.name", o["id"])
    wrows = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
        escape(w["product"]), escape(w["serial"]), w["start_date"], w["end_date"]) for w in ws)
    checks = "".join("<li><b>%s</b> – %s</li>" % ("Done" if j[f] else "NOT DONE", escape(l)) for f, l in rules.CHECKLIST)
    sig = "<img src='%s' alt='signature'>" % escape(j["signature"]) if (j["signature"] or "").startswith("data:image/") else ""
    body = ("<h1 style='text-align:center'>Solar Installation &amp; Commissioning Certificate</h1>"
            "<p class='muted' style='text-align:center'>Job %s · Order %s</p><table>"
            "<tr><th>Customer</th><td>%s</td></tr><tr><th>Site address</th><td>%s, %s</td></tr>"
            "<tr><th>System installed</th><td>%g kW (%s)</td></tr><tr><th>Generation at test</th><td>%s kW</td></tr>"
            "<tr><th>Work started</th><td>%s</td></tr><tr><th>Work finished</th><td>%s</td></tr><tr><th>Crew</th><td>%s</td></tr>"
            "</table><h2>Installed equipment &amp; warranty</h2><table><thead><tr><th>Equipment</th><th>Serial / lot</th>"
            "<th>Warranty from</th><th>Warranty until</th></tr></thead><tbody>%s</tbody></table><h2>Checklist</h2><ul>%s</ul>"
            "<div class='sig'><div>Accepted by the customer:<br>%s<br><b>%s</b><br>%s</div>"
            "<div style='text-align:right'>For %s<br><br><br>Authorised signatory</div></div>") % (
        escape(j["ref"]), escape(o["ref"]), escape(c["name"]), escape(c.get("street") or ""), escape(c.get("city") or ""),
        j["kw_confirmed"] or 0, "On-Grid" if o["system_type"] == "on_grid" else "Off-Grid", j["generation_reading_kw"] or "–",
        _lt(j["site_start"]), _lt(j["site_end"]), escape(crew), wrows, checks, sig, escape(j["signed_by"] or ""),
        _lt(j["signed_on"]), escape(db.setting("company_name", "SunPower")))
    return _page(db, "Installation certificate %s" % j["ref"], body)


@router.get("/report")
def report(request: Request, period: str = "month", db=Depends(get_db)):
    user = session_user(db, request)
    if not user or user["role"] != "director":
        raise HTTPException(403, "Sign in as the Director to open this report.")
    d = dashboard_data(db, period if period in ("today", "week", "month", "year") else "month")
    k = d["kpi"]
    kv = [("New enquiries", k["leads_new"]), ("Orders won", "%s (%g kW)" % (k["orders_won"], k["kw_sold"])),
          ("Order value", rules.money(k["orders_value"])), ("Job profit", rules.money(k["profit"])),
          ("Invoiced", rules.money(k["invoiced"])), ("Collected", rules.money(k["collected"])),
          ("Installs done", k["installs_done"]), ("Installs pending", k["installs_pending"]),
          ("Open repairs", k["tickets_open"]), ("Subsidies pending", "%s (%s)" % (k["subsidy_pending"], rules.money(k["subsidy_amount"]))),
          ("Receivables", rules.money(k["receivable"])), ("Stock value", rules.money(k["stock_value"]))]
    cells = "".join("<tr><th>%s</th><td>%s</td></tr>" % (escape(a), escape(str(b))) for a, b in kv)
    jobs = "".join("<tr%s><td>%s</td><td>%s</td><td class='num'>%g</td><td class='num'>%s</td><td class='num'>%s</td>"
                   "<td class='num'>%s</td><td class='num'>%s</td><td class='num'>%.1f%%</td><td>%s</td></tr>" % (
                       " class='bad'" if j["profit"] < 0 else "", escape(j["name"]), escape(j["customer"]), j["kw"],
                       _m(j["revenue"]), _m(j["material"]), _m(j["labour"]), _m(j["profit"]), j["margin"], escape(j["pending"]))
                   for j in d["jobs"])
    tickets = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td class='num'>%s</td></tr>" % (
        escape(t["name"]), escape(t["customer"]), escape(t["product"]), escape(t["stage"]), "Yes" if t["warranty"] else "No", t["days"])
        for t in d["tickets"])
    body = ("<h1>Performance report</h1><p class='muted'>Period: %s</p><table>%s</table><h2>Profit by job</h2><table><thead><tr>"
            "<th>Order</th><th>Customer</th><th class='num'>kW</th><th class='num'>Revenue</th><th class='num'>Material</th>"
            "<th class='num'>Labour</th><th class='num'>Profit</th><th class='num'>Margin</th><th>Pending</th></tr></thead>"
            "<tbody>%s</tbody></table><h2>Open repairs</h2><table><thead><tr><th>Request</th><th>Customer</th><th>Equipment</th>"
            "<th>Stage</th><th>Warranty</th><th class='num'>Days open</th></tr></thead><tbody>%s</tbody></table>") % (
        escape(d["period_label"]), cells, jobs or "<tr><td colspan='9' class='muted'>No jobs in this period.</td></tr>",
        tickets or "<tr><td colspan='6' class='muted'>No open repairs.</td></tr>")
    return _page(db, "SunPower report – %s" % d["period_label"], body)
