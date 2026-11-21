"""Online advance payment setup (runs once on install/upgrade).

- Quotations ask for the advance when the customer accepts online
  (share = the company's "Minimum Advance before Dispatch").
- Every online payment on an order creates an advance (down payment) invoice
  that is marked paid automatically, so dispatch unlocks by itself.
- Razorpay is installed but stays off until the Director enters the API keys.
- The built-in test provider is switched on in test mode so the flow can be
  demonstrated without real money. Switch it off before going live.
"""
from odoo import api, models

SETUP_FLAG = "sunpower.payment_setup_done"


class SolarPaymentSetup(models.AbstractModel):
    _name = "solar.payment.setup"
    _description = "SunPower online payment setup"

    @api.model
    def apply(self, force=False):
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("sale.automatic_invoice", "True")
        params.set_param("sale.async_emails", "True")   # invoice emails go via the queue
        self.sync_advance_rules()
        if params.get_param(SETUP_FLAG) and not force:
            return True
        demo = self.env.ref("payment.payment_provider_demo", raise_if_not_found=False)
        if demo and demo.state == "disabled":
            demo.write({"state": "test", "is_published": True, "name": "Test payment (no real money)"})
        params.set_param(SETUP_FLAG, "1")
        return True

    @api.model
    def sync_advance_rules(self):
        """Online quote acceptance asks for the same advance the warehouse needs."""
        for company in self.env["res.company"].search([]):
            pct = company.solar_min_advance_pct or 0.0
            company.write({"portal_confirmation_pay": bool(pct),
                           "prepayment_percent": min(max(pct / 100.0, 0.01), 1.0)})
        templates = self.env["sale.order.template"].search([("solar_kw", ">", 0)])
        for tmpl in templates:
            pct = (tmpl.company_id or self.env.company).solar_min_advance_pct or 0.0
            tmpl.write({"require_payment": bool(pct),
                        "prepayment_percent": min(max(pct / 100.0, 0.01), 1.0)})
        return True
