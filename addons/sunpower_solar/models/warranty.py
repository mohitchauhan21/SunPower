from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class SolarWarranty(models.Model):
    _name = "solar.warranty"
    _description = "Equipment Warranty (per serial / lot)"
    _inherit = ["mail.thread"]
    _order = "start_date desc, id desc"
    _rec_name = "serial"

    lot_id = fields.Many2one("stock.lot", "Serial / Lot", required=True, index=True)
    serial = fields.Char(related="lot_id.name", store=True, index=True)
    product_id = fields.Many2one("product.product", required=True)
    product_categ_id = fields.Many2one(related="product_id.categ_id", store=True)
    partner_id = fields.Many2one("res.partner", "Customer", required=True, index=True)
    phone = fields.Char(related="partner_id.phone")
    sale_order_id = fields.Many2one("sale.order", "Sales Order")
    picking_id = fields.Many2one("stock.picking", "Delivery")
    start_date = fields.Date(required=True)
    months = fields.Integer("Warranty (months)", required=True)
    end_date = fields.Date(compute="_compute_end_date", store=True)
    state = fields.Selection([("active", "Under Warranty"), ("expired", "Expired")],
                             compute="_compute_state", search="_search_state")
    days_left = fields.Integer(compute="_compute_state")
    ticket_ids = fields.One2many("solar.service.ticket", "warranty_id", "Tickets")

    _sql_constraints = [
        ("lot_unique", "unique(lot_id, partner_id)",
         "This serial already has a warranty for this customer."),
    ]

    @api.depends("start_date", "months")
    def _compute_end_date(self):
        for w in self:
            w.end_date = (w.start_date + relativedelta(months=w.months)
                          if w.start_date else False)

    def _compute_state(self):
        today = fields.Date.context_today(self)
        for w in self:
            w.days_left = (w.end_date - today).days if w.end_date else 0
            w.state = "active" if w.end_date and w.end_date >= today else "expired"

    def _search_state(self, operator, value):
        today = fields.Date.context_today(self)
        active = (value == "active") == (operator == "=")
        return [("end_date", ">=" if active else "<", today)]

    def is_active_on(self, date):
        self.ensure_one()
        return bool(self.end_date and self.start_date <= date <= self.end_date)
