"""Master data for SunPower: product categories with warranty terms, kit
components, the 10 packages (1-5 kW x On/Off-grid) as phantom BoMs,
installation service, project template and quotation templates."""
import math

PANEL_W = 540

CATEGORIES = [
    # key, name, warranty months
    ("panel", "Solar Panels", 240),
    ("inverter", "Inverters", 24),
    ("battery", "Batteries", 24),
    ("controller", "Charge Controllers", 24),
    ("bos", "Balance of System", 0),
    ("kit", "Solar Packages", 0),
    ("service", "Solar Services", 0),
]

# code, name, category, tracking, cost, price
COMPONENTS = [
    ("PNL-540", "Solar Panel 540W Mono PERC", "panel", "lot", 11500, 14500),
    ("MPPT-60", "MPPT Charge Controller 60A", "controller", "serial", 4200, 5800),
    ("BAT-150", "Tubular Battery 150Ah 12V", "battery", "serial", 11000, 14000),
    ("STR-1KW", "GI Mounting Structure (per kW)", "bos", "none", 4500, 6000),
    ("DCDB-1", "DC Distribution Box (DCDB)", "bos", "none", 1800, 2500),
    ("ACDB-1", "AC Distribution Box (ACDB)", "bos", "none", 1600, 2200),
    ("MC4-PR", "MC4 Connector Pair", "bos", "none", 90, 150),
    ("CBL-DC4", "DC Solar Cable 4 sq mm (m)", "bos", "none", 45, 70),
    ("CBL-AC4", "AC Cable 4 sq mm (m)", "bos", "none", 55, 80),
    ("ERT-KIT", "Earthing Kit (chemical, 2 m)", "bos", "none", 1400, 2000),
    ("LA-1", "Lightning Arrester", "bos", "none", 1200, 1800),
]
INVERTER_COST = {1: 9000, 2: 14000, 3: 19000, 4: 24000, 5: 28000}


def _xmlid(env, record, name):
    env["ir.model.data"].create({
        "module": "sunpower_solar", "name": name,
        "model": record._name, "res_id": record.id, "noupdate": True,
    })


def _ref(env, name):
    return env.ref("sunpower_solar.%s" % name, raise_if_not_found=False)


def enable_settings(env):
    """Serial/lot tracking + quotation templates (needed so the quote picks the
    right package automatically) + down payments."""
    env["res.config.settings"].create({
        "group_stock_production_lot": True,
        "group_stock_tracking_lot": False,
        "group_sale_order_template": True,
    }).execute()
    # No "send an SMS?" pop-up on every dispatch (SMS isn't configured)
    company = env.company
    if "stock_move_sms_validation" in company._fields:
        company.write({"stock_move_sms_validation": False,
                       "has_received_warning_stock_sms": True})


HSN = {"panel": "85414300", "inverter": "85044010", "battery": "85072000",
       "controller": "85044090", "bos": "85371000", "kit": "85414300", "service": "995461"}


def apply_gst(env):
    """12% GST on solar goods (kits & components), 18% on installation services.
    Uses the intra-state group taxes (CGST+SGST); Odoo's fiscal positions switch
    to IGST automatically for customers in other states."""
    company = env.company
    Tax = env["account.tax"].with_context(active_test=True)

    def tax(name):
        return Tax.search([("name", "=", name), ("type_tax_use", "=", "sale"),
                           ("company_id", "=", company.id)], limit=1)
    goods, service = tax("12% GST S"), tax("18% GST S")
    if not goods or not service:
        return False
    Tmpl = env["product.template"]
    has_hsn = "l10n_in_hsn_code" in Tmpl._fields
    for key, _name, _m in CATEGORIES:
        cat = _ref(env, "categ_%s" % key)
        if not cat:
            continue
        products = Tmpl.search([("categ_id", "=", cat.id)])
        vals = {"taxes_id": [(6, 0, (service if key == "service" else goods).ids)]}
        if has_hsn:
            vals["l10n_in_hsn_code"] = HSN[key]
        products.write(vals)
    return True


