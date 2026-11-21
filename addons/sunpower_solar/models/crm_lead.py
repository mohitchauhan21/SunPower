from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .product import SYSTEM_TYPES

AVG_TARIFF_INR = 8.0          # ₹ per kWh, used when only the bill amount is known
UNITS_PER_KW_MONTH = 120.0    # ~4 kWh/kW/day in India


class CrmLead(models.Model):
    _inherit = "crm.lead"

    enquiry_channel = fields.Selection([
        ("web", "Website Form"), ("whatsapp", "WhatsApp"), ("call", "Phone Call"),
        ("walkin", "Walk-in"), ("referral", "Referral"),
    ], default="call", tracking=True)
    requested_kw = fields.Float("Requested Size (kW)", tracking=True)
    system_type = fields.Selection(SYSTEM_TYPES, default="on_grid", tracking=True)
    subsidy_requested = fields.Boolean("Wants Govt. Subsidy")

    # Phone screening
    roof_area_sqft = fields.Float("Shadow-free Roof Area (sq ft)")
    monthly_bill = fields.Float("Monthly Electricity Bill (₹)")
    monthly_units = fields.Float("Monthly Units (kWh)")
    grid_suitable = fields.Selection([("yes", "Suitable"), ("no", "Not Suitable"),
                                      ("unknown", "To Check")], default="unknown",
                                     string="Grid Connection")
    discom = fields.Char("Electricity Board (DISCOM)")
    consumer_no = fields.Char("Consumer No.")
    bill_attachment = fields.Binary("Electricity Bill", attachment=True)
    bill_filename = fields.Char()
    recommended_kw = fields.Float(compute="_compute_recommended_kw",
                                  string="Suggested kW (from bill)")
    screening_ok = fields.Boolean(compute="_compute_screening_ok")

    survey_ids = fields.One2many("solar.site.survey", "lead_id", "Surveys")
    survey_count = fields.Integer(compute="_compute_survey_count")
    survey_state = fields.Selection([
        ("none", "No Survey"), ("scheduled", "Survey Scheduled"), ("done", "Visited"),
        ("approved", "Survey Approved"), ("rejected", "Survey Rejected"),
    ], compute="_compute_survey_state", store=True, string="Survey")
    approved_survey_id = fields.Many2one("solar.site.survey",
                                         compute="_compute_survey_state", store=True)

    @api.depends("monthly_units", "monthly_bill")
    def _compute_recommended_kw(self):
        for lead in self:
            units = lead.monthly_units or (lead.monthly_bill / AVG_TARIFF_INR)
            kw = round(units / UNITS_PER_KW_MONTH) if units else 0
            lead.recommended_kw = min(max(kw, 1), 5) if units else 0

    @api.depends("roof_area_sqft", "monthly_bill", "monthly_units", "grid_suitable")
    def _compute_screening_ok(self):
        for lead in self:
            lead.screening_ok = bool(
                lead.roof_area_sqft and (lead.monthly_bill or lead.monthly_units)
                and lead.grid_suitable == "yes")

    @api.depends("survey_ids.state")
    def _compute_survey_state(self):
        order = ["rejected", "scheduled", "done", "approved"]
        for lead in self:
            surveys = lead.survey_ids
            approved = surveys.filtered(lambda s: s.state == "approved")[:1]
            lead.approved_survey_id = approved
            if not surveys:
                lead.survey_state = "none"
            else:
                lead.survey_state = max(surveys.mapped("state"), key=order.index)

    def _compute_survey_count(self):
        for lead in self:
            lead.survey_count = len(lead.survey_ids)

    # ------------------------------------------------------------------ actions
    def action_schedule_survey(self):
        self.ensure_one()
        if not self.screening_ok:
            raise UserError(_("Complete the phone screening first: shadow-free roof "
                              "area, monthly bill/units and a suitable grid connection."))
        survey = self.env["solar.site.survey"].create({
            "lead_id": self.id,
            "recommended_kw": self.requested_kw or self.recommended_kw,
            "usable_area_sqft": self.roof_area_sqft,
        })
        return {
            "type": "ir.actions.act_window", "res_model": "solar.site.survey",
            "res_id": survey.id, "view_mode": "form", "target": "current",
        }

    def action_view_surveys(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Surveys"),
            "res_model": "solar.site.survey", "view_mode": "list,form",
            "domain": [("lead_id", "=", self.id)],
            "context": {"default_lead_id": self.id},
        }

    def _solar_quotation_template(self):
        self.ensure_one()
        kw = self.approved_survey_id.recommended_kw or self.requested_kw
        if not kw:
            return self.env["sale.order.template"]
        return self.env["sale.order.template"].search([
            ("solar_kw", "=", round(kw)),
            ("solar_system_type", "=", self.system_type or "on_grid"),
        ], limit=1)

    def _prepare_opportunity_quotation_context(self):
        ctx = super()._prepare_opportunity_quotation_context()
        template = self._solar_quotation_template()
        if template:
            ctx["default_sale_order_template_id"] = template.id
        if self.approved_survey_id:
            ctx["default_survey_id"] = self.approved_survey_id.id
        return ctx

    def action_new_quotation(self):
        for lead in self:
            if lead.type == "opportunity" and not lead.approved_survey_id:
                raise UserError(_("A quotation can only be prepared after the roof "
                                  "survey is approved."))
        return super().action_new_quotation()

    # ------------------------------------------------------------------ intake
    @api.model
    def _solar_pick_salesperson(self, team):
        """Least-loaded salesperson of the team (simple round robin)."""
        members = team.member_ids or self.env.user
        counts = {u.id: self.search_count([("user_id", "=", u.id), ("active", "=", True),
                                           ("stage_id.is_won", "=", False)])
                  for u in members}
        return min(members, key=lambda u: counts[u.id])

    @api.model
    def solar_create_enquiry(self, vals, channel="web"):
        """Single entry point for web form / WhatsApp / AI intake so that an
        enquiry is never lost: lead + salesperson + call activity."""
        team = self.env.ref("sales_team.team_sales_department",
                            raise_if_not_found=False)
        vals = dict(vals, enquiry_channel=channel, type="opportunity")
        if team:
            vals.setdefault("team_id", team.id)
            vals.setdefault("user_id", self._solar_pick_salesperson(team).id)
        lead = self.create(vals)
        lead.activity_schedule(
            "mail.mail_activity_data_call", date_deadline=fields.Date.today(),
            summary=_("Call within 2 hours: screen roof, bill and grid"),
            user_id=lead.user_id.id or self.env.user.id)
        return lead
