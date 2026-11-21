"""SunPower roles: which role a user has, where they land after signing in, and
the demo logins (one per role)."""
from odoo import api, models

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
    "sales": "crm.crm_lead_action_pipeline",
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
            return engine_url + "/my/solar"
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
