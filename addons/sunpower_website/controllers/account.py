"""Customer accounts for the React website: sign up, the "My account" overview
(enquiries, orders, installation progress, warranties, repairs), raising a
complaint, confirming a repair, and profile / password.

Security notes:
- Sign-up only ever creates customer (portal) accounts.
- Signing up with an email that already belongs to an account or a known customer
  never logs anyone in: a single-use link is emailed to that address instead, so
  only the owner of the inbox can claim it.
- Every read below is filtered to the signed-in customer's own company/contact.
"""
import logging
import re

from markupsafe import Markup, escape

from odoo import _, fields, http
from odoo.exceptions import AccessDenied, UserError
from odoo.http import request

from urllib.parse import urlencode

from odoo.addons.payment import utils as payment_utils
from odoo.addons.sale.controllers.portal import PaymentPortal as SalePaymentPortal

from .auth import MIN_PASSWORD, _engine_url, _frontend_url, _rate_limited

_logger = logging.getLogger(__name__)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CHECK_EMAIL_MSG = ("This email already has a SunPower account. We've emailed you a link "
                   "to choose a password and sign in.")


def _date(v):
    return fields.Date.to_string(v) if v else None


def _dt(v):
    return fields.Datetime.to_string(v) if v else None


def _label(record, field):
    return dict(record._fields[field]._description_selection(record.env)).get(record[field])


