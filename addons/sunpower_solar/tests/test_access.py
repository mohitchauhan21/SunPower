"""Roles & permissions: each role sees and changes only what it should."""
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "sunpower")
class TestSunpowerAccess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env["res.users"].with_context(no_reset_password=True)

        def user(login, group):
            return Users.create({"name": login, "login": login, "email": login,
                                 "groups_id": [(6, 0, [cls.env.ref(group).id])]})
        cls.director = user("t_director@x.test", "sunpower_solar.group_director")
        cls.sales = user("t_sales@x.test", "sunpower_solar.group_sales")
        cls.warehouse = user("t_wh@x.test", "sunpower_solar.group_warehouse")
        cls.support = user("t_support@x.test", "sunpower_solar.group_support")
        cls.tech = user("t_tech@x.test", "sunpower_solar.group_technician")
        cls.tech2 = user("t_tech2@x.test", "sunpower_solar.group_technician")
        cls.customer_partner = cls.env["res.partner"].create({"name": "Cust A", "email": "a@x.test"})
        cls.other_partner = cls.env["res.partner"].create({"name": "Cust B"})
        cls.customer = Users.create({"name": "Cust A", "login": "a@x.test", "partner_id": cls.customer_partner.id,
                                     "groups_id": [(6, 0, [cls.env.ref("base.group_portal").id])]})
        cls.lead = cls.env["crm.lead"].create({"name": "L", "type": "opportunity"})
        cls.survey_mine = cls.env["solar.site.survey"].create({"lead_id": cls.lead.id, "technician_id": cls.tech.id})
        cls.survey_other = cls.env["solar.site.survey"].create({"lead_id": cls.lead.id, "technician_id": cls.tech2.id})
        cls.ticket_mine = cls.env["solar.service.ticket"].create({"partner_id": cls.customer_partner.id, "user_id": cls.tech.id})
        cls.ticket_other = cls.env["solar.service.ticket"].create({"partner_id": cls.other_partner.id, "user_id": cls.tech2.id})

    def test_roles_resolve(self):
        self.assertEqual(self.director._sunpower_role(), "director")
        self.assertEqual(self.sales._sunpower_role(), "sales")
        self.assertEqual(self.tech._sunpower_role(), "technician")
        self.assertEqual(self.customer._sunpower_role(), "customer")
        self.assertEqual(self.director._sunpower_home(), "/console")
        self.assertEqual(self.customer._sunpower_home(), "/account")

    def test_technician_only_own_work(self):
        Survey = self.env["solar.site.survey"].with_user(self.tech)
        self.assertIn(self.survey_mine, Survey.search([]))
        self.assertNotIn(self.survey_other, Survey.search([]))
        Ticket = self.env["solar.service.ticket"].with_user(self.tech)
        self.assertEqual(Ticket.search([]), self.ticket_mine)
        with self.assertRaises(AccessError):
            self.env["crm.lead"].with_user(self.tech).search([])
        with self.assertRaises(AccessError):
            self.env["stock.picking"].with_user(self.tech).search([])

    def test_technician_cannot_approve_survey(self):
        self.survey_mine.write({"state": "done", "recommended_kw": 3, "roof_direction": "S", "usable_area_sqft": 300})
        with self.assertRaises(UserError):
            self.survey_mine.with_user(self.tech).action_approve()
        self.survey_mine.with_user(self.sales).action_approve()
        self.assertEqual(self.survey_mine.state, "approved")

    def test_profit_and_dashboard_director_only(self):
        order = self.env["sale.order"].create({"partner_id": self.customer_partner.id})
        for u in (self.sales, self.support, self.warehouse):
            with self.assertRaises(AccessError):
                order.with_user(u).read(["job_profit"])
            with self.assertRaises(AccessError):
                self.env["solar.dashboard"].with_user(u).get_data("month")
        self.assertIn("job_profit", order.with_user(self.director).read(["job_profit"])[0])
        self.assertIn("kpi", self.env["solar.dashboard"].with_user(self.director).get_data("month"))

    def test_warehouse_no_enquiries_or_tickets(self):
        with self.assertRaises(AccessError):
            self.env["crm.lead"].with_user(self.warehouse).search([])
        with self.assertRaises(AccessError):
            self.env["solar.service.ticket"].with_user(self.warehouse).search([])

    def test_support_reads_but_cannot_delete_tickets(self):
        tickets = self.env["solar.service.ticket"].with_user(self.support).search([])
        self.assertIn(self.ticket_other, tickets)
        with self.assertRaises(AccessError):
            self.ticket_other.with_user(self.support).unlink()

    def test_customer_sees_only_own_tickets(self):
        tickets = self.env["solar.service.ticket"].with_user(self.customer).search([])
        self.assertEqual(tickets, self.ticket_mine)
        with self.assertRaises(AccessError):
            self.ticket_mine.with_user(self.customer).write({"description": "x"})

    def test_settings_director_only(self):
        with self.assertRaises(AccessError):
            self.env["product.category"].with_user(self.sales).create({"name": "x", "solar_warranty_months": 1})
        self.assertTrue(self.director.has_group("base.group_system"))
        self.assertFalse(self.sales.has_group("base.group_system"))

    def test_invite_customer_once(self):
        partner = self.env["res.partner"].create({"name": "New Buyer", "email": "buyer@x.test"})
        partner._sunpower_invite_customer()
        user = partner.user_ids
        self.assertEqual(len(user), 1)
        self.assertEqual(user._sunpower_role(), "customer")
        self.assertEqual(partner.signup_type, "reset", "a set-password link was prepared")
        partner._sunpower_invite_customer()
        self.assertEqual(len(partner.user_ids), 1)
        # no email -> no account
        silent = self.env["res.partner"].create({"name": "No Mail"})
        silent._sunpower_invite_customer()
        self.assertFalse(silent.user_ids)
