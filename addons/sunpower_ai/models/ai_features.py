from markupsafe import Markup

from odoo import _, fields, models
from odoo.exceptions import UserError


def _ai(env):
    return env["solar.ai.client"]


class CrmLead(models.Model):
    _inherit = "crm.lead"

    def action_ai_read_bill(self):
        self.ensure_one()
        if not self.bill_attachment:
            raise UserError(_("Upload the customer's electricity bill first."))
        ai = _ai(self.env)
        res = ai.call("/bill/parse", files={"file": ai.file_tuple(
            self.bill_attachment, self.bill_filename or "bill.jpg", "image/jpeg")})
        vals = {}
        if res.get("monthly_units_kwh"):
            vals["monthly_units"] = res["monthly_units_kwh"]
        if res.get("bill_amount"):
            vals["monthly_bill"] = res["bill_amount"]
        if res.get("consumer_no"):
            vals["consumer_no"] = res["consumer_no"]
        if res.get("discom"):
            vals["discom"] = res["discom"]
        if res.get("recommended_kw") and not self.requested_kw:
            vals["requested_kw"] = res["recommended_kw"]
        self.write(vals)
        self.message_post(body=Markup(
            "<b>AI read the electricity bill</b>: %s units, ₹%s, consumer %s, %s → "
            "suggested <b>%s kW</b>. <i>(method: %s)</i>") % (
            res.get("monthly_units_kwh") or "?", res.get("bill_amount") or "?",
            res.get("consumer_no") or "?", res.get("discom") or "?",
            res.get("recommended_kw") or "?", res.get("method") or res.get("model")))
        return True


class SolarEnquiryWizard(models.TransientModel):
    _inherit = "solar.enquiry.wizard"

    ai_note = fields.Char(readonly=True)

    def action_ai_fill(self):
        self.ensure_one()
        data, files = {}, None
        if self.raw_message:
            data["text"] = self.raw_message
        if self.voice_note:
            files = {"audio": _ai(self.env).file_tuple(self.voice_note,
                                                       self.voice_filename or "voice.wav")}
        if not data and not files:
            raise UserError(_("Paste the message or attach the voice note first."))
        res = _ai(self.env).call("/lead/parse", data=data, files=files)
        vals = {"ai_note": _("Filled by AI (%s) – please check before saving.",
                             res.get("model") or "AI")}
        for key in ("name", "phone", "email", "street", "city", "summary"):
            if res.get(key):
                vals[key] = res[key]
        if res.get("intent") in ("new_enquiry", "complaint"):
            vals["intent"] = res["intent"]
        if res.get("system_kw"):
            vals["system_kw"] = res["system_kw"]
        if res.get("system_type") in ("on_grid", "off_grid"):
            vals["system_type"] = res["system_type"]
        if res.get("subsidy") is not None:
            vals["subsidy"] = bool(res["subsidy"])
        if res.get("monthly_bill"):
            vals["monthly_bill"] = res["monthly_bill"]
        if res.get("transcript") and not self.raw_message:
            vals["raw_message"] = res["transcript"]
        self.write(vals)
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id,
                "view_mode": "form", "target": "new", "name": _("Log WhatsApp / Call")}


class SolarServiceTicket(models.Model):
    _inherit = "solar.service.ticket"

    def action_ai_diagnose(self):
        self.ensure_one()
        if not (self.fault_code or self.description):
            raise UserError(_("Enter the fault code or describe the complaint first."))
        res = _ai(self.env).call("/fault/diagnose", json={
            "fault_code": self.fault_code or "", "description": self.description or "",
            "inverter_brand": self.product_id.name or ""})
        steps = Markup("").join(Markup("<li>%s</li>") % s for s in res.get("steps") or [])
        parts = ", ".join(res.get("likely_parts") or []) or _("none expected")
        html = Markup(
            "<p><b>Likely cause:</b> %s</p><p><b>Suggested steps:</b></p><ol>%s</ol>"
            "<p><b>Site visit needed:</b> %s &nbsp; <b>Likely parts:</b> %s &nbsp; "
            "<b>Confidence:</b> %s%%</p><p class='text-muted small'>Source: %s</p>") % (
            res.get("likely_cause") or "-", steps,
            _("Yes") if res.get("needs_site_visit") else _("No"), parts,
            int((res.get("confidence") or 0) * 100), res.get("source") or res.get("model") or "AI")
        vals = {"ai_diagnosis": html}
        if self.stage == "new":
            vals["stage"] = "diagnosed"
        self.write(vals)
        return True


class ProjectTask(models.Model):
    _inherit = "project.task"

    def action_ai_check_photos(self):
        self.ensure_one()
        photos = self.install_photo_ids.filtered(lambda a: (a.mimetype or "").startswith("image"))
        if not photos:
            raise UserError(_("Upload photos of the finished roof first."))
        results, flagged = [], []
        for att in photos:
            res = _ai(self.env).call("/photo/check", files={
                "file": (att.name, att.raw, att.mimetype)})
            results.append("%s: %s (%d%%)" % (att.name, res.get("label"),
                                              int((res.get("confidence") or 0) * 100)))
            if res.get("flag"):
                flagged.append(att.name)
        self.photo_check_result = (_("⚠ Check: ") if flagged else _("✔ OK: ")) + "; ".join(results)
        self.message_post(body=_("AI photo check – %s", self.photo_check_result))
        return True
