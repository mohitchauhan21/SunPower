from datetime import datetime, time, timedelta

from odoo import _, api, fields, models


class SolarDashboard(models.AbstractModel):
    _name = "solar.dashboard"
    _description = "Director Dashboard Data"

    @api.model
    def _period_bounds(self, period):
        today = fields.Date.context_today(self)
        if period == "today":
            start = today
        elif period == "week":
            start = today - timedelta(days=today.weekday())
        elif period == "year":
            start = today.replace(month=1, day=1)
        else:
            start = today.replace(day=1)
        return start, today

    @api.model
    def get_data(self, period="month", refresh=False):
        start, end = self._period_bounds(period)
        dt_start = datetime.combine(start, time.min)
        dt_end = datetime.combine(end, time.max)
        env = self.env
        cur = env.company.currency_id

        orders_won = env["sale.order"].search([
            ("is_solar_job", "=", True), ("state", "=", "sale"),
            ("date_order", ">=", dt_start), ("date_order", "<=", dt_end)])
        all_jobs = env["sale.order"].search([("is_solar_job", "=", True),
                                             ("state", "=", "sale")])
        if refresh:
            all_jobs._solar_refresh_job_financials()

        invoices = env["account.move"].search([
            ("move_type", "in", ("out_invoice", "out_refund")), ("state", "=", "posted"),
            ("invoice_date", ">=", start), ("invoice_date", "<=", end)])
        payments = env["account.payment"].search([
            ("payment_type", "=", "inbound"), ("state", "not in", ("draft", "canceled")),
            ("date", ">=", start), ("date", "<=", end)])
        Task = env["project.task"]
        installs_done = Task.search_count([
            ("is_installation", "=", True), ("site_end", ">=", dt_start),
            ("site_end", "<=", dt_end)])
        installs_pending = Task.search([("is_installation", "=", True),
                                        ("installation_state", "!=", "done")])
        Ticket = env["solar.service.ticket"]
        open_tickets = Ticket.search([("stage", "not in", ("closed", "cancel"))])
        tickets_new = Ticket.search_count([("reported_on", ">=", dt_start),
                                           ("reported_on", "<=", dt_end)])
        subsidies = env["solar.subsidy.application"].search(
            [("state", "not in", ("disbursed", "rejected"))])
        leads_new = env["crm.lead"].search_count([("create_date", ">=", dt_start),
                                                  ("create_date", "<=", dt_end)])
        stock_groups = env["stock.quant"]._read_group(
            [("location_id.usage", "=", "internal")], ["product_id"], ["quantity:sum"])
        stock_value = sum(p.standard_price * qty for p, qty in stock_groups)

        period_jobs = orders_won
        jobs = []
        for o in (period_jobs if period != "today" else all_jobs)[:60]:
            jobs.append({
                "id": o.id, "name": o.name, "customer": o.partner_id.name,
                "kw": o.solar_kw,
                "type": dict(o._fields["solar_system_type"].selection).get(
                    o.solar_system_type, ""),
                "revenue": o.amount_untaxed, "material": o.job_material_cost,
                "labour": o.job_labour_cost, "repair": o.job_repair_cost,
                "profit": o.job_profit, "margin": o.job_margin,
                "stage": dict(o._fields["job_stage"].selection).get(o.job_stage, ""),
                "pending": o.job_pending_steps or "",
            })
        jobs.sort(key=lambda j: j["profit"])

        unfinished = all_jobs.filtered(lambda o: o.job_stage != "closed")
        return {
            "period": period,
            "period_label": "%s → %s" % (start.strftime("%d %b"), end.strftime("%d %b %Y")),
            "currency": cur.symbol,
            "kpi": {
                "leads_new": leads_new,
                "orders_won": len(orders_won),
                "orders_value": sum(orders_won.mapped("amount_untaxed")),
                "kw_sold": sum(orders_won.mapped("solar_kw")),
                "invoiced": sum(invoices.mapped("amount_untaxed_signed")),
                "collected": sum(payments.mapped("amount")),
                "profit": sum(orders_won.mapped("job_profit")),
                "loss_jobs": len(orders_won.filtered(lambda o: o.job_profit < 0)),
                "installs_done": installs_done,
                "installs_pending": len(installs_pending),
                "unfinished_jobs": len(unfinished),
                "receivable": sum(env["account.move"].search([
                    ("move_type", "=", "out_invoice"), ("state", "=", "posted"),
                    ("payment_state", "in", ("not_paid", "partial"))
                ]).mapped("amount_residual")),
                "tickets_open": len(open_tickets),
                "tickets_new": tickets_new,
                "tickets_overdue": len(open_tickets.filtered(lambda t: t.days_open > 3)),
                "subsidy_pending": len(subsidies),
                "subsidy_amount": sum(subsidies.mapped("amount_expected")),
                "stock_value": stock_value,
            },
            "jobs": jobs,
            "tickets": [{
                "id": t.id, "name": t.name, "customer": t.partner_id.name,
                "product": t.product_id.display_name or "",
                "stage": dict(t._fields["stage"].selection)[t.stage],
                "warranty": t.under_warranty, "days": t.days_open,
            } for t in open_tickets[:15]],
            "unfinished": [{
                "id": o.id, "name": o.name, "customer": o.partner_id.name,
                "pending": o.job_pending_steps or "",
            } for o in unfinished[:15]],
        }


class SolarDirectorReport(models.TransientModel):
    _name = "solar.director.report"
    _description = "Share Director Report"

    period = fields.Selection([("today", "Today"), ("week", "This Week"),
                               ("month", "This Month"), ("year", "This Year")],
                              default="month", required=True)
    email_to = fields.Char("Send To (email)")

    def _get_data(self):
        return self.env["solar.dashboard"].get_data(self.period)

    def action_print(self):
        return self.env.ref("sunpower_solar.action_report_director").report_action(self)

    def action_send(self):
        self.ensure_one()
        report = self.env.ref("sunpower_solar.action_report_director")
        pdf, _fmt = self.env["ir.actions.report"]._render_qweb_pdf(report, self.ids)
        att = self.env["ir.attachment"].create({
            "name": "SunPower-%s-report.pdf" % self.period, "type": "binary",
            "raw": pdf, "mimetype": "application/pdf",
        })
        self.env["mail.mail"].create({
            "subject": _("SunPower performance report (%s)", self.period),
            "email_to": self.email_to,
            "body_html": _("<p>Please find attached the SunPower performance report.</p>"),
            "attachment_ids": [(6, 0, att.ids)],
        }).send()
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"message": _("Report sent to %s", self.email_to),
                           "type": "success", "next": {"type": "ir.actions.act_window_close"}}}