def post_init_hook(env):
    company = env.company
    if company.name in ("My Company", "YourCompany"):
        company.write({"name": "SunPower Solutions", "city": "Ahmedabad",
                       "phone": "+91 79 4000 5000", "email": "hello@sunpower.example"})
    gujarat = env.ref("base.state_in_gj", raise_if_not_found=False)
    if gujarat and not company.state_id:
        company.write({"street": "12, Solar Park Road, SG Highway", "zip": "380054",
                       "city": "Ahmedabad", "state_id": gujarat.id,
                       "country_id": env.ref("base.in").id})

    enable_settings(env)

    cats = {}
    parent = env["product.category"].create({"name": "SunPower"})
    for key, name, months in CATEGORIES:
        cat = env["product.category"].create({
            "name": name, "parent_id": parent.id, "solar_warranty_months": months})
        _xmlid(env, cat, "categ_%s" % key)
        cats[key] = cat

    Product = env["product.product"]
    comp = {}
    for code, name, cat, tracking, cost, price in COMPONENTS:
        p = Product.create({
            "name": name, "default_code": code, "type": "consu",
            "is_storable": True, "tracking": tracking, "categ_id": cats[cat].id,
            "standard_price": cost, "list_price": price,
        })
        _xmlid(env, p, "prod_%s" % code.replace("-", "_").lower())
        comp[code] = p
    for kw, cost in INVERTER_COST.items():
        p = Product.create({
            "name": "Solar Inverter %s kW (Hybrid)" % kw, "default_code": "INV-%sKW" % kw,
            "type": "consu", "is_storable": True, "tracking": "serial",
            "categ_id": cats["inverter"].id, "standard_price": cost,
            "list_price": round(cost * 1.3, -2),
        })
        _xmlid(env, p, "prod_inv_%skw" % kw)
        comp["INV-%s" % kw] = p

    # Project template for installation jobs (one project per job = analytic account)
    template = env["project.project"].create({
        "name": "Installation Job Template", "allow_timesheets": True,
        "is_template": True,
    } if "is_template" in env["project.project"]._fields else {
        "name": "Installation Job Template", "allow_timesheets": True,
    })
    stages = env["project.task.type"]
    for seq, (sname, fold) in enumerate([("Planned", False), ("Material Dispatched", False),
                                         ("On Site", False), ("Completed", True)]):
        stages |= env["project.task.type"].create(
            {"name": sname, "sequence": seq, "fold": fold,
             "project_ids": [(4, template.id)]})
    _xmlid(env, template, "project_installation_template")

    install = Product.create({
        "name": "Solar Installation & Commissioning (per kW)",
        "default_code": "SRV-INSTALL", "type": "service",
        "categ_id": cats["service"].id, "list_price": 5000, "standard_price": 0,
        "service_tracking": "task_in_project", "project_template_id": template.id,
        "is_installation_service": True, "invoice_policy": "order",
    })
    _xmlid(env, install, "prod_installation")

    Bom = env["mrp.bom"]
    Tmpl = env["sale.order.template"]
    for system_type in ("on_grid", "off_grid"):
        for kw in range(1, 6):
            panels = math.ceil(kw * 1000 / PANEL_W)
            lines = [
                (comp["PNL-540"], panels), (comp["INV-%s" % kw], 1),
                (comp["MPPT-60"], 1), (comp["STR-1KW"], kw),
                (comp["DCDB-1"], 1), (comp["ACDB-1"], 1),
                (comp["MC4-PR"], 2 + panels // 2), (comp["CBL-DC4"], 20 + 5 * kw),
                (comp["CBL-AC4"], 15 + 2 * kw), (comp["ERT-KIT"], 3), (comp["LA-1"], 1),
            ]
            if system_type == "off_grid":
                lines.append((comp["BAT-150"], 2 * kw))
            cost = sum(p.standard_price * q for p, q in lines)
            label = "On-Grid" if system_type == "on_grid" else "Off-Grid"
            kit = Product.create({
                "name": "%s Solar System %s kW" % (label, kw),
                "default_code": "KIT-%s-%sKW" % ("ON" if system_type == "on_grid" else "OFF", kw),
                "type": "consu", "is_storable": False, "categ_id": cats["kit"].id,
                "is_solar_kit": True, "solar_kw": kw, "solar_system_type": system_type,
                "standard_price": cost, "list_price": round(cost * 1.22, -3),
                "invoice_policy": "order",
            })
            _xmlid(env, kit, "kit_%s_%skw" % (system_type, kw))
            Bom.create({
                "product_tmpl_id": kit.product_tmpl_id.id, "type": "phantom",
                "product_qty": 1,
                "bom_line_ids": [(0, 0, {"product_id": p.id, "product_qty": q})
                                 for p, q in lines],
            })
            qt = Tmpl.create({
                "name": "%s %s kW Rooftop Package" % (label, kw),
                "solar_kw": kw, "solar_system_type": system_type,
                "number_of_days": 15,
                "note": "Prices include GST-exclusive supply of the complete kit. "
                        "Installation, net-metering paperwork and subsidy filing "
                        "handled by SunPower. Panels: 20-year warranty. "
                        "Inverter, batteries & controller: 2-year warranty.",
                "sale_order_template_line_ids": [
                    (0, 0, {"product_id": kit.id, "product_uom_qty": 1}),
                    (0, 0, {"product_id": install.id, "product_uom_qty": kw}),
                ],
            })
            _xmlid(env, qt, "qt_%s_%skw" % (system_type, kw))
    apply_gst(env)
