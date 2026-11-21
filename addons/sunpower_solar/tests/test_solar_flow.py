from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "sunpower")
class TestSolarFlow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.partner = env["res.partner"].create({"name": "Test Homeowner", "phone": "9999900000"})
        cls.lead = env["crm.lead"].create({
            "name": "3 kW test", "partner_id": cls.partner.id, "type": "opportunity",
            "requested_kw": 3, "system_type": "on_grid", "roof_area_sqft": 400,
            "monthly_bill": 3500, "grid_suitable": "yes",
        })
        cls.kit = env.ref("sunpower_solar.kit_on_grid_3kw")
        cls.template = env.ref("sunpower_solar.qt_on_grid_3kw")
        # stock with serials
        loc = env["stock.warehouse"].search([], limit=1).lot_stock_id
        Quant, Lot = env["stock.quant"], env["stock.lot"]
        bom = env["mrp.bom"]._bom_find(cls.kit)[cls.kit]
        for line in bom.bom_line_ids:
            p = line.product_id
            if p.tracking == "serial":
                for n in range(int(line.product_qty)):
                    lot = Lot.create({"name": "T-%s-%d" % (p.default_code, n), "product_id": p.id})
                    Quant._update_available_quantity(p, loc, 1, lot_id=lot)
            elif p.tracking == "lot":
                lot = Lot.create({"name": "T-%s" % p.default_code, "product_id": p.id})
                Quant._update_available_quantity(p, loc, 100, lot_id=lot)
            else:
                Quant._update_available_quantity(p, loc, 500)

    def _order(self, survey=None):
        so = self.env["sale.order"].create({
            "partner_id": self.partner.id, "opportunity_id": self.lead.id,
            "sale_order_template_id": self.template.id,
            "survey_id": survey and survey.id,
        })
        so._onchange_sale_order_template_id()
        return so

    def _approved_survey(self):
        s = self.env["solar.site.survey"].create({
            "lead_id": self.lead.id, "roof_direction": "S", "usable_area_sqft": 400,
            "recommended_kw": 3})
        s.action_mark_done()
        s.action_approve()
        return s

    def _deliver(self, so):
        picking = so.picking_ids[0]
        picking.action_assign()
        for m in picking.move_ids:
            m.quantity = m.product_uom_qty
            m.picked = True
        picking.with_context(skip_backorder=True, cancel_backorder=True,
                             solar_skip_advance_check=True).button_validate()
        return picking

    def test_01_kit_template_has_parts(self):
        so = self._order()
        self.assertTrue(so.is_solar_job)
        self.assertEqual(so.solar_kw, 3)
        self.assertTrue(so.order_line.filtered(lambda l: l.product_id == self.kit))

    def test_02_quote_blocked_without_approved_survey(self):
        so = self._order()
        with self.assertRaises(UserError):
            so.action_quotation_send()
        with self.assertRaises(UserError):
            so.action_confirm()

    def test_03_confirm_creates_picking_task_and_warranties(self):
        survey = self._approved_survey()
        so = self._order(survey)
        so.action_confirm()
        self.assertTrue(so.picking_ids, "warehouse gets a delivery order")
        self.assertTrue(so.tasks_ids.filtered("is_installation"), "crew gets a job")
        picking = self._deliver(so)
        self.assertEqual(picking.state, "done")
        ws = so.warranty_ids
        self.assertTrue(ws)
        today = fields.Date.context_today(picking)
        inv = ws.filtered(lambda w: w.product_id.categ_id.solar_warranty_months == 24)[:1]
        panel = ws.filtered(lambda w: w.months == 240)[:1]
        self.assertEqual(inv.end_date, today + relativedelta(months=24))
        self.assertEqual(panel.end_date, today + relativedelta(months=240))

    def test_04_ticket_billing_by_warranty(self):
        survey = self._approved_survey()
        so = self._order(survey)
        so.action_confirm()
        self._deliver(so)
        w = so.warranty_ids.filtered(lambda w: w.months == 24)[:1]

        free = self.env["solar.service.ticket"].create({
            "partner_id": self.partner.id, "lot_id": w.lot_id.id, "labour_hours": 2,
            "resolution": "<p>fixed</p>"})
        self.assertTrue(free.under_warranty)
        free.action_resolve()
        self.assertFalse(free.invoice_id)
        self.assertEqual(free.stage, "awaiting")
        free.action_customer_confirm()
        self.assertEqual(free.stage, "closed")

        w.start_date = fields.Date.today() - timedelta(days=900)
        paid = self.env["solar.service.ticket"].create({
            "partner_id": self.partner.id, "lot_id": w.lot_id.id, "labour_hours": 2,
            "resolution": "<p>fixed</p>"})
        self.assertFalse(paid.under_warranty)
        paid.action_resolve()
        self.assertTrue(paid.invoice_id)
        self.assertEqual(paid.invoice_id.state, "posted")

    def test_05_no_dispatch_before_advance(self):
        self.env.company.solar_min_advance_pct = 30
        survey = self._approved_survey()
        so = self._order(survey)
        so.action_confirm()
        picking = so.picking_ids[0]
        picking.action_assign()
        for m in picking.move_ids:
            m.quantity = m.product_uom_qty
            m.picked = True
        with self.assertRaises(UserError):
            picking.with_context(skip_backorder=True).button_validate()
        wiz = self.env["sale.advance.payment.inv"].with_context(
            active_model="sale.order", active_ids=so.ids).create(
            {"advance_payment_method": "percentage", "amount": 30})
        wiz.create_invoices()
        inv = so.invoice_ids
        inv.action_post()
        self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=inv.ids).create({})._create_payments()
        picking.with_context(skip_backorder=True, cancel_backorder=True).button_validate()
        self.assertEqual(picking.state, "done")