class SunpowerAccountApi(http.Controller):

    # ------------------------------------------------------------------ sign up
    @http.route("/api/sunpower/auth/signup", type="json", auth="public", csrf=False)
    def signup(self, name="", email="", phone="", password="", **kw):
        name = (name or "").strip()[:120]
        email = (email or "").strip().lower()[:200]
        phone = (phone or "").strip()[:40]
        if not name:
            return {"ok": False, "field": "name", "error": _("Please enter your name.")}
        if not EMAIL_RE.match(email):
            return {"ok": False, "field": "email", "error": _("Please enter a valid email address.")}
        if len(password or "") < MIN_PASSWORD:
            return {"ok": False, "field": "password",
                    "error": _("Use at least %s characters for your password.", MIN_PASSWORD)}
        if _rate_limited("signup:" + email):
            return {"ok": False, "error": _("Too many attempts. Please try again in an hour.")}

        Users = request.env["res.users"].sudo().with_context(active_test=False)
        user = Users.search(["|", ("login", "=ilike", email), ("email", "=ilike", email)], limit=1)
        if user:
            if user.active:
                user._sunpower_send_account_email("claim")
            return {"ok": True, "status": "check_email", "message": CHECK_EMAIL_MSG}

        # A known customer (enquired or bought before) without a login yet
        partner = request.env["res.partner"].sudo().search(
            [("email", "=ilike", email), ("user_ids", "=", False)], limit=1)
        if partner:
            portal = request.env.ref("base.group_portal")
            new = Users.with_context(no_reset_password=True).create({
                "name": partner.name, "login": email, "email": email,
                "partner_id": partner.id, "groups_id": [(6, 0, [portal.id])]})
            new._sunpower_send_account_email("claim")
            return {"ok": True, "status": "check_email", "message": CHECK_EMAIL_MSG}

        try:
            # our own gate above decides who may sign up; the portal template
            # user guarantees a customer-only account
            new = request.env["res.users"].sudo().with_context(no_reset_password=True)._create_user_from_template(
                {"login": email, "email": email, "name": name, "password": password})
            login, pwd = new.login, password
            if phone:
                new.partner_id.phone = phone
            request.env.cr.commit()  # authenticate() uses its own cursor
            request.session.authenticate(request.db, {"login": login, "password": pwd, "type": "password"})
        except Exception:
            _logger.exception("SunPower: sign-up failed")
            request.env.cr.rollback()
            return {"ok": False, "error": _("We couldn't create your account. Please try again.")}
        return {"ok": True, "status": "created", "home": "/account"}

    # ----------------------------------------------------------------- helpers
    def _customer(self):
        user = request.env.user
        if user._is_public():
            raise AccessDenied()
        return user.partner_id.commercial_partner_id

    def _mine(self, model, field="partner_id"):
        return request.env[model].sudo().search([(field, "child_of", self._customer().id)])

    # ---------------------------------------------------------------- overview
    @http.route("/api/sunpower/my/overview", type="json", auth="user", csrf=False)
    def overview(self, **kw):
        partner = self._customer()
        env = request.env
        engine = _engine_url()

        leads = env["crm.lead"].sudo().search(
            [("partner_id", "child_of", partner.id)], order="create_date desc", limit=10)
        orders = env["sale.order"].sudo().search(
            [("partner_id", "child_of", partner.id), ("state", "in", ("sent", "sale"))],
            order="date_order desc")
        enquiries = []
        for lead in leads.filtered(lambda l: not (l.order_ids & orders)):
            survey = lead.survey_ids[:1] if "survey_ids" in lead._fields else env["solar.site.survey"]
            enquiries.append({
                "id": lead.id, "name": lead.name, "created": _dt(lead.create_date),
                "kw": lead.requested_kw or 0, "stage": lead.stage_id.name,
                "survey": survey and {
                    "state": _label(survey, "state"),
                    "date": _dt(survey.survey_date) if "survey_date" in survey._fields else None,
                    "technician": survey.technician_id.name or None,
                } or None,
            })

        out_orders = []
        for o in orders:
            o._portal_ensure_token()
            paid = o._solar_paid_amount()
            advance_due = max(o._solar_advance_needed() - paid, 0) if o.state == "sale" else 0
            pending_tx = o.transaction_ids.filtered(lambda t: t.state in ("pending", "authorized"))
            jobs = o.tasks_ids.filtered("is_installation")
            job = jobs[:1]
            delivered = any(p.state == "done" for p in o.picking_ids)
            installed = bool(job) and job.installation_state == "done"
            checklist = [job.chk_stands, job.chk_panels, job.chk_wiring, job.chk_earthing,
                         job.chk_generation] if job else []
            subsidy = o.subsidy_ids[:1] if "subsidy_ids" in o._fields else None
            out_orders.append({
                "id": o.id, "name": o.name, "kw": o.solar_kw or 0,
                "state": o.state, "quote_pending": o.state == "sent",
                "date": _dt(o.date_order), "total": o.amount_total, "paid": paid,
                "due": max(o.amount_total - paid, 0),
                "advance_pct": o.company_id.solar_min_advance_pct or 0,
                "advance_due": round(advance_due, 2),
                "payment_pending": bool(pending_tx),
                "pdf_url": "%s/my/orders/%s?access_token=%s&report_type=pdf&download=true"
                           % (engine, o.id, o.access_token),
                "review_url": "%s/my/orders/%s?access_token=%s" % (engine, o.id, o.access_token),
                "steps": [
                    {"label": _("Order confirmed"), "done": o.state == "sale"},
                    {"label": _("Advance paid"), "done": o.state == "sale" and not advance_due},
                    {"label": _("Kit dispatched"), "done": delivered},
                    {"label": _("Installation scheduled"), "done": bool(job and job.installation_date),
                     "date": _dt(job.installation_date) if job else None},
                    {"label": _("Crew on site"), "done": bool(job) and job.installation_state in ("in_progress", "done")},
                    {"label": _("Tested & handed over"), "done": installed},
                ],
                "checklist_done": sum(1 for c in checklist if c), "checklist_total": len(checklist) or 5,
                "subsidy": subsidy and {"state": _label(subsidy, "state"),
                                        "amount": subsidy.amount_expected} or None,
            })

        warranties = self._mine("solar.warranty").sorted("end_date")
        tickets = self._mine("solar.service.ticket").sorted("reported_on", reverse=True)
        return {
            "customer": {"name": partner.name, "email": partner.email, "phone": partner.phone,
                         "street": partner.street, "city": partner.city},
            "enquiries": enquiries,
            "orders": out_orders,
            "warranties": [{
                "id": w.id, "product": w.product_id.name, "serial": w.serial,
                "start": _date(w.start_date), "end": _date(w.end_date),
                "active": w.state == "active", "days_left": w.days_left,
            } for w in warranties],
            "tickets": [{
                "id": t.id, "name": t.name, "stage": t.stage, "stage_label": _label(t, "stage"),
                "product": t.product_id.name or None, "serial": t.lot_id.name or None,
                "reported": _dt(t.reported_on), "closed": _dt(t.closed_on),
                "description": t.description or "", "fault_code": t.fault_code or None,
                "under_warranty": t.under_warranty,
                "charge": 0 if t.under_warranty else t.customer_charge,
                "technician": t.user_id.name or None,
                "resolution": Markup(t.resolution or "").striptags() or None,
                "can_confirm": t.stage == "awaiting",
            } for t in tickets],
        }

    # -------------------------------------------------------------- complaints
    @http.route("/api/sunpower/my/complaint", type="json", auth="user", csrf=False)
    def complaint(self, description="", fault_code="", warranty_id=None, **kw):
        partner = self._customer()
        description = (description or "").strip()[:2000]
        if len(description) < 10:
            return {"ok": False, "field": "description",
                    "error": _("Please describe the problem in a few words (at least 10 characters).")}
        vals = {"partner_id": request.env.user.partner_id.id, "description": description,
                "fault_code": (fault_code or "").strip()[:20] or False}
        if warranty_id:
            warranty = request.env["solar.warranty"].sudo().search(
                [("id", "=", int(warranty_id)), ("partner_id", "child_of", partner.id)], limit=1)
            if not warranty:
                return {"ok": False, "field": "warranty_id", "error": _("Please pick your own equipment.")}
            vals["lot_id"] = warranty.lot_id.id
        ticket = request.env["solar.service.ticket"].sudo().create(vals)
        ticket.message_post(body=_("Complaint raised by the customer from the website."))
        return {"ok": True, "id": ticket.id, "name": ticket.name}

    def _my_ticket(self, ticket_id):
        ticket = request.env["solar.service.ticket"].sudo().search(
            [("id", "=", int(ticket_id or 0)), ("partner_id", "child_of", self._customer().id)], limit=1)
        if not ticket:
            raise UserError(_("Request not found."))
        return ticket

    @http.route("/api/sunpower/my/ticket/confirm", type="json", auth="user", csrf=False)
    def ticket_confirm(self, ticket_id=None, **kw):
        ticket = self._my_ticket(ticket_id)
        if ticket.stage != "awaiting":
            return {"ok": False, "error": _("This request is not waiting for your confirmation.")}
        ticket.action_customer_confirm()
        return {"ok": True}

    @http.route("/api/sunpower/my/ticket/reopen", type="json", auth="user", csrf=False)
    def ticket_reopen(self, ticket_id=None, note="", **kw):
        ticket = self._my_ticket(ticket_id)
        if ticket.stage != "awaiting":
            return {"ok": False, "error": _("This request is not waiting for your confirmation.")}
        ticket.action_reopen()
        note = (note or "").strip()[:1000]
        ticket.message_post(body=Markup("%s<br/>%s") % (
            _("Customer says the problem is not fixed."), escape(note) if note else ""))
        return {"ok": True}

    # ----------------------------------------------------------------- profile
    @http.route("/api/sunpower/my/profile", type="json", auth="user", csrf=False)
    def profile(self, name=None, phone=None, street=None, city=None, **kw):
        user = request.env.user
        vals = {}
        if name is not None:
            name = name.strip()[:120]
            if not name:
                return {"ok": False, "field": "name", "error": _("Please enter your name.")}
            vals["name"] = name
        for key, value in (("phone", phone), ("street", street), ("city", city)):
            if value is not None:
                vals[key] = value.strip()[:200] or False
        if vals:
            user.partner_id.sudo().write(vals)
        return {"ok": True}

    @http.route("/api/sunpower/my/password", type="json", auth="user", csrf=False)
    def password(self, old="", new="", **kw):
        if len(new or "") < MIN_PASSWORD:
            return {"ok": False, "field": "new", "error": _("Use at least %s characters.", MIN_PASSWORD)}
        try:
            request.env.user.change_password(old, new)
        except AccessDenied:
            return {"ok": False, "field": "old", "error": _("Your current password is not correct.")}
        except UserError as e:
            return {"ok": False, "field": "new", "error": e.args[0]}
        request.env.cr.commit()
        # keep this browser signed in after the password change
        request.session.session_token = request.env.user._compute_session_token(request.session.sid)
        return {"ok": True}


    # ----------------------------------------------------------------- payments
    @http.route("/api/sunpower/my/order/pay", type="json", auth="user", csrf=False)
    def order_pay(self, order_id=None, kind="advance", **kw):
        """Link to the secure payment page for the advance (or the balance) of
        one of the customer's own confirmed orders."""
        partner = self._customer()
        order = request.env["sale.order"].sudo().search([
            ("id", "=", int(order_id or 0)), ("partner_id", "child_of", partner.id),
            ("state", "=", "sale")], limit=1)
        if not order:
            return {"ok": False, "error": _("Order not found.")}
        paid = order._solar_paid_amount()
        if kind == "balance":
            amount = order.amount_total - paid
        else:
            amount = order._solar_advance_needed() - paid
        amount = order.currency_id.round(max(amount, 0))
        if amount <= 0:
            return {"ok": False, "error": _("Nothing to pay right now. Thank you!")}
        providers = request.env["payment.provider"].sudo()._get_compatible_providers(
            order.company_id.id, order.partner_invoice_id.id, amount,
            currency_id=order.currency_id.id, sale_order_id=order.id)
        if not providers:
            return {"ok": False, "error": _("Online payment isn't switched on yet. "
                                            "Please call us on +91 79 4000 5000 to pay.")}
        token = payment_utils.generate_access_token(
            order.partner_invoice_id.id, amount, order.currency_id.id)
        url = "%s/payment/pay?%s" % (_engine_url(), urlencode({
            "sale_order_id": order.id, "amount": amount, "access_token": token,
            "sunpower": 1}))
        return {"ok": True, "url": url, "amount": amount}

    @http.route("/api/sunpower/payment/return", type="http", auth="public")
    def payment_return(self, order=None, **kw):
        """Where the payment page sends the customer when it is finished."""
        order_rec = request.env["sale.order"].sudo().browse(int(order or 0)).exists()
        target = "%s/account?%s" % (_frontend_url(), urlencode({"paid": order_rec.name or ""}))
        return request.redirect(target, local=False)


class SunpowerPaymentPortal(SalePaymentPortal):
    """Payments started from the website return to My account instead of the
    engine's order page."""

    def _get_extra_payment_form_values(self, sale_order_id=None, sunpower=None, **kwargs):
        values = super()._get_extra_payment_form_values(sale_order_id=sale_order_id, **kwargs)
        if sunpower and sale_order_id:
            values["landing_route"] = "/api/sunpower/payment/return?order=%s" % int(sale_order_id)
        return values
