import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .crm_lead import AVG_TARIFF_INR
from .product import SYSTEM_TYPES

_logger = logging.getLogger(__name__)

PVGIS_URL = "https://re.jrc.ec.europa.eu/api/v5_2/PVcalc"
# PVGIS aspect: 0 = south, 90 = west, -90 = east, 180 = north
ASPECT = {"S": 0, "SW": 45, "W": 90, "NW": 135, "N": 180, "NE": -135, "E": -90, "SE": -45}
DEFAULT_LATLON = (23.0225, 72.5714)       # Ahmedabad, used when survey has no GPS
FALLBACK_KWH_PER_KW = 1450.0              # typical Indian yield per year


class SaleOrderTemplate(models.Model):
    _inherit = "sale.order.template"

    solar_kw = fields.Float("System Size (kW)")
    solar_system_type = fields.Selection(SYSTEM_TYPES, "System Type")


class SaleOrder(models.Model):
    _inherit = "sale.order"

    survey_id = fields.Many2one("solar.site.survey", "Approved Survey",
                                domain="[('state', '=', 'approved')]")
    is_solar_job = fields.Boolean(compute="_compute_solar_info", store=True)
    solar_kw = fields.Float("System kW", compute="_compute_solar_info", store=True)
    solar_system_type = fields.Selection(SYSTEM_TYPES, compute="_compute_solar_info",
                                         store=True)
    est_kwh_year = fields.Float("Est. Generation (kWh/yr)")
    est_savings_year = fields.Monetary("Est. Savings (₹/yr)")
    est_payback_years = fields.Float("Est. Payback (yrs)", digits=(4, 1))
    est_source = fields.Char("Estimate Source")

    subsidy_ids = fields.One2many("solar.subsidy.application", "sale_order_id")
    warranty_ids = fields.One2many("solar.warranty", "sale_order_id")
    ticket_ids = fields.One2many("solar.service.ticket", "sale_order_id")
    warranty_count = fields.Integer(compute="_compute_solar_counts")
    ticket_count = fields.Integer(compute="_compute_solar_counts")

    # Job financials (refreshed by _solar_refresh_job_financials / cron)
    job_invoiced = fields.Monetary("Invoiced", readonly=True)
    job_collected = fields.Monetary("Collected", readonly=True)
    job_material_cost = fields.Monetary("Material Cost", readonly=True)
    job_labour_cost = fields.Monetary("Labour Cost", readonly=True)
    job_labour_hours = fields.Float("Technician Hours", readonly=True)
    job_repair_cost = fields.Monetary("Warranty Repair Cost", readonly=True)
    job_profit = fields.Monetary("Job Profit", readonly=True)
    job_margin = fields.Float("Margin %", readonly=True, digits=(5, 1))
    job_stage = fields.Selection([
        ("quote", "Quotation"), ("confirmed", "Confirmed – awaiting dispatch"),
        ("dispatched", "Dispatched – awaiting install"), ("installed", "Installed"),
        ("closed", "Completed & Paid"),
    ], readonly=True, default="quote")
    job_pending_steps = fields.Char("Pending Steps", readonly=True)

    @api.depends("order_line.product_id")
    def _compute_solar_info(self):
        for order in self:
            kit = order.order_line.filtered(
                lambda l: l.product_id.product_tmpl_id.is_solar_kit)[:1]
            tmpl = kit.product_id.product_tmpl_id
            order.is_solar_job = bool(kit)
            order.solar_kw = tmpl.solar_kw * (kit.product_uom_qty or 1) if kit else 0
            order.solar_system_type = tmpl.solar_system_type if kit else False

    def _compute_solar_counts(self):
        for order in self:
            order.warranty_count = len(order.warranty_ids)
            order.ticket_count = len(order.ticket_ids)

    @api.onchange("opportunity_id")
    def _onchange_opportunity_survey(self):
        if self.opportunity_id.approved_survey_id:
            self.survey_id = self.opportunity_id.approved_survey_id

    # ----------------------------------------------------------- survey gating
    def _solar_check_survey(self):
        if self.env.context.get("solar_skip_survey_check"):
            return
        for order in self.filtered("is_solar_job"):
            survey = order.survey_id or order.opportunity_id.approved_survey_id
            if not survey or survey.state != "approved":
                raise UserError(_(
                    "%(so)s: the customer can only receive a quote after the roof "
                    "survey is approved.", so=order.name))
            if not order.survey_id:
                order.survey_id = survey

    def action_quotation_send(self):
        self._solar_check_survey()
        return super().action_quotation_send()

    def action_confirm(self):
        self._solar_check_survey()
        res = super().action_confirm()
        self._solar_after_confirm()
        return res

    def _solar_after_confirm(self):
        for order in self.filtered("is_solar_job"):
            # crew schedule: flag the tasks created by sale_project
            tasks = order.tasks_ids
            tasks.write({
                "is_installation": True,
                "installation_kw_planned": order.solar_kw,
                "installation_date": order.commitment_date or fields.Datetime.now(),
            })
            # subsidy paperwork starts automatically
            if order.opportunity_id.subsidy_requested and not order.subsidy_ids:
                self.env["solar.subsidy.application"].create({
                    "sale_order_id": order.id,
                    "amount_expected": self.env["solar.subsidy.application"]
                    ._expected_subsidy(order.solar_kw),
                })
            pickings = order.picking_ids.filtered(lambda p: p.state not in
                                                  ("done", "cancel"))
            order.message_post(body=_(
                "Order confirmed: %(p)s delivery order(s) sent to the warehouse and "
                "%(t)s installation job(s) put on the crew schedule.",
                p=len(pickings), t=len(tasks)))
        self._solar_refresh_job_financials()

    # ----------------------------------------------------------- PVGIS estimate
    def action_compute_generation(self):
        for order in self:
            kw = order.solar_kw or 1.0
            survey = order.survey_id
            lat = survey.latitude or DEFAULT_LATLON[0]
            lon = survey.longitude or DEFAULT_LATLON[1]
            params = {
                "lat": lat, "lon": lon, "peakpower": kw, "loss": 14,
                "angle": survey.roof_tilt or 20,
                "aspect": ASPECT.get(survey.roof_direction or "S", 0),
                "outputformat": "json",
            }
            try:
                r = requests.get(PVGIS_URL, params=params, timeout=12)
                r.raise_for_status()
                kwh = r.json()["outputs"]["totals"]["fixed"]["E_y"]
                source = "PVGIS (EU JRC) for %.4f, %.4f" % (lat, lon)
            except Exception as e:  # offline / API down -> rule of thumb
                _logger.warning("PVGIS failed: %s", e)
                kwh = kw * FALLBACK_KWH_PER_KW
                source = "Rule of thumb (%d kWh/kW/yr)" % FALLBACK_KWH_PER_KW
            savings = kwh * AVG_TARIFF_INR
            order.write({
                "est_kwh_year": round(kwh),
                "est_savings_year": round(savings),
                "est_payback_years": order.amount_total / savings if savings else 0,
                "est_source": source,
            })
        return True

    # ----------------------------------------------------------- financials
    def _solar_refresh_job_financials(self):
        Timesheet = self.env["account.analytic.line"].sudo()
        for order in self.filtered("is_solar_job"):
            invoices = order.invoice_ids.filtered(lambda m: m.state == "posted")
            out = invoices.filtered(lambda m: m.move_type == "out_invoice")
            refunds = invoices.filtered(lambda m: m.move_type == "out_refund")
            invoiced = sum(out.mapped("amount_untaxed")) - sum(refunds.mapped("amount_untaxed"))
            collected = sum(m.amount_total - m.amount_residual for m in out)

            material = 0.0
            for move in order.picking_ids.move_ids.filtered(lambda m: m.state == "done"):
                sign = -1 if move.picking_code == "incoming" else 1
                material += sign * move.quantity * move.product_id.standard_price

            lines = Timesheet.search([("task_id", "in", order.tasks_ids.ids)]) \
                if order.tasks_ids else Timesheet
            labour = -sum(lines.mapped("amount"))
            hours = sum(lines.mapped("unit_amount"))
            repair = sum(order.ticket_ids.filtered("under_warranty").mapped("repair_cost"))

            revenue = order.amount_untaxed if order.state == "sale" else 0.0
            profit = revenue - material - labour - repair

            tasks = order.tasks_ids.filtered("is_installation")
            delivered = order.picking_ids and all(
                p.state in ("done", "cancel") for p in order.picking_ids)
            installed = tasks and all(t.installation_state == "done" for t in tasks)
            paid = out and all(m.payment_state in ("paid", "in_payment") for m in out) \
                and invoiced >= order.amount_untaxed - 1
            pending = []
            if order.state != "sale":
                stage = "quote"
            else:
                if not delivered:
                    pending.append(_("Dispatch"))
                if not installed:
                    pending.append(_("Installation"))
                if not paid:
                    pending.append(_("Invoice/Payment"))
                if order.subsidy_ids.filtered(lambda s: s.state not in
                                              ("disbursed", "rejected")):
                    pending.append(_("Subsidy"))
                stage = ("closed" if not pending or pending == [_("Subsidy")]
                         else "installed" if installed
                         else "dispatched" if delivered else "confirmed")
            order.write({
                "job_invoiced": invoiced, "job_collected": collected,
                "job_material_cost": material, "job_labour_cost": labour,
                "job_labour_hours": hours, "job_repair_cost": repair,
                "job_profit": profit,
                "job_margin": (profit / revenue * 100) if revenue else 0.0,
                "job_stage": stage, "job_pending_steps": ", ".join(pending),
            })

    @api.model
    def _cron_refresh_job_financials(self):
        self.search([("state", "=", "sale"), ("is_solar_job", "=", True)]) \
            ._solar_refresh_job_financials()

    def action_refresh_financials(self):
        self._solar_refresh_job_financials()

    def action_view_warranties(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Warranties"),
            "res_model": "solar.warranty", "view_mode": "list,form",
            "domain": [("sale_order_id", "=", self.id)],
        }

    def action_view_tickets(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Service Tickets"),
            "res_model": "solar.service.ticket", "view_mode": "list,form",
            "domain": [("sale_order_id", "=", self.id)],
            "context": {"default_sale_order_id": self.id,
                        "default_partner_id": self.partner_id.id},
        }
