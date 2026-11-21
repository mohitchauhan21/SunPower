"""When an online payment for a solar order succeeds, tell the office and
refresh the job's money figures. (The advance invoice itself is created and
reconciled by the standard automatic invoicing.)"""
from odoo import _, models


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    def _post_process(self):
        done = self.filtered(lambda tx: tx.state == "done" and not tx.is_post_processed)
        res = super()._post_process()
        for tx in done:
            for order in tx.sale_order_ids.filtered("is_solar_job"):
                order._solar_announce_payment(tx)
        return res


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _solar_paid_amount(self):
        self.ensure_one()
        invoices = self.invoice_ids.filtered(
            lambda m: m.state == "posted" and m.move_type == "out_invoice")
        return sum(m.amount_total - m.amount_residual for m in invoices)

    def _solar_advance_needed(self):
        self.ensure_one()
        pct = self.company_id.solar_min_advance_pct or 0.0
        return round(self.amount_total * pct / 100.0, 2)

    def _solar_announce_payment(self, tx):
        self.ensure_one()
        paid = self._solar_paid_amount()
        ready = paid + 0.5 >= self._solar_advance_needed()
        body = _("Online payment of %(amt)s received (%(ref)s). Paid so far: %(paid)s.",
                 amt=tx.currency_id.format(tx.amount), ref=tx.reference,
                 paid=self.currency_id.format(paid))
        if ready and self.state == "sale":
            body += " " + _("The advance is complete: the kit can be dispatched.")
        self.sudo().message_post(body=body)
        self.sudo()._solar_refresh_job_financials()
