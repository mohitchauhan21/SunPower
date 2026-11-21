"""Phase-by-phase health checks for the SunPower system.

Run inside the Odoo shell, e.g. for phase 1:
  Get-Content scripts\\phase_checks.py | & "C:\\Users\\Ankit Kumar\\odoo18\\venv\\Scripts\\python.exe" `
      "C:\\Users\\Ankit Kumar\\odoo18\\odoo\\odoo-bin" shell -c "C:\\Users\\Ankit Kumar\\odoo18\\odoo.conf" -d sunpower
Set PHASES below to choose which phases to run.
"""
PHASES = [1, 2, 3, 4, 5]

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
        env.flush_all()
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
        env.flush_all()
        sp.rollback()
    env.invalidate_all()


def _confirmed_job(env, kw=3, system_type="on_grid"):
    """Helper: a confirmed solar order with an approved survey (inside caller's savepoint)."""
    partner = env["res.partner"].create({
        "name": "Check Customer %s" % kw, "phone": "+91 90000 0000%s" % kw,
        "state_id": env.ref("base.state_in_gj").id, "country_id": env.ref("base.in").id})
    lead = env["crm.lead"].create({
        "name": "check", "partner_id": partner.id, "type": "opportunity",
        "requested_kw": kw, "system_type": system_type})
    survey = env["solar.site.survey"].create({
        "lead_id": lead.id, "roof_direction": "S", "usable_area_sqft": 500,
        "recommended_kw": kw})
    survey.action_mark_done()
    survey.action_approve()
    so = env["sale.order"].create({
        "partner_id": partner.id, "opportunity_id": lead.id, "survey_id": survey.id,
        "sale_order_template_id": lead._solar_quotation_template().id})
    so._onchange_sale_order_template_id()
    so.action_confirm()
    return so


def _dispatch(so):
    pick = so.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))
    pick.action_assign()
    for m in pick.move_ids:
        m.quantity = m.product_uom_qty
        m.picked = True
    return pick, pick.with_context(skip_backorder=True, cancel_backorder=True,
                                   solar_skip_advance_check=True).button_validate()


def phase4(env):
    """Serial scanning at dispatch + automatic warranties. Savepoint + rollback."""
    from dateutil.relativedelta import relativedelta
    from odoo import fields
    from odoo.exceptions import UserError
    check(4, "No SMS pop-up on dispatch", not env.company.stock_move_sms_validation)
    with env.cr.savepoint(flush=False) as sp:
        so = _confirmed_job(env, 2, "off_grid")
        pick = so.picking_ids
        pick.action_assign()
        for ml in pick.move_line_ids.filtered(lambda l: l.product_id.tracking != "none"):
            ml.lot_id = False
        for m in pick.move_ids:
            m.quantity = m.product_uom_qty
            m.picked = True
        try:
            pick.with_context(skip_backorder=True, solar_skip_advance_check=True).button_validate()
            check(4, "Dispatch refused without scanned serials", False)
        except UserError:
            check(4, "Dispatch refused without scanned serials", True)
        env.flush_all()
        sp.rollback()
    env.invalidate_all()
    with env.cr.savepoint(flush=False) as sp:
        so = _confirmed_job(env, 2, "off_grid")
        pick, res = _dispatch(so)
        check(4, "Dispatch completes in one click (no extra pop-up)", res is True and pick.state == "done",
              pick.state)
        today = fields.Date.context_today(pick)
        ws = so.warranty_ids
        serial_lines = pick.move_line_ids.filtered("lot_id")
        check(4, "One warranty per scanned serial/batch", len(ws) == len(serial_lines.mapped("lot_id")),
              "%s warranties" % len(ws))
        batts = ws.filtered(lambda w: w.product_id.default_code == "BAT-150")
        check(4, "Off-Grid 2 kW: 4 batteries each with own warranty", len(batts) == 4, len(batts))
        inv = ws.filtered(lambda w: w.product_id.default_code.startswith("INV"))
        check(4, "Inverter warranty = 2 years from delivery",
              inv and inv.end_date == today + relativedelta(months=24), inv.end_date)
        pnl = ws.filtered(lambda w: w.product_id.default_code == "PNL-540")
        check(4, "Panel warranty = 20 years from delivery",
              pnl and pnl.end_date == today + relativedelta(months=240), pnl.end_date)
        lot = env["stock.lot"].search([("name", "=", inv.serial)])
        check(4, "Serial number finds the customer", lot.solar_partner_id == so.partner_id,
              lot.solar_partner_id.name)
        check(4, "Job moves to 'Dispatched'", (so._solar_refresh_job_financials() or True)
              and so.job_stage == "dispatched", so.job_stage)
        check(4, "Material cost counted on the job", so.job_material_cost > 0, so.job_material_cost)
        env.flush_all()
        sp.rollback()
    env.invalidate_all()


def phase5(env):
    """Crew form rules, timesheets, certificate e-mail. Savepoint + rollback."""
    import base64
    from odoo.exceptions import UserError
    tech = env["res.users"].search([("login", "=", "tech01@sunpower.demo")])
    with env.cr.savepoint(flush=False) as sp:
        so = _confirmed_job(env, 3)
        so.partner_id.email = "check.customer@example.com"
        _dispatch(so)
        task = so.tasks_ids.filtered("is_installation")
        task.user_ids = tech
        t = task.with_user(tech)
        check(5, "Technician sees the job in My Jobs", t in env["project.task"].with_user(tech).search(
            [("is_installation", "=", True), ("user_ids", "in", tech.id)]))
        t.action_start_work()
        refused = 0
        for vals in [{}, {"chk_stands": True, "chk_panels": True, "chk_wiring": True,
                          "chk_earthing": True, "chk_generation": True},
                     {"install_photo_ids": [(0, 0, {"name": "p.png", "datas": base64.b64encode(b"x")})]},
                     {"installation_kw_confirmed": 3}]:
            t.write(vals)
            try:
                t.action_finish_work()
            except UserError:
                refused += 1
        check(5, "Finish refused until checklist, photo, kW and signature", refused == 4, refused)
        t.write({"customer_signature": base64.b64encode(b"sig"), "signed_by": "Check"})
        t.action_finish_work()
        check(5, "Technician (no e-mail of own) can finish the job", task.installation_state == "done")
        lines = env["account.analytic.line"].search([("task_id", "=", task.id)])
        check(5, "Hours logged per technician on the job", len(lines) == 1 and lines.amount < 0,
              "%s line(s), cost %s" % (len(lines), sum(lines.mapped("amount"))))
        msg = env["mail.message"].search([("model", "=", "project.task"), ("res_id", "=", task.id),
                                          ("attachment_ids", "!=", False)], limit=1)
        check(5, "Certificate e-mailed to customer with PDF attached", bool(msg),
              msg.attachment_ids.mapped("name"))
        so._solar_refresh_job_financials()
        check(5, "Job moves to 'Installed' with labour cost", so.job_stage == "installed"
              and so.job_labour_cost > 0, "%s / %s" % (so.job_stage, so.job_labour_cost))
        env.flush_all()
        sp.rollback()
    env.invalidate_all()


for p in PHASES:
    globals()["phase%d" % p](env)

print("\n=== SunPower phase checks ===")
for phase, label, ok, detail in results:
    print("[%s] P%d %s%s" % ("PASS" if ok else "FAIL", phase, label,
                            ("  (%s)" % detail) if detail not in ("", None) else ""))
print("TOTAL: %d passed, %d failed" % (sum(r[2] for r in results),
                                       sum(not r[2] for r in results)))
