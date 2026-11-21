"""Website accounts: sign up, the customer's own overview, complaints and repairs."""
import json

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "sunpower")
class TestSunpowerAccount(HttpCase):

    def rpc(self, url, **params):
        res = self.url_open(url, data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": params}),
                            headers={"Content-Type": "application/json"})
        body = res.json()
        self.assertNotIn("error", body, body.get("error"))
        return body["result"]

    def test_signup_creates_customer_and_signs_in(self):
        r = self.rpc("/api/sunpower/auth/signup", name="Asha Patel", email="asha@x.test",
                     phone="9800000000", password="longenough1")
        self.assertEqual(r["status"], "created")
        me = self.rpc("/api/sunpower/me")
        self.assertTrue(me["authenticated"])
        self.assertEqual(me["role"], "customer")
        self.assertEqual(me["home"], "/account")
        user = self.env["res.users"].search([("login", "=", "asha@x.test")])
        self.assertTrue(user.share, "self sign-up must never create staff")
        self.assertEqual(user.partner_id.phone, "9800000000")

    def test_signup_validation(self):
        self.assertFalse(self.rpc("/api/sunpower/auth/signup", name="A", email="bad", password="longenough1")["ok"])
        self.assertFalse(self.rpc("/api/sunpower/auth/signup", name="A", email="a@x.test", password="short")["ok"])

    def test_signup_existing_email_does_not_sign_in(self):
        self.env["res.partner"].create({"name": "Known Customer", "email": "known@x.test"})
        r = self.rpc("/api/sunpower/auth/signup", name="Impostor", email="known@x.test", password="longenough1")
        self.assertEqual(r["status"], "check_email")
        self.assertFalse(self.rpc("/api/sunpower/me")["authenticated"])
        r = self.rpc("/api/sunpower/auth/signup", name="Impostor", email="admin", password="longenough1")
        self.assertFalse(r["ok"])  # not an email
        self.assertFalse(self.rpc("/api/sunpower/me")["authenticated"])

    def test_overview_complaint_and_confirm(self):
        partner = self.env["res.partner"].create({"name": "Cust", "email": "cust@x.test"})
        other = self.env["res.partner"].create({"name": "Other"})
        self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Cust", "login": "cust@x.test", "password": "longenough1", "partner_id": partner.id,
            "groups_id": [(6, 0, [self.env.ref("base.group_portal").id])]})
        theirs = self.env["solar.service.ticket"].create({"partner_id": other.id, "description": "x"})
        self.authenticate("cust@x.test", "longenough1")
        r = self.rpc("/api/sunpower/my/complaint", description="short")
        self.assertFalse(r["ok"])
        r = self.rpc("/api/sunpower/my/complaint", description="Inverter shows a red light", fault_code="E021")
        self.assertTrue(r["ok"])
        data = self.rpc("/api/sunpower/my/overview")
        self.assertEqual([t["id"] for t in data["tickets"]], [r["id"]])
        self.assertNotIn(theirs.id, [t["id"] for t in data["tickets"]])
        mine = self.env["solar.service.ticket"].browse(r["id"])
        mine.stage = "awaiting"
        self.assertTrue(self.rpc("/api/sunpower/my/ticket/confirm", ticket_id=mine.id)["ok"])
        self.assertEqual(mine.stage, "closed")
        # someone else's ticket is never reachable
        res = self.url_open("/api/sunpower/my/ticket/confirm", data=json.dumps(
            {"jsonrpc": "2.0", "method": "call", "params": {"ticket_id": theirs.id}}),
            headers={"Content-Type": "application/json"}).json()
        self.assertIn("error", res)
        self.assertEqual(theirs.stage, "new")

    def test_pay_advance_online(self):
        partner = self.env["res.partner"].create({"name": "Payer", "email": "payer@x.test"})
        self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Payer", "login": "payer@x.test", "password": "longenough1", "partner_id": partner.id,
            "groups_id": [(6, 0, [self.env.ref("base.group_portal").id])]})
        product = self.env["product.product"].create({"name": "Kit", "list_price": 100000, "type": "consu"})
        order = self.env["sale.order"].create({
            "partner_id": partner.id, "order_line": [(0, 0, {"product_id": product.id, "product_uom_qty": 1})]})
        order.with_context(sunpower_no_invite=True).action_confirm()
        needed = order._solar_advance_needed()
        self.assertGreater(needed, 0)

        self.authenticate("payer@x.test", "longenough1")
        r = self.rpc("/api/sunpower/my/order/pay", order_id=order.id)
        self.assertTrue(r["ok"], r)
        self.assertIn("/payment/pay?", r["url"])
        self.assertAlmostEqual(r["amount"], needed)
        # the payment page opens for that link
        page = self.url_open(r["url"].split("8069", 1)[-1] if "8069" in r["url"] else r["url"])
        self.assertEqual(page.status_code, 200)

        # simulate the provider confirming the payment
        provider = self.env.ref("payment.payment_provider_demo")
        tx = self.env["payment.transaction"].sudo().create({
            "provider_id": provider.id, "payment_method_id": provider.payment_method_ids[:1].id,
            "amount": r["amount"], "currency_id": order.currency_id.id, "partner_id": partner.id,
            "reference": "TEST-%s" % order.id, "operation": "online_direct", "sale_order_ids": [(6, 0, order.ids)]})
        tx._set_done()
        tx._post_process()
        self.assertAlmostEqual(order._solar_paid_amount(), needed, places=0)
        data = self.rpc("/api/sunpower/my/overview")
        mine = [o for o in data["orders"] if o["id"] == order.id][0]
        self.assertEqual(mine["advance_due"], 0)
        # nothing more to pay as advance; someone else's order is refused
        self.assertFalse(self.rpc("/api/sunpower/my/order/pay", order_id=order.id)["ok"])
        other = self.env["sale.order"].create({"partner_id": self.env["res.partner"].create({"name": "X"}).id,
                                               "order_line": [(0, 0, {"product_id": product.id})]})
        self.assertFalse(self.rpc("/api/sunpower/my/order/pay", order_id=other.id)["ok"])
