"""Phase-by-phase health checks for the SunPower system.

Run inside the Odoo shell, e.g. for phase 1:
  Get-Content scripts\\phase_checks.py | & "C:\\Users\\Ankit Kumar\\odoo18\\venv\\Scripts\\python.exe" `
      "C:\\Users\\Ankit Kumar\\odoo18\\odoo\\odoo-bin" shell -c "C:\\Users\\Ankit Kumar\\odoo18\\odoo.conf" -d sunpower
Set PHASES below to choose which phases to run.
"""
PHASES = [1, 2, 3]

results = []


def check(phase, label, ok, detail=""):
    results.append((phase, label, bool(ok), detail))


def phase1(env):
    c = env.company
    check(1, "Company is SunPower Solutions", c.name == "SunPower Solutions", c.name)
    check(1, "Country is India", c.country_id.code == "IN", c.country_id.name)
    check(1, "Currency is Indian Rupee", c.currency_id.name == "INR", c.currency_id.name)
    check(1, "Indian (GST) chart of accounts", c.chart_template == "in", c.chart_template)
    check(1, "Company state set (needed for GST invoices)", bool(c.state_id), c.state_id.name)
    gst = env["account.tax"].search_count([("company_id", "=", c.id), ("name", "ilike", "GST")])
    check(1, "GST taxes available", gst > 0, "%s GST taxes" % gst)
    mods = env["ir.module.module"].search([("name", "in", ("sunpower_solar", "sunpower_website"))])
    for m in mods:
        check(1, "Module %s installed" % m.name, m.state == "installed", m.state)
    check(1, "Serial/lot tracking switched on",
          env.user.has_group("stock.group_production_lot"))
    kits = env["product.template"].search_count([("is_solar_kit", "=", True)])
    check(1, "10 solar packages (1-5 kW x On/Off-grid)", kits == 10, kits)
    boms = env["mrp.bom"].search_count([("type", "=", "phantom"),
                                        ("product_tmpl_id.is_solar_kit", "=", True)])
    check(1, "Each package has a parts list (kit BoM)", boms == 10, boms)
    tmpls = env["sale.order.template"].search_count([("solar_kw", ">", 0)])
    check(1, "10 quotation templates", tmpls == 10, tmpls)
    for xmlid, months in [("sunpower_solar.categ_panel", 240), ("sunpower_solar.categ_inverter", 24),
                          ("sunpower_solar.categ_battery", 24), ("sunpower_solar.categ_controller", 24)]:
        cat = env.ref(xmlid)
        check(1, "Warranty for %s = %s months" % (cat.name, months),
              cat.solar_warranty_months == months, cat.solar_warranty_months)
    serial = env["product.product"].search([("tracking", "=", "serial")]).mapped("default_code")
    check(1, "Inverters, batteries, controllers tracked by serial",
          {"MPPT-60", "BAT-150", "INV-3KW"} <= set(serial), ", ".join(sorted(serial)))
    techs = env["res.users"].search_count([("login", "=like", "tech%@sunpower.demo")])
    check(1, "15 technician logins", techs == 15, techs)
    no_cost = env["hr.employee"].search([("user_id.login", "=like", "tech%@sunpower.demo"),
                                         ("hourly_cost", "=", 0)])
    check(1, "Every technician has an hourly cost", not no_cost, len(no_cost))
    menus = env.ref("sunpower_solar.menu_sunpower_root").child_id.mapped("name")
    check(1, "SunPower app menus", {"Dashboard", "Sales", "Operations", "Service", "Reports"} <= set(menus),
          ", ".join(menus))
    jobs = env["sale.order"].search_count([("is_solar_job", "=", True), ("state", "=", "sale")])
    check(1, "Sample data loaded (at least 40 jobs)", jobs >= 40, jobs)


def phase2(env):
    """Enquiry -> screening -> survey -> quote gate. Runs inside a savepoint and
    rolls back, so it leaves no data behind."""
    from odoo.exceptions import UserError
    Lead = env["crm.lead"]
    with env.cr.savepoint(flush=False) as sp:
        lead = Lead.solar_create_enquiry({
            "name": "P2 check", "contact_name": "Phase Two", "phone": "+91 90000 00002",
            "requested_kw": 3, "system_type": "on_grid", "monthly_bill": 3200,
            "roof_area_sqft": 420}, channel="web")
        check(2, "Website enquiry becomes an opportunity", lead.type == "opportunity")
        check(2, "Enquiry is assigned to a salesperson", bool(lead.user_id), lead.user_id.name)
        act = lead.activity_ids.filtered(lambda a: "2 hours" in (a.summary or ""))
        check(2, "'Call within 2 hours' reminder created", bool(act), act.date_deadline)
        check(2, "Suggested size from bill (₹3,200 -> 3 kW)", lead.recommended_kw == 3,
              lead.recommended_kw)
        try:
            lead.action_schedule_survey()
            check(2, "Survey refused before grid check", False)
        except UserError:
            check(2, "Survey refused before grid check", True)
        try:
            lead.action_new_quotation()
            check(2, "Quote refused with no survey", False)
        except UserError:
            check(2, "Quote refused with no survey", True)
        lead.grid_suitable = "yes"
        lead.action_schedule_survey()
        survey = lead.survey_ids[:1]
        check(2, "Survey created and pre-filled", survey and survey.usable_area_sqft == 420
              and survey.recommended_kw == 3, survey.name)
        check(2, "Max kW that fits (420 sq ft -> 4.2)", survey.max_kw_fit == 4.2,
              survey.max_kw_fit)
        try:
            survey.action_mark_done()
            check(2, "Visit refused without roof direction", False)
        except UserError:
            check(2, "Visit refused without roof direction", True)
        survey.write({"roof_direction": "S", "roof_tilt": 15})
        survey.action_mark_done()
        survey.action_approve()
        check(2, "Survey approved -> enquiry shows approved", lead.survey_state == "approved")
        ctx = lead._prepare_opportunity_quotation_context()
        tmpl = env["sale.order.template"].browse(ctx.get("default_sale_order_template_id"))
        check(2, "Quote picks the 3 kW On-Grid template", tmpl.solar_kw == 3 and
              tmpl.solar_system_type == "on_grid", tmpl.name)
        check(2, "Quotation templates switched on (so template applies)",
              env.user.has_group("sale_management.group_sale_order_template"))
        sp.rollback()


