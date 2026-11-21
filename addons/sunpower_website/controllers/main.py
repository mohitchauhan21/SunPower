import json
from urllib.parse import urlencode

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request

# Same rule of thumb as sunpower_solar.models.crm_lead._compute_recommended_kw
UNITS_PER_KW_MONTH = 120.0
AVG_TARIFF_INR = 8.0
MIN_KW, MAX_KW = 1, 5
# Indicative figures shown on the estimate page (not a quotation)
COST_PER_KW_INR = 65000.0
ROOF_SQFT_PER_KW = 100.0
AI_SERVICE_URL = "http://localhost:8000"


def _float(v):
    try:
        return max(float(v or 0), 0.0)
    except (TypeError, ValueError):
        return 0.0


def pm_surya_ghar_subsidy(kw):
    """₹30k/kW for the first 2 kW, ₹18k for the 3rd kW, capped at ₹78k."""
    return min(kw, 2) * 30000 + (18000 if kw >= 3 else 0)


def solar_estimate(units=0.0, bill=0.0):
    units = units or (bill / AVG_TARIFF_INR if bill else 0.0)
    if not units:
        return None
    # half-up rounding so it matches Math.round in estimate.js
    kw = int(min(max(int(units / UNITS_PER_KW_MONTH + 0.5), MIN_KW), MAX_KW))
    generation = kw * UNITS_PER_KW_MONTH
    monthly_saving = min(generation, units) * AVG_TARIFF_INR
    cost = kw * COST_PER_KW_INR
    subsidy = pm_surya_ghar_subsidy(kw)
    net = cost - subsidy
    return {
        "units": round(units),
        "kw": kw,
        "system_type": "on_grid",
        "generation": round(generation),
        "monthly_saving": round(monthly_saving),
        "yearly_saving": round(monthly_saving * 12),
        "cost": round(cost),
        "subsidy": round(subsidy),
        "net_cost": round(net),
        "payback_years": round(net / (monthly_saving * 12), 1) if monthly_saving else 0,
        "roof_sqft": round(kw * ROOF_SQFT_PER_KW),
    }


class SunpowerWebsite(http.Controller):

    # ------------------------------------------------------------ estimate
    @http.route("/solar/estimate", type="http", auth="public", website=True,
                sitemap=True)
    def solar_estimate_page(self, units=None, bill=None, **kw):
        est = solar_estimate(_float(units), _float(bill))
        return request.render("sunpower_website.estimate_page", {
            "est": est,
            "units": units or "",
            "bill": bill or "",
            "ai_url": AI_SERVICE_URL,
            "cfg_json": json.dumps({
                "unitsPerKw": UNITS_PER_KW_MONTH, "tariff": AVG_TARIFF_INR,
                "minKw": MIN_KW, "maxKw": MAX_KW, "costPerKw": COST_PER_KW_INR,
                "roofPerKw": ROOF_SQFT_PER_KW,
            }),
        })


class SunpowerCustomerPortal(http.Controller):

    def _partner(self):
        return request.env.user.partner_id.commercial_partner_id

    @http.route("/my/solar", type="http", auth="user", website=True)
    def my_solar(self, submitted=None, **kw):
        partner = self._partner()
        env = request.env
        jobs = env["project.task"].sudo().search([
            ("is_installation", "=", True),
            "|", ("partner_id", "child_of", partner.id),
            ("sale_order_id.partner_id", "child_of", partner.id),
        ], order="installation_date desc, id desc")
        orders = env["sale.order"].sudo().search([
            ("partner_id", "child_of", partner.id), ("state", "=", "sale"),
        ], order="date_order desc")
        tickets = env["solar.service.ticket"].sudo().search([
            ("partner_id", "child_of", partner.id),
        ])
        warranties = env["solar.warranty"].sudo().search([
            ("partner_id", "child_of", partner.id),
        ])
        for t in tickets:
            t._portal_ensure_token()
        return request.render("sunpower_website.portal_my_solar", {
            "partner": partner, "jobs": jobs, "orders": orders,
            "tickets": tickets, "warranties": warranties,
            "submitted": submitted, "page_name": "my_solar",
        })

    @http.route("/my/solar/complaint", type="http", auth="user", website=True,
                methods=["POST"])
    def my_solar_complaint(self, description=None, fault_code=None, warranty_id=None,
                           **kw):
        description = (description or "").strip()
        if not description:
            return request.redirect("/my/solar?submitted=error#complaint")
        partner = self._partner()
        vals = {
            "partner_id": request.env.user.partner_id.id,
            "description": description,
            "fault_code": (fault_code or "").strip() or False,
        }
        if warranty_id and warranty_id.isdigit():
            warranty = request.env["solar.warranty"].sudo().search([
                ("id", "=", int(warranty_id)), ("partner_id", "child_of", partner.id),
            ], limit=1)
            if warranty:
                vals["lot_id"] = warranty.lot_id.id
        ticket = request.env["solar.service.ticket"].sudo().create(vals)
        ticket.message_post(body=_("Complaint raised by the customer from the website."))
        return request.redirect("/my/solar?submitted=%s#tickets" % ticket.id)


class SunpowerTechnician(http.Controller):

    def _check_internal(self):
        return request.env.user._is_internal()

    @http.route("/technician", type="http", auth="user", website=True)
    def technician_home(self, msg=None, err=None, **kw):
        if not self._check_internal():
            return request.redirect("/my/solar")
        uid = request.env.uid
        jobs = request.env["project.task"].search([
            ("is_installation", "=", True), ("user_ids", "in", uid),
            ("installation_state", "!=", "done"),
        ], order="installation_date asc, id asc")
        done_jobs = request.env["project.task"].search([
            ("is_installation", "=", True), ("user_ids", "in", uid),
            ("installation_state", "=", "done"),
        ], order="site_end desc", limit=5)
        tickets = request.env["solar.service.ticket"].search([
            ("user_id", "=", uid), ("stage", "not in", ("closed", "cancel")),
        ])
        return request.render("sunpower_website.technician_page", {
            "jobs": jobs, "done_jobs": done_jobs, "tickets": tickets,
            "msg": msg, "err": err,
        })

    @http.route("/technician/job/<int:task_id>/start", type="http", auth="user",
                website=True, methods=["POST"])
    def technician_start(self, task_id, **kw):
        if not self._check_internal():
            return request.redirect("/my/solar")
        task = request.env["project.task"].browse(task_id).exists()
        if not task or request.env.uid not in task.user_ids.ids:
            return request.redirect("/technician?err=Job+not+found")
        try:
            task.action_start_work()
        except UserError as e:
            return request.redirect("/technician?" + urlencode({"err": e.args[0]}))
        return request.redirect("/technician?msg=Job+%s+started" % task.id)
