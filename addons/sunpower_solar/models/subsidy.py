from odoo import _, api, fields, models


class SolarSubsidyApplication(models.Model):
    _name = "solar.subsidy.application"
    _description = "Government Subsidy Application"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default=lambda s: _("New"), readonly=True, copy=False)
    sale_order_id = fields.Many2one("sale.order", "Job", required=True,
                                    ondelete="cascade")
    partner_id = fields.Many2one(related="sale_order_id.partner_id", store=True)
    system_kw = fields.Float(related="sale_order_id.solar_kw", store=True)
    scheme = fields.Char(default="PM Surya Ghar Muft Bijli Yojana")
    portal_application_no = fields.Char("Portal Application No.", tracking=True)
    discom = fields.Char(related="sale_order_id.opportunity_id.discom")
    consumer_no = fields.Char(related="sale_order_id.opportunity_id.consumer_no")
    state = fields.Selection([
        ("draft", "Documents Pending"),
        ("applied", "Applied on Portal"),
        ("inspection", "DISCOM Inspection"),
        ("approved", "Approved"),
        ("disbursed", "Disbursed"),
        ("rejected", "Rejected"),
    ], default="draft", tracking=True, group_expand="_group_expand_state")
    applied_on = fields.Date(tracking=True)
    inspection_on = fields.Date(tracking=True)
    disbursed_on = fields.Date(tracking=True)
    currency_id = fields.Many2one("res.currency",
                                  default=lambda s: s.env.company.currency_id)
    amount_expected = fields.Monetary()
    amount_received = fields.Monetary(tracking=True)
    document_ids = fields.Many2many("ir.attachment", string="Documents")
    doc_aadhaar = fields.Boolean("ID proof")
    doc_bill = fields.Boolean("Latest electricity bill")
    doc_bank = fields.Boolean("Cancelled cheque / bank details")
    doc_photo = fields.Boolean("Installation photo with customer")
    doc_net_meter = fields.Boolean("Net-meter commissioning report")
    days_pending = fields.Integer(compute="_compute_days_pending")

    @api.model
    def _group_expand_state(self, states, domain):
        return [s for s, _l in self._fields["state"].selection]

    @api.model
    def _expected_subsidy(self, kw):
        """PM Surya Ghar central subsidy: ₹30k/kW for first 2 kW, ₹18k for the 3rd,
        capped at ₹78,000."""
        kw = kw or 0
        return min(30000 * min(kw, 2) + 18000 * max(min(kw, 3) - 2, 0), 78000)

    def _compute_days_pending(self):
        today = fields.Date.context_today(self)
        for s in self:
            s.days_pending = (today - s.applied_on).days \
                if s.applied_on and s.state not in ("disbursed", "rejected") else 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "solar.subsidy.application")
        return super().create(vals_list)

    def action_apply(self):
        self.write({"state": "applied", "applied_on": fields.Date.context_today(self)})

    def action_inspection(self):
        self.write({"state": "inspection",
                    "inspection_on": fields.Date.context_today(self)})

    def action_approve(self):
        self.write({"state": "approved"})

    def action_disburse(self):
        for s in self:
            s.write({"state": "disbursed",
                     "disbursed_on": fields.Date.context_today(s),
                     "amount_received": s.amount_received or s.amount_expected})

    def action_reject(self):
        self.write({"state": "rejected"})
