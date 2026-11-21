from odoo import api, fields, models

SYSTEM_TYPES = [("on_grid", "On-Grid"), ("off_grid", "Off-Grid")]


class ResCompany(models.Model):
    _inherit = "res.company"

    solar_min_advance_pct = fields.Float(
        "Minimum Advance before Dispatch (%)", default=30.0,
        help="Solar kits are only dispatched once this share of the order value "
             "has been paid. 0 = no check.")


class ProductCategory(models.Model):
    _inherit = "product.category"

    solar_warranty_months = fields.Integer(
        "Default Warranty (months)",
        help="Warranty applied to every serial/lot of products in this category "
             "from the delivery date. E.g. 24 for inverters, 240 for panels.")


class ProductTemplate(models.Model):
    _inherit = "product.template"

    solar_warranty_months = fields.Integer(
        "Warranty (months)", compute="_compute_solar_warranty_months",
        store=True, readonly=False,
        help="Overrides the category default. 0 = no warranty tracking.")
    is_solar_kit = fields.Boolean("Solar System Package")
    solar_kw = fields.Float("System Size (kW)")
    solar_system_type = fields.Selection(SYSTEM_TYPES, "System Type")
    is_installation_service = fields.Boolean("Solar Installation Service")

    @api.depends("categ_id.solar_warranty_months")
    def _compute_solar_warranty_months(self):
        for tmpl in self:
            tmpl.solar_warranty_months = tmpl.categ_id.solar_warranty_months
