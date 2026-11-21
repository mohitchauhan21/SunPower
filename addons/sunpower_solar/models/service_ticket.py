from odoo import _, api, fields, models
from odoo.exceptions import UserError

STAGES = [
    ("new", "New"),
    ("diagnosed", "Diagnosed"),
    ("repair", "Repair in Progress"),
    ("awaiting", "Awaiting Customer Confirmation"),
    ("closed", "Closed"),
    ("cancel", "Cancelled"),
]


class SolarServiceTicket(models.Model):
    _name = "solar.service.ticket"
    _description = "Service Ticket"
    _inherit = ["mail.thread", "mail.activity.mixin", "portal.mixin"]
    _order = "priority desc, reported_on desc, id desc"

    name = fields.Char(default=lambda s: _("New"), readonly=True, copy=False)
    stage = fields.Selection(STAGES, default="new", tracking=True, required=True,
                             group_expand="_group_expand_stage")
    priority = fields.Selection([("0", "Normal"), ("1", "High"), ("2", "Urgent")],
                                default="0")
    partner_id = fields.Many2one("res.partner", "Customer", required=True, tracking=True)
    phone = fields.Char(related="partner_id.phone")
    lot_id = fields.Many2one("stock.lot", "Serial Number", tracking=True,
                             domain="[('warranty_ids', '!=', False)]")
    product_id = fields.Many2one("product.product", compute="_compute_from_lot",
                                 store=True, readonly=False)
    warranty_id = fields.Many2one("solar.warranty", compute="_compute_from_lot",
                                  store=True)
    warranty_end = fields.Date(related="warranty_id.end_date")
    sale_order_id = fields.Many2one("sale.order", "Original Job",
                                    compute="_compute_from_lot", store=True,
                                    readonly=False)
    under_warranty = fields.Boolean(compute="_compute_under_warranty", store=True)
    reported_on = fields.Datetime(default=fields.Datetime.now, required=True)
    closed_on = fields.Datetime(readonly=True)
    days_open = fields.Integer(compute="_compute_days_open")
    user_id = fields.Many2one("res.users", "Technician", tracking=True)
    fault_code = fields.Char()
    description = fields.Text("Complaint")
    resolution = fields.Html()
    ai_diagnosis = fields.Html("AI Diagnosis", readonly=True)
    photo_ids = fields.Many2many("ir.attachment", "solar_ticket_photo_rel", "ticket_id",
                                 "attachment_id", string="Photos")

    line_ids = fields.One2many("solar.service.ticket.line", "ticket_id", "Parts")
    labour_hours = fields.Float()
    labour_rate = fields.Monetary(default=500.0)
    currency_id = fields.Many2one("res.currency",
                                  default=lambda s: s.env.company.currency_id)
    parts_price = fields.Monetary(compute="_compute_amounts", store=True)
    repair_cost = fields.Monetary("Cost to Company", compute="_compute_amounts",
                                  store=True)
    customer_charge = fields.Monetary(compute="_compute_amounts", store=True)
    invoice_id = fields.Many2one("account.move", readonly=True, copy=False)
    customer_confirmed = fields.Boolean(readonly=True, tracking=True)

    # ----------------------------------------------------------------- computes
    @api.model
    def _group_expand_stage(self, stages, domain):
        return [s for s, _l in STAGES if s != "cancel"]

    @api.depends("lot_id")
    def _compute_from_lot(self):
        for t in self:
            w = t.lot_id.warranty_ids[:1]
            t.warranty_id = w
            if w:
                t.product_id = w.product_id
                t.sale_order_id = w.sale_order_id
                t.partner_id = w.partner_id

    @api.depends("warranty_id.end_date", "reported_on")
    def _compute_under_warranty(self):
        for t in self:
            t.under_warranty = bool(t.warranty_id and t.reported_on and
                                    t.warranty_id.is_active_on(t.reported_on.date()))

    @api.depends("line_ids.subtotal", "line_ids.cost", "labour_hours", "labour_rate",
                 "under_warranty")
    def _compute_amounts(self):
        for t in self:
            parts = sum(t.line_ids.mapped("subtotal"))
            labour = t.labour_hours * t.labour_rate
            t.parts_price = parts
            t.repair_cost = sum(t.line_ids.mapped("cost")) + labour
            t.customer_charge = 0.0 if t.under_warranty else parts + labour

    def _compute_days_open(self):
        now = fields.Datetime.now()
        for t in self:
            end = t.closed_on or now
            t.days_open = (end - t.reported_on).days if t.reported_on else 0

    def _compute_access_url(self):
        super()._compute_access_url()
        for t in self:
            t.access_url = "/my/solar-ticket/%s" % t.id

    @api.onchange("partner_id")
    def _onchange_partner(self):
        if self.partner_id and self.lot_id and \
                self.lot_id.solar_partner_id != self.partner_id:
            self.lot_id = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("solar.service.ticket")
        return super().create(vals_list)

    # ----------------------------------------------------------------- flow
    def action_diagnose(self):
        self.write({"stage": "diagnosed"})

    def action_start_repair(self):
        self.write({"stage": "repair"})

    def action_resolve(self):
        """Repair done: bill automatically when out of warranty, then ask the
        customer to confirm everything works."""
        for t in self:
            if not t.resolution:
                raise UserError(_("Describe what was repaired/replaced first."))
            if not t.under_warranty and t.customer_charge and not t.invoice_id:
                t._create_invoice()
            t.stage = "awaiting"
            t._send_confirmation_request()
            if t.sale_order_id:
                t.sale_order_id._solar_refresh_job_financials()
        return True

    def _create_invoice(self):
        self.ensure_one()
        lines = [(0, 0, {
            "product_id": l.product_id.id, "name": l.product_id.display_name,
            "quantity": l.quantity, "price_unit": l.price_unit,
        }) for l in self.line_ids]
        if self.labour_hours:
            lines.append((0, 0, {
                "name": _("Service labour (%s h) – %s", self.labour_hours, self.name),
                "quantity": self.labour_hours, "price_unit": self.labour_rate,
            }))
        move = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.partner_id.id,
            "invoice_origin": self.name,
            "invoice_line_ids": lines,
        })
        move.action_post()
        self.invoice_id = move
        self.message_post(body=_("Out of warranty: invoice %s created automatically.",
                                 move._get_html_link()))

    def _send_confirmation_request(self):
        for t in self:
            url = t.get_base_url() + t.get_portal_url()
            t.message_post(
                body=_("Repair completed. Please confirm everything works: "
                       "<a href='%(u)s'>%(u)s</a>", u=url),
                partner_ids=t.partner_id.ids, subtype_xmlid="mail.mt_comment")

    def action_customer_confirm(self):
        self.write({"stage": "closed", "customer_confirmed": True,
                    "closed_on": fields.Datetime.now()})
        for t in self:
            t.message_post(body=_("Customer confirmed the system works. Ticket closed."))

    def action_reopen(self):
        self.write({"stage": "repair", "customer_confirmed": False, "closed_on": False})

    def action_cancel(self):
        self.write({"stage": "cancel"})

    def action_view_invoice(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": "account.move",
                "res_id": self.invoice_id.id, "view_mode": "form"}


class SolarServiceTicketLine(models.Model):
    _name = "solar.service.ticket.line"
    _description = "Service Ticket Part"

    ticket_id = fields.Many2one("solar.service.ticket", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", required=True)
    quantity = fields.Float(default=1.0)
    price_unit = fields.Float("Unit Price")
    new_lot_name = fields.Char("New Serial (if replaced)")
    subtotal = fields.Float(compute="_compute_subtotal", store=True)
    cost = fields.Float(compute="_compute_subtotal", store=True)

    @api.onchange("product_id")
    def _onchange_product(self):
        self.price_unit = self.product_id.lst_price

    @api.depends("quantity", "price_unit", "product_id.standard_price")
    def _compute_subtotal(self):
        for l in self:
            l.subtotal = l.quantity * l.price_unit
            l.cost = l.quantity * l.product_id.standard_price
