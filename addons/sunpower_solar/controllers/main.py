from odoo import _, http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal


def _float(v):
    try:
        return float(v or 0)
    except ValueError:
        return 0.0


class SolarWebsite(http.Controller):

    @http.route("/solar-quote", type="http", auth="public", website=True, sitemap=True)
    def solar_quote_form(self, **kw):
        return request.render("sunpower_solar.solar_quote_page", {})

    @http.route("/solar-quote/submit", type="http", auth="public", website=True,
                methods=["POST"], csrf=True)
    def solar_quote_submit(self, **post):
        name = (post.get("name") or "").strip()
        phone = (post.get("phone") or "").strip()
        if not name or not phone:
            return request.render("sunpower_solar.solar_quote_page",
                                  {"error": _("Name and phone are required."),
                                   "values": post})
        kw = _float(post.get("system_kw"))
        lead = request.env["crm.lead"].sudo().solar_create_enquiry({
            "name": _("%(kw)s kW %(t)s – %(n)s", kw=kw or "?",
                      t="Off-Grid" if post.get("system_type") == "off_grid" else "On-Grid",
                      n=name),
            "contact_name": name,
            "phone": phone,
            "email_from": post.get("email"),
            "street": post.get("street"),
            "city": post.get("city"),
            "requested_kw": kw,
            "system_type": post.get("system_type") or "on_grid",
            "subsidy_requested": bool(post.get("subsidy")),
            "monthly_bill": _float(post.get("monthly_bill")),
            "roof_area_sqft": _float(post.get("roof_area")),
            "description": post.get("notes"),
        }, channel="web")
        return request.render("sunpower_solar.solar_quote_thanks", {"lead": lead})


class SolarPortal(CustomerPortal):

    def _ticket_check(self, ticket_id, access_token):
        return self._document_check_access("solar.service.ticket", int(ticket_id),
                                           access_token)

    @http.route("/my/solar-ticket/<int:ticket_id>", type="http", auth="public",
                website=True)
    def solar_ticket_page(self, ticket_id, access_token=None, **kw):
        try:
            ticket = self._ticket_check(ticket_id, access_token)
        except (AccessError, MissingError):
            return request.redirect("/my")
        return request.render("sunpower_solar.portal_solar_ticket",
                              {"ticket": ticket, "access_token": access_token})

    @http.route("/my/solar-ticket/<int:ticket_id>/confirm", type="http", auth="public",
                website=True, methods=["POST"])
    def solar_ticket_confirm(self, ticket_id, access_token=None, works="yes", **kw):
        try:
            ticket = self._ticket_check(ticket_id, access_token)
        except (AccessError, MissingError):
            return request.redirect("/my")
        ticket = ticket.sudo()
        if works == "yes" and ticket.stage == "awaiting":
            ticket.action_customer_confirm()
        elif works == "no" and ticket.stage == "awaiting":
            ticket.action_reopen()
            ticket.message_post(body=_("Customer reports the problem is NOT fixed: %s",
                                       kw.get("comment") or ""))
        return request.redirect("/my/solar-ticket/%s?access_token=%s"
                                % (ticket.id, access_token or ""))
