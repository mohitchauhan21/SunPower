from odoo import _, fields, models

from ..models.product import SYSTEM_TYPES


class SolarEnquiryWizard(models.TransientModel):
    _name = "solar.enquiry.wizard"
    _description = "Log a WhatsApp / Call Enquiry or Complaint"

    channel = fields.Selection([("whatsapp", "WhatsApp"), ("call", "Phone Call"),
                                ("walkin", "Walk-in")], default="whatsapp",
                               required=True)
    raw_message = fields.Text("Message / Call Notes")
    voice_note = fields.Binary("Voice Note")
    voice_filename = fields.Char()
    intent = fields.Selection([("new_enquiry", "New Enquiry"),
                               ("complaint", "Complaint / Service")],
                              default="new_enquiry", required=True)
    name = fields.Char("Customer Name")
    phone = fields.Char()
    email = fields.Char()
    street = fields.Char()
    city = fields.Char()
    system_kw = fields.Float("Requested kW")
    system_type = fields.Selection(SYSTEM_TYPES, default="on_grid")
    subsidy = fields.Boolean("Wants Subsidy")
    monthly_bill = fields.Float("Monthly Bill (₹)")
    summary = fields.Text()

    def action_create(self):
        self.ensure_one()
        if self.intent == "complaint":
            partner = self.env["res.partner"].search(
                [("phone", "ilike", (self.phone or "")[-10:])], limit=1) \
                if self.phone else self.env["res.partner"]
            if not partner:
                partner = self.env["res.partner"].create(
                    {"name": self.name or self.phone or _("Unknown caller"),
                     "phone": self.phone})
            lot = self.env["stock.lot"].search(
                [("solar_partner_id", "=", partner.id),
                 ("product_id.name", "ilike", "inverter")], limit=1)
            ticket = self.env["solar.service.ticket"].create({
                "partner_id": partner.id, "lot_id": lot.id,
                "description": self.summary or self.raw_message, "priority": "1",
            })
            return {"type": "ir.actions.act_window", "res_model": "solar.service.ticket",
                    "res_id": ticket.id, "view_mode": "form"}
        lead = self.env["crm.lead"].solar_create_enquiry({
            "name": _("%(kw)s kW enquiry – %(n)s", kw=self.system_kw or "?",
                      n=self.name or self.phone),
            "contact_name": self.name, "phone": self.phone, "email_from": self.email,
            "street": self.street, "city": self.city,
            "requested_kw": self.system_kw, "system_type": self.system_type,
            "subsidy_requested": self.subsidy, "monthly_bill": self.monthly_bill,
            "description": "\n\n".join(p for p in [self.summary, self.raw_message] if p),
        }, channel=self.channel)
        return {"type": "ir.actions.act_window", "res_model": "crm.lead",
                "res_id": lead.id, "view_mode": "form"}
