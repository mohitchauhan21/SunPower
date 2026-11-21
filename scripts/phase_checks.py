"""Phase-by-phase health checks for the SunPower system.

Run inside the Odoo shell, e.g. for phase 1:
  Get-Content scripts\\phase_checks.py | & "C:\\Users\\Ankit Kumar\\odoo18\\venv\\Scripts\\python.exe" `
      "C:\\Users\\Ankit Kumar\\odoo18\\odoo\\odoo-bin" shell -c "C:\\Users\\Ankit Kumar\\odoo18\\odoo.conf" -d sunpower
Set PHASES below to choose which phases to run.
"""
PHASES = [1, 2]

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
    check(1, "Sample data loaded (40 jobs)", jobs == 40, jobs)


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


for p in PHASES:
    globals()["phase%d" % p](env)

print("\n=== SunPower phase checks ===")
for phase, label, ok, detail in results:
    print("[%s] P%d %s%s" % ("PASS" if ok else "FAIL", phase, label,
                            ("  (%s)" % detail) if detail not in ("", None) else ""))
print("TOTAL: %d passed, %d failed" % (sum(r[2] for r in results),
                                       sum(not r[2] for r in results)))
