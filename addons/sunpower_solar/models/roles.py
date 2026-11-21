"""SunPower roles: which role a user has, where they land after signing in, and
the demo logins (one per role)."""
import logging
from html import escape
from urllib.parse import urlencode

from odoo import api, models

_logger = logging.getLogger(__name__)

# Most powerful first: a user's role is the first group they belong to.
ROLES = [
    ("director", "sunpower_solar.group_director"),
    ("sales", "sunpower_solar.group_sales"),
    ("support", "sunpower_solar.group_support"),
    ("warehouse", "sunpower_solar.group_warehouse"),
    ("technician", "sunpower_solar.group_technician"),
]

# Back-office screen each role opens on (React Console for the director)
ROLE_ACTIONS = {
    "director": "sunpower_solar.action_solar_dashboard",
    "sales": "sunpower_solar.action_solar_pipeline",
    "support": "sunpower_solar.action_solar_ticket",
    "warehouse": "stock.action_picking_tree_outgoing",
    "technician": "sunpower_solar.action_my_installation_jobs",
}

DEMO_USERS = [
    ("director@sunpower.demo", "Priya Desai (Director)", "director"),
    ("sales@sunpower.demo", "Rohan Mehta (Sales)", "sales"),
    ("warehouse@sunpower.demo", "Imran Shaikh (Warehouse)", "warehouse"),
    ("support@sunpower.demo", "Neha Joshi (Support)", "support"),
]
DEMO_PASSWORD = "sunpower"


class ResUsers(models.Model):
    _inherit = "res.users"

    def _sunpower_role(self):
        self.ensure_one()
        if self.share:
            return "customer"
        for role, xmlid in ROLES:
            if self.has_group(xmlid):
                return role
        return "staff"

    def _sunpower_home(self, engine_url=""):
        """Where this user should go after signing in: a React path for the
        director/customers, a back-office URL for everyone else."""
        role = self._sunpower_role()
        if role == "director":
            return "/console"
        if role == "customer":
            return "/account"
        action = ROLE_ACTIONS.get(role)
        return engine_url + ("/odoo/action-%s" % action if action else "/odoo")

    @api.model
    def _sunpower_apply_role_home(self):
        """Open each staff member on their own screen in the back office."""
        for user in self.search([("share", "=", False)]):
            xmlid = ROLE_ACTIONS.get(user._sunpower_role())
            action = self.env.ref(xmlid, raise_if_not_found=False) if xmlid else None
            if action:
                user.action_id = action.id


    # ------------------------------------------------------------ account emails
    _ACCOUNT_EMAILS = {
        "reset": ("Reset your SunPower password",
                  "Someone (hopefully you) asked to reset the password for your SunPower account.",
                  "Choose a new password"),
        "invite": ("Your SunPower account is ready",
                   "Thank you for choosing SunPower. Your order is confirmed, and you can now follow "
                   "your installation, warranties and service requests online.",
                   "Set your password"),
        "claim": ("Finish setting up your SunPower account",
                  "Someone (hopefully you) tried to sign up with this email. You already have a "
                  "SunPower account, so just choose a password to sign in.",
                  "Choose a password"),
    }

    def _sunpower_send_account_email(self, kind):
        """Queue a branded email with a single-use link to the website's
        set-password page. kind: reset | invite | claim."""
        self.ensure_one()
        if not self.email:
            return False
        partner = self.partner_id.sudo()
        partner.signup_prepare(signup_type="reset")
        token = partner._generate_signup_token()
        frontend = (self.env["ir.config_parameter"].sudo()
                    .get_param("sunpower.frontend_url", "http://localhost:5173")).rstrip("/")
        params = {"token": token}
        if kind != "reset":
            params["welcome"] = 1
        link = "%s/reset-password?%s" % (frontend, urlencode(params))
        subject, intro, button = self._ACCOUNT_EMAILS[kind]
        body = (
            '<div style="font-family:-apple-system,Segoe UI,Inter,sans-serif;max-width:520px;margin:auto;color:#1d1d1f">'
            '<p style="font-size:20px;font-weight:600">%s</p><p>Hi %s,</p><p>%s The link works once and '
            'expires in 24 hours.</p><p><a href="%s" style="display:inline-block;background:#1d1d1f;color:#fff;'
            'padding:12px 22px;border-radius:999px;text-decoration:none;font-weight:600">%s</a></p>'
            '<p style="color:#6e6e73;font-size:13px">If you didn&#39;t ask for this, you can ignore this email.</p></div>'
        ) % (escape(subject), escape(self.name), escape(intro), escape(link), escape(button))
        company = self.company_id or self.env.company
        mail = self.env["mail.mail"].sudo().create({
            "subject": subject,
            "email_from": company.email_formatted or company.partner_id.email_formatted,
            "email_to": self.email_formatted or self.email,
            "body_html": body,
            "auto_delete": True,
        })
        try:
            mail.send()
        except Exception:  # queued; the mail queue retries
            _logger.exception("SunPower: account email could not be sent now")
        return link


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _sunpower_invite_customer(self):
        """Give a customer a website account (customer role) and email them a
        link to choose a password. Skips partners without email or who
        already have a login."""
        Users = self.env["res.users"].sudo().with_context(no_reset_password=True)
        portal = self.env.ref("base.group_portal")
        for partner in self:
            email = (partner.email or "").strip().lower()
            if not email or partner.user_ids:
                continue
            if Users.with_context(active_test=False).search_count([("login", "=ilike", email)]):
                continue
            user = Users.create({"name": partner.name, "login": email, "email": email,
                                 "partner_id": partner.id,
                                 "groups_id": [(6, 0, [portal.id])]})
            user._sunpower_send_account_email("invite")
        return True


class SolarRoleSetup(models.AbstractModel):
    _name = "solar.role.setup"
    _description = "SunPower roles setup"

    @api.model
    def apply(self):
        """Idempotent: create the demo role logins, move technicians to the
        Technician role (no warehouse rights), make job projects visible only to
        the assigned crew, and set everyone's home screen."""
        Users = self.env["res.users"].with_context(no_reset_password=True)
        for login, name, role in DEMO_USERS:
            group = self.env.ref("sunpower_solar.group_%s" % role)
            user = Users.search([("login", "=", login)], limit=1)
            if not user:
                user = Users.create({"name": name, "login": login, "email": login,
                                     "password": DEMO_PASSWORD,
                                     "groups_id": [(6, 0, [group.id])]})
            else:
                user.groups_id = [(4, group.id)]
        tech_group = self.env.ref("sunpower_solar.group_technician")
        stock_user = self.env.ref("stock.group_stock_user")
        techs = Users.search([("login", "=like", "tech%@sunpower.demo")])
        for tech in techs:
            tech.write({"groups_id": [(4, tech_group.id), (3, stock_user.id)]})
        # Crew sees only installation jobs they are assigned to / follow
        projects = self.env["project.task"].search([("is_installation", "=", True)]).project_id
        template = self.env.ref("sunpower_solar.project_installation_template",
                                raise_if_not_found=False)
        (projects | (template or projects.browse())).write({"privacy_visibility": "followers"})
        self.env["res.users"]._sunpower_apply_role_home()
        return True
