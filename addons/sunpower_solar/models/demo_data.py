"""One-click realistic demo data so the dashboard has a story to tell."""
import logging
import random
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

FIRST = ["Aarav", "Vihaan", "Ananya", "Diya", "Rohan", "Kavya", "Arjun", "Isha", "Kabir",
         "Meera", "Rahul", "Sneha", "Vikram", "Pooja", "Aditya", "Neha", "Karan", "Riya",
         "Siddharth", "Tanvi", "Manish", "Priya", "Harsh", "Nisha", "Yash", "Anjali"]
LAST = ["Patel", "Shah", "Mehta", "Sharma", "Desai", "Joshi", "Trivedi", "Iyer", "Reddy",
        "Nair", "Gupta", "Verma", "Chauhan", "Parmar", "Rana", "Bhatt"]
AREAS = ["Satellite", "Bopal", "Navrangpura", "Maninagar", "Gota", "Thaltej", "Vastrapur",
         "Chandkheda", "Naranpura", "Prahlad Nagar", "Sanand", "Gandhinagar Sec 21"]
TECHS = ["Ramesh Solanki", "Suresh Makwana", "Mahesh Vaghela", "Dinesh Rathod",
         "Jignesh Prajapati", "Bharat Thakor", "Kalpesh Parmar", "Hitesh Gohil",
         "Nilesh Chavda", "Paresh Barot", "Vipul Dabhi", "Hardik Zala", "Mukesh Bariya",
         "Sanjay Koli", "Ajay Damor"]
FAULTS = [
    ("E-07", "Inverter showing fault code E-07, zero power since the rain started"),
    ("F-24", "Isolation fault on inverter display, tripping every morning"),
    ("", "Battery backup lasting only 30 minutes"),
    ("W-11", "Grid overvoltage warning, generation drops at noon"),
    ("", "Panel glass cracked after hailstorm"),
    ("E-33", "Inverter fan noise and over-temperature alarm"),
]