def phase3(env):
    """Quote -> GST -> estimate -> confirm -> packing list + crew job + subsidy ->
    advance rule. Savepoint + rollback."""
    from odoo.exceptions import UserError
    kit = env.ref("sunpower_solar.kit_on_grid_3kw")
    inst = env.ref("sunpower_solar.prod_installation")
    check(3, "Kit carries 12% GST", "12% GST S" in kit.taxes_id.mapped("name"),
          kit.taxes_id.mapped("name"))
    check(3, "Installation carries 18% GST", "18% GST S" in inst.taxes_id.mapped("name"),
          inst.taxes_id.mapped("name"))
    check(3, "HSN codes set (needed on GST invoices)",
          bool(kit.l10n_in_hsn_code and inst.l10n_in_hsn_code),
          "%s / %s" % (kit.l10n_in_hsn_code, inst.l10n_in_hsn_code))
    with env.cr.savepoint(flush=False) as sp:
        partner = env["res.partner"].create({
            "name": "P3 Customer", "state_id": env.ref("base.state_in_gj").id,
            "country_id": env.ref("base.in").id})
        lead = env["crm.lead"].create({
            "name": "P3", "partner_id": partner.id, "type": "opportunity",
            "requested_kw": 3, "system_type": "on_grid", "subsidy_requested": True,
            "roof_area_sqft": 400, "monthly_bill": 3000, "grid_suitable": "yes"})
        survey = env["solar.site.survey"].create({
            "lead_id": lead.id, "roof_direction": "S", "usable_area_sqft": 400,
            "recommended_kw": 3})
        survey.action_mark_done()
        survey.action_approve()
        so = env["sale.order"].create({
            "partner_id": partner.id, "opportunity_id": lead.id, "survey_id": survey.id,
            "sale_order_template_id": lead._solar_quotation_template().id})
        so._onchange_sale_order_template_id()
        check(3, "Quote total includes GST", round(so.amount_tax) == 19980,
              "tax %s, total %s" % (so.amount_tax, so.amount_total))
        so.action_compute_generation()
        check(3, "Generation & savings estimate filled", so.est_kwh_year > 3000 and
              so.est_savings_year > 0, "%s kWh, %s" % (so.est_kwh_year, so.est_source))
        so.action_confirm()
        bom = env["mrp.bom"]._bom_find(kit)[kit]
        moves = so.picking_ids.move_ids
        check(3, "Packing list = full parts list of the kit",
              len(moves) == len(bom.bom_line_ids), "%s lines" % len(moves))
        task = so.tasks_ids.filtered("is_installation")
        check(3, "Crew job created with a readable name", task and task.name.startswith("Install 3 kW"),
              task.name)
        check(3, "Job has its own cost account (for profit per job)",
              bool(so.project_ids.account_id))
        check(3, "Subsidy file opened automatically (₹78,000 for 3 kW)",
              so.subsidy_ids and so.subsidy_ids.amount_expected == 78000,
              so.subsidy_ids.amount_expected)
        pick = so.picking_ids
        try:
            pick._solar_check_advance()
            check(3, "Dispatch refused before 30% advance", False)
        except UserError:
            check(3, "Dispatch refused before 30% advance", True)
        wiz = env["sale.advance.payment.inv"].with_context(
            active_model="sale.order", active_ids=so.ids).create(
            {"advance_payment_method": "percentage", "amount": 30})
        wiz.create_invoices()
        inv = so.invoice_ids
        inv.action_post()
        check(3, "30% advance invoice amount correct", round(inv.amount_total) == round(so.amount_total * .3),
              inv.amount_total)
        env["account.payment.register"].with_context(
            active_model="account.move", active_ids=inv.ids).create({})._create_payments()
        try:
            pick._solar_check_advance()
            check(3, "Dispatch allowed after advance paid", True)
        except UserError:
            check(3, "Dispatch allowed after advance paid", False)
        sp.rollback()


for p in PHASES:
    globals()["phase%d" % p](env)

print("\n=== SunPower phase checks ===")
for phase, label, ok, detail in results:
    print("[%s] P%d %s%s" % ("PASS" if ok else "FAIL", phase, label,
                            ("  (%s)" % detail) if detail not in ("", None) else ""))
print("TOTAL: %d passed, %d failed" % (sum(r[2] for r in results),
                                       sum(not r[2] for r in results)))
