from odoo import _, api, fields, models
from odoo.exceptions import UserError

DIRECTIONS = [
    ("N", "North"), ("NE", "North-East"), ("E", "East"), ("SE", "South-East"),
    ("S", "South"), ("SW", "South-West"), ("W", "West"), ("NW", "North-West"),
]


class SolarSiteSurvey(models.Model):
    _name = "solar.site.survey"
    _description = "Rooftop Site Survey"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "survey_date desc, id desc"

    name = fields.Char(default=lambda s: _("New"), readonly=True, copy=False)
    lead_id = fields.Many2one("crm.lead", "Enquiry", required=True, ondelete="cascade",
                              tracking=True)
    partner_id = fields.Many2one(related="lead_id.partner_id", store=True)
    contact_name = fields.Char(compute="_compute_contact", store=True)
    phone = fields.Char(related="lead_id.phone")
    address = fields.Char(compute="_compute_contact", store=True)
    technician_id = fields.Many2one("res.users", "Surveyor", tracking=True,
                                    default=lambda s: s.env.user)
    survey_date = fields.Datetime("Visit Date", tracking=True)
    state = fields.Selection([
        ("scheduled", "Scheduled"),
        ("done", "Visited"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ], default="scheduled", tracking=True, required=True)

    # Measurements
    roof_type = fields.Selection([
        ("rcc", "RCC / Concrete"), ("metal", "Metal Sheet"),
        ("tile", "Tiles"), ("ground", "Ground Mount"),
    ])
    roof_direction = fields.Selection(DIRECTIONS, "Roof Facing")
    roof_tilt = fields.Float("Roof Tilt (°)")
    usable_area_sqft = fields.Float("Shadow-free Area (sq ft)")
    shading = fields.Selection([("none", "No Shade"), ("partial", "Partial"),
                                ("heavy", "Heavy")], default="none")
    cable_distance_m = fields.Float("Cable Distance to Meter (m)")
    earthing_possible = fields.Boolean("Earthing Pit Possible", default=True)
    latitude = fields.Float(digits=(10, 6))
    longitude = fields.Float(digits=(10, 6))
    max_kw_fit = fields.Float("Max kW that fits", compute="_compute_max_kw", store=True,
                              help="≈100 sq ft of shadow-free area per kW")
    recommended_kw = fields.Float("Recommended kW", tracking=True)
    photo_ids = fields.Many2many("ir.attachment", string="Site Photos")
    notes = fields.Html()
    rejection_reason = fields.Char()

    @api.depends("lead_id.contact_name", "lead_id.partner_name", "lead_id.street",
                 "lead_id.city")
    def _compute_contact(self):
        for s in self:
            lead = s.lead_id
            s.contact_name = lead.contact_name or lead.partner_name or lead.name
            s.address = ", ".join(p for p in [lead.street, lead.city] if p)

    @api.depends("usable_area_sqft")
    def _compute_max_kw(self):
        for s in self:
            s.max_kw_fit = round(s.usable_area_sqft / 100.0, 1)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("solar.site.survey")
        surveys = super().create(vals_list)
        for s in surveys:
            if s.technician_id and s.survey_date:
                s.activity_schedule(
                    "mail.mail_activity_data_todo", date_deadline=s.survey_date.date(),
                    summary=_("Roof survey visit"), user_id=s.technician_id.id)
        return surveys

    def action_mark_done(self):
        for s in self:
            if not (s.roof_direction and s.usable_area_sqft):
                raise UserError(_("Record at least roof direction and shadow-free area "
                                  "before marking the visit done."))
        self.write({"state": "done"})

    def action_approve(self):
        if not (self.env.user.has_group("sunpower_solar.group_sales")
                or self.env.su):
            raise UserError(_("Only Sales or the Director can approve a survey."))
        for s in self:
            if s.state != "done":
                raise UserError(_("Only visited surveys can be approved."))
            if not s.recommended_kw:
                raise UserError(_("Set the recommended system size (kW) first."))
            s.lead_id.write({"requested_kw": s.recommended_kw})
        self.write({"state": "approved"})
        self.activity_feedback(["mail.mail_activity_data_todo"])

    def action_reject(self):
        self.write({"state": "rejected"})

    def action_reset(self):
        self.write({"state": "scheduled"})
