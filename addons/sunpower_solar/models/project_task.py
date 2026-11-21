from odoo import _, api, fields, models
from odoo.exceptions import UserError

CHECKLIST = [
    ("chk_stands", "Mounting stands fixed"),
    ("chk_panels", "Panels laid & clamped"),
    ("chk_wiring", "DCDB/ACDB & wiring connected"),
    ("chk_earthing", "Earthing & lightning arrester done"),
    ("chk_generation", "Power generation tested"),
]


class ProjectTask(models.Model):
    _inherit = "project.task"

    is_installation = fields.Boolean("Solar Installation Job", index=True)
    installation_date = fields.Datetime("Scheduled On")
    installation_state = fields.Selection([
        ("planned", "Planned"), ("in_progress", "On Site"), ("done", "Completed"),
    ], default="planned", tracking=True, string="Job Status")
    installation_kw_planned = fields.Float("Ordered kW")
    installation_kw_confirmed = fields.Float("Installed kW (confirmed)")
    generation_reading_kw = fields.Float("Live Generation at Test (kW)")
    site_start = fields.Datetime("Work Started", readonly=True)
    site_end = fields.Datetime("Work Finished", readonly=True)
    site_hours = fields.Float(compute="_compute_site_hours", store=True)
    chk_stands = fields.Boolean(CHECKLIST[0][1])
    chk_panels = fields.Boolean(CHECKLIST[1][1])
    chk_wiring = fields.Boolean(CHECKLIST[2][1])
    chk_earthing = fields.Boolean(CHECKLIST[3][1])
    chk_generation = fields.Boolean(CHECKLIST[4][1])
    install_photo_ids = fields.Many2many(
        "ir.attachment", "project_task_install_photo_rel", "task_id", "attachment_id",
        string="Roof Photos")
    customer_signature = fields.Binary("Customer Signature", copy=False, attachment=True)
    signed_by = fields.Char("Signed By", copy=False)
    signed_on = fields.Datetime("Signed On", copy=False, readonly=True)
    installed_serials = fields.Text(compute="_compute_installed_serials")
    photo_check_result = fields.Char("AI Photo Check", readonly=True)

    @api.depends("site_start", "site_end")
    def _compute_site_hours(self):
        for t in self:
            t.site_hours = ((t.site_end - t.site_start).total_seconds() / 3600.0
                            if t.site_start and t.site_end else 0.0)

    def _compute_installed_serials(self):
        for t in self:
            ws = t.sale_order_id.warranty_ids
            t.installed_serials = "\n".join(
                "%s — %s (warranty until %s)" % (w.product_id.display_name, w.serial,
                                                 w.end_date) for w in ws)

    def action_open_installation_form(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "res_model": "project.task",
            "res_id": self.id, "view_mode": "form",
            "views": [(self.env.ref("sunpower_solar.view_installation_task_form").id,
                       "form")],
        }

    def action_start_work(self):
        for t in self:
            if t.installation_state == "done":
                raise UserError(_("This job is already completed."))
            t.write({"site_start": fields.Datetime.now(),
                     "installation_state": "in_progress"})
        return True

    def action_finish_work(self):
        for t in self:
            missing = [label for fname, label in CHECKLIST if not t[fname]]
            if missing:
                raise UserError(_("Checklist incomplete: %s", ", ".join(missing)))
            if not t.install_photo_ids:
                raise UserError(_("Upload at least one photo of the finished roof."))
            if not t.installation_kw_confirmed:
                raise UserError(_("Confirm the installed system size (kW)."))
            if not t.customer_signature:
                raise UserError(_("The homeowner must sign to accept the work."))
            now = fields.Datetime.now()
            t.write({
                "site_start": t.site_start or now,
                "site_end": now,
                "installation_state": "done",
                "signed_on": t.signed_on or now,
            })
            t._solar_log_timesheets()
            done_stage = t.project_id.type_ids.filtered("fold")[:1]
            if done_stage:
                t.stage_id = done_stage
            t._solar_send_certificate()
            t.sale_order_id._solar_refresh_job_financials()
        return True

    def _solar_log_timesheets(self):
        """Technician hours land on the job's analytic account -> job costing."""
        Line = self.env["account.analytic.line"].sudo()
        for t in self:
            hours = max(t.site_hours, 0.25)
            for user in t.user_ids or self.env.user:
                employee = user.employee_id
                if not employee:
                    continue
                Line.create({
                    "name": _("Installation %s", t.name),
                    "project_id": t.project_id.id,
                    "task_id": t.id,
                    "employee_id": employee.id,
                    "unit_amount": hours,
                    "date": fields.Date.context_today(t),
                })

    def _solar_send_certificate(self):
        template = self.env.ref("sunpower_solar.mail_template_installation_done",
                                raise_if_not_found=False)
        for t in self:
            t = t.sudo()
            company = t.company_id or self.env.company
            note = _("Installation completed and accepted by %s.",
                     t.signed_by or t.partner_id.name)
            if template and t.partner_id.email:
                try:
                    # sent from the company, never from the technician's own address
                    with self.env.cr.savepoint():
                        t.message_post_with_source(
                            template, subtype_xmlid="mail.mt_comment",
                            author_id=company.partner_id.id,
                            email_from=company.email_formatted or company.partner_id.email_formatted)
                    continue
                except Exception as e:  # never block job completion on e-mail
                    note += " " + _("Certificate e-mail could not be sent: %s", e)
            t.message_post(body=note, author_id=company.partner_id.id)