class SolarDemoData(models.AbstractModel):
    _name = "solar.demo.data"
    _description = "SunPower demo data loader"

    # ---------------------------------------------------------------- helpers
    def _ensure_accounting(self):
        company = self.env.company
        if not self.env["account.journal"].search_count(
                [("type", "=", "sale"), ("company_id", "=", company.id)]):
            self.env["account.chart.template"].try_loading(
                "in" if company.country_id.code == "IN" else "generic_coa",
                company, install_demo=False)

    def _partner(self, rnd, i):
        name = "%s %s" % (rnd.choice(FIRST), rnd.choice(LAST))
        return self.env["res.partner"].create({
            "name": name, "phone": "+91 98%08d" % rnd.randint(0, 99999999),
            "email": "%s.%d@example.com" % (name.lower().replace(" ", "."), i),
            "street": "%d, %s" % (rnd.randint(1, 250), rnd.choice(AREAS)),
            "city": "Ahmedabad", "zip": "3800%02d" % rnd.randint(1, 99),
            "state_id": self.env.ref("base.state_in_gj").id,
            "country_id": self.env.ref("base.in").id,
        })

    def _technicians(self):
        Users = self.env["res.users"].with_context(no_reset_password=True)
        # Technician role: own jobs only, no stock/prices (see security/security.xml)
        groups = [self.env.ref("sunpower_solar.group_technician").id]
        techs = Users.browse()
        for i, name in enumerate(TECHS):
            login = "tech%02d@sunpower.demo" % (i + 1)
            user = Users.search([("login", "=", login)], limit=1) or Users.create({
                "name": name, "login": login, "password": "sunpower",
                "groups_id": [(6, 0, groups)],
            })
            emp = user.employee_id or self.env["hr.employee"].create(
                {"name": name, "user_id": user.id})
            emp.hourly_cost = 220 + (i % 5) * 40
            techs |= user
        # technicians open straight on their own jobs, never the director's dashboard
        techs.write({"action_id": self.env.ref("sunpower_solar.action_my_installation_jobs").id})
        return techs

    def _receive_stock(self):
        Quant = self.env["stock.quant"]
        Lot = self.env["stock.lot"]
        loc = self.env["stock.warehouse"].search([], limit=1).lot_stock_id
        products = self.env["product.product"].search([
            ("default_code", "!=", False), ("is_storable", "=", True),
            ("categ_id.parent_id.name", "=", "SunPower")])
        for p in products:
            if p.tracking == "serial":
                prefix = p.default_code.replace("-", "")
                count = 220 if p.default_code == "BAT-150" else 60
                for n in range(1, count + 1):
                    lot = Lot.create({"name": "%s-%s%04d" % (prefix, "26", n),
                                      "product_id": p.id})
                    Quant._update_available_quantity(p, loc, 1, lot_id=lot)
            elif p.tracking == "lot":
                for batch in ("A", "B", "C"):
                    lot = Lot.create({"name": "PNL-2026-%s" % batch, "product_id": p.id})
                    Quant._update_available_quantity(p, loc, 400, lot_id=lot)
            else:
                Quant._update_available_quantity(p, loc, 300 if p.uom_id.name != "m" else 3000)

    def _deliver(self, order, when):
        for picking in order.picking_ids.filtered(lambda p: p.state not in ("done", "cancel")):
            picking.action_assign()
            for move in picking.move_ids:
                if move.quantity < move.product_uom_qty:
                    move.quantity = move.product_uom_qty
                move.picked = True
            picking.with_context(skip_backorder=True, cancel_backorder=True,
                                 skip_sms=True, solar_skip_advance_check=True).button_validate()
            picking.date_done = when
            picking.warranty_ids.write({"start_date": when.date()})

    def _install(self, order, techs, when, hours, rnd):
        for task in order.tasks_ids.filtered("is_installation"):
            crew = techs[rnd.randint(0, len(techs) - 3):][:rnd.randint(2, 3)]
            task.write({
                "user_ids": [(6, 0, crew.ids)], "installation_date": when,
                "chk_stands": True, "chk_panels": True, "chk_wiring": True,
                "chk_earthing": True, "chk_generation": True,
                "installation_kw_confirmed": order.solar_kw,
                "generation_reading_kw": round(order.solar_kw * rnd.uniform(.62, .81), 2),
                "signed_by": order.partner_id.name,
                "site_start": when, "site_end": when + timedelta(hours=hours),
                "installation_state": "done", "signed_on": when + timedelta(hours=hours),
            })
            for user in crew:
                self.env["account.analytic.line"].create({
                    "name": "Installation", "project_id": task.project_id.id,
                    "task_id": task.id, "employee_id": user.employee_id.id,
                    "unit_amount": hours, "date": when.date(),
                })

    def _invoice(self, order, when, mode):
        if mode == "none":
            return
        if mode == "advance":
            wiz = self.env["sale.advance.payment.inv"].with_context(
                active_model="sale.order", active_ids=order.ids).create({
                    "advance_payment_method": "percentage", "amount": 30})
            wiz.create_invoices()
            moves = order.invoice_ids.filtered(lambda m: m.state == "draft")
        else:
            moves = order._create_invoices()
        moves.write({"invoice_date": when.date()})
        moves.action_post()
        if mode in ("advance", "paid"):
            self.env["account.payment.register"].with_context(
                active_model="account.move", active_ids=moves.ids).create(
                {"payment_date": when.date()})._create_payments()

    # ---------------------------------------------------------------- main
    @api.model
    def load(self):
        if self.env["sale.order"].search_count([("is_solar_job", "=", True)]):
            raise UserError(_("Demo data already loaded (solar jobs exist)."))
        self._ensure_accounting()
        rnd = random.Random(42)
        techs = self._technicians()
        self._receive_stock()
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        Lead = self.env["crm.lead"]
        templates = self.env["sale.order.template"].search([("solar_kw", ">", 0)])
        won_stage = self.env["crm.stage"].search([("is_won", "=", True)], limit=1)

        plans = []
        # 2 old jobs (one out of inverter warranty) + 38 recent jobs
        plans.append({"days_ago": 800, "kw": 3, "type": "on_grid", "pay": "paid"})
        plans.append({"days_ago": 545, "kw": 5, "type": "off_grid", "pay": "paid"})
        for i in range(38):
            days = rnd.randint(0, 85)
            plans.append({
                "days_ago": days,
                "kw": rnd.choice([1, 2, 3, 3, 3, 4, 5]),
                "type": "off_grid" if rnd.random() < .3 else "on_grid",
                "pay": "paid" if days > 20 else rnd.choice(["advance", "advance", "paid", "invoiced"]),
                "loss": i in (4, 11, 23),
                "stage": "installed" if days > 10 else rnd.choice(["installed", "dispatched", "confirmed"]),
            })

        orders = self.env["sale.order"]
        for i, plan in enumerate(plans):
            when = now - timedelta(days=plan["days_ago"], hours=rnd.randint(0, 6))
            partner = self._partner(rnd, i)
            lead = Lead.create({
                "name": "%s kW %s – %s" % (plan["kw"], "Off-Grid" if plan["type"] == "off_grid" else "On-Grid", partner.name),
                "partner_id": partner.id, "type": "opportunity",
                "requested_kw": plan["kw"], "system_type": plan["type"],
                "roof_area_sqft": plan["kw"] * 110 + rnd.randint(0, 150),
                "monthly_bill": plan["kw"] * 1000 + rnd.randint(-200, 600),
                "grid_suitable": "yes", "subsidy_requested": plan["type"] == "on_grid",
                "enquiry_channel": rnd.choice(["web", "web", "whatsapp", "call", "referral"]),
                "discom": "Torrent Power", "consumer_no": "TP%09d" % rnd.randint(0, 10**9),
            })
            survey = self.env["solar.site.survey"].create({
                "lead_id": lead.id, "technician_id": rnd.choice(techs).id,
                "survey_date": when - timedelta(days=5), "roof_type": "rcc",
                "roof_direction": rnd.choice(["S", "S", "SE", "SW"]),
                "roof_tilt": rnd.choice([10, 15, 20]),
                "usable_area_sqft": lead.roof_area_sqft, "cable_distance_m": rnd.randint(8, 35),
                "recommended_kw": plan["kw"], "state": "approved",
            })
            tmpl = templates.filtered(lambda t: t.solar_kw == plan["kw"] and
                                      t.solar_system_type == plan["type"])[:1]
            order = self.env["sale.order"].create({
                "partner_id": partner.id, "opportunity_id": lead.id,
                "survey_id": survey.id, "sale_order_template_id": tmpl.id,
            })
            order._onchange_sale_order_template_id()
            if plan.get("loss"):
                for line in order.order_line:
                    line.discount = 22
            order.with_context(sunpower_no_invite=True).action_confirm()
            order.date_order = when
            lead.stage_id = won_stage
            stage = plan.get("stage", "installed")
            if stage in ("dispatched", "installed"):
                self._deliver(order, when + timedelta(days=2))
            if stage == "installed":
                hours = rnd.uniform(5, 8) if not plan.get("loss") else rnd.uniform(14, 20)
                self._install(order, techs, when + timedelta(days=3, hours=9), hours, rnd)
            self._invoice(order, when, plan["pay"] if stage == "installed" or plan["pay"] == "advance" else "advance")
            orders |= order

        # Subsidy pipeline at different stages
        states = ["draft", "applied", "inspection", "approved", "disbursed"]
        for sub in self.env["solar.subsidy.application"].search([]):
            age = (now - sub.sale_order_id.date_order).days
            st = states[min(age // 15, 4)]
            vals = {"state": st, "portal_application_no": "PMSG-GJ-%06d" % sub.id,
                    "doc_aadhaar": True, "doc_bill": True, "doc_bank": st != "draft",
                    "doc_photo": st not in ("draft",), "doc_net_meter": st in ("approved", "disbursed")}
            if st != "draft":
                vals["applied_on"] = (sub.sale_order_id.date_order + timedelta(days=4)).date()
            if st == "disbursed":
                vals.update(amount_received=sub.amount_expected,
                            disbursed_on=(sub.sale_order_id.date_order + timedelta(days=60)).date())
            sub.write(vals)

        # Service tickets
        installed = orders.filtered(lambda o: o.warranty_ids)
        for n, (code, desc) in enumerate(FAULTS):
            order = installed[n] if n < 2 else rnd.choice(installed)
            w = order.warranty_ids.filtered(lambda w: "Inverter" in w.product_id.name)[:1] \
                or order.warranty_ids[:1]
            ticket = self.env["solar.service.ticket"].create({
                "partner_id": order.partner_id.id, "lot_id": w.lot_id.id,
                "fault_code": code, "description": desc,
                "reported_on": now - timedelta(days=rnd.randint(0, 6)),
                "user_id": rnd.choice(techs).id, "priority": rnd.choice(["0", "1", "2"]),
            })
            if n in (2, 3):
                ticket.action_diagnose()
            if n == 3:
                ticket.action_start_repair()
        # one fully closed warranty repair adds cost to its job
        closed_order = installed[-1]
        w = closed_order.warranty_ids[:1]
        inverter = w.product_id
        t = self.env["solar.service.ticket"].create({
            "partner_id": closed_order.partner_id.id, "lot_id": w.lot_id.id,
            "description": "Replaced faulty unit", "reported_on": now - timedelta(days=9),
            "labour_hours": 3, "resolution": "<p>Unit replaced under warranty.</p>",
            "line_ids": [(0, 0, {"product_id": inverter.id, "quantity": 1,
                                 "price_unit": inverter.lst_price})],
        })
        t.action_resolve()
        t.action_customer_confirm()

        # Fresh pipeline: enquiries at each stage
        for i in range(6):
            p_name = "%s %s" % (rnd.choice(FIRST), rnd.choice(LAST))
            lead = Lead.solar_create_enquiry({
                "name": "%s kW enquiry – %s" % (rnd.choice([2, 3, 5]), p_name),
                "contact_name": p_name, "phone": "+91 97%08d" % rnd.randint(0, 99999999),
                "city": "Ahmedabad", "requested_kw": rnd.choice([2, 3, 5]),
                "subsidy_requested": True,
            }, channel=rnd.choice(["web", "whatsapp", "call"]))
            if i >= 2:
                lead.write({"roof_area_sqft": 400, "monthly_bill": 3200, "grid_suitable": "yes"})
            if i >= 4:
                lead.action_schedule_survey()
                lead.survey_ids.write({"technician_id": techs[i].id,
                                       "survey_date": now + timedelta(days=1)})

        orders._solar_refresh_job_financials()
        self.env["solar.role.setup"].apply()
        return {"type": "ir.actions.client", "tag": "reload"}
