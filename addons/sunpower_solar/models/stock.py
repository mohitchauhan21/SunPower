from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockLot(models.Model):
    _inherit = "stock.lot"

    warranty_ids = fields.One2many("solar.warranty", "lot_id", "Warranties")
    solar_partner_id = fields.Many2one("res.partner", "Installed At",
                                       compute="_compute_solar_partner", store=True)
    warranty_end = fields.Date(compute="_compute_solar_partner", store=True)

    @api.depends("warranty_ids.partner_id", "warranty_ids.end_date")
    def _compute_solar_partner(self):
        for lot in self:
            w = lot.warranty_ids[:1]
            lot.solar_partner_id = w.partner_id
            lot.warranty_end = w.end_date


class StockPicking(models.Model):
    _inherit = "stock.picking"

    warranty_ids = fields.One2many("solar.warranty", "picking_id", "Warranties Started")
    warranty_count = fields.Integer(compute="_compute_warranty_count")

    def _compute_warranty_count(self):
        for p in self:
            p.warranty_count = len(p.warranty_ids)

    def button_validate(self):
        self._solar_check_advance()
        return super().button_validate()

    def _solar_check_advance(self):
        """No dispatch of a solar kit until the minimum advance is paid."""
        if self.env.context.get("solar_skip_advance_check"):
            return
        for picking in self.filtered(lambda p: p.picking_type_code == "outgoing"
                                     and p.sale_id.is_solar_job):
            order = picking.sale_id
            pct = order.company_id.solar_min_advance_pct
            if not pct:
                continue
            invoices = order.invoice_ids.filtered(
                lambda m: m.state == "posted" and m.move_type == "out_invoice")
            paid = sum(m.amount_total - m.amount_residual for m in invoices)
            needed = order.amount_total * pct / 100.0
            if paid + 0.5 < needed:
                raise UserError(_(
                    "%(so)s cannot be dispatched yet: %(pct)s%% advance (%(need)s) is "
                    "required, %(paid)s received so far.",
                    so=order.name, pct=int(pct),
                    need=order.currency_id.format(needed),
                    paid=order.currency_id.format(paid)))

    def _action_done(self):
        res = super()._action_done()
        self._solar_start_warranties()
        return res

    def _solar_start_warranties(self):
        """Warranty clock starts automatically for every delivered serial/lot."""
        Warranty = self.env["solar.warranty"].sudo()
        for picking in self.filtered(lambda p: p.picking_type_code == "outgoing"):
            partner = picking.partner_id.commercial_partner_id or picking.partner_id
            order = picking.sale_id
            start = (picking.date_done or fields.Datetime.now()).date()
            created = Warranty
            for ml in picking.move_line_ids.filtered("lot_id"):
                months = ml.product_id.product_tmpl_id.solar_warranty_months
                if not months:
                    continue
                if Warranty.search_count([("lot_id", "=", ml.lot_id.id),
                                          ("partner_id", "=", partner.id)]):
                    continue
                created |= Warranty.create({
                    "lot_id": ml.lot_id.id,
                    "product_id": ml.product_id.id,
                    "partner_id": partner.id,
                    "sale_order_id": order.id,
                    "picking_id": picking.id,
                    "start_date": start,
                    "months": months,
                })
            if created:
                picking.message_post(body=_(
                    "Warranty started for %(n)s serial/lot numbers: %(s)s",
                    n=len(created), s=", ".join(created.mapped("serial"))))

    def action_view_warranties(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Warranties"),
            "res_model": "solar.warranty", "view_mode": "list,form",
            "domain": [("picking_id", "=", self.id)],
        }
