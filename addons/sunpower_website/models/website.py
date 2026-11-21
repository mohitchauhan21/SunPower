from odoo import api, models


class Website(models.Model):
    _inherit = "website"

    @api.model
    def _sp_sync_logo_from_company(self):
        """Use each website's company logo as the header logo (replaces the
        'YourLogo' placeholder). Called from views/branding.xml on install/upgrade."""
        for website in self.search([]):
            company = website.company_id
            if company.logo and not company.uses_default_logo:
                website.logo = company.logo
        return True
