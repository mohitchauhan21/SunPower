"""Account endpoints for the React website: who am I, Google sign-in links,
password reset (request + confirm) and the landing page after Google sign-in.

Security notes:
- The reset request always gives the same answer, so it never reveals whether an
  email has an account, and it is rate-limited per email.
- Reset links are Odoo signup tokens (signed, single use, expire after 24 h).
- Staff accounts are never created here. Google sign-up creates customers only
  (auth_signup.invitation_scope = b2c, new users get the portal template).
"""
import logging
import time
from collections import defaultdict, deque

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.auth_oauth.controllers.main import OAuthLogin

_logger = logging.getLogger(__name__)

RESET_LIMIT = 3            # reset emails per address ...
RESET_WINDOW = 3600        # ... per hour
MIN_PASSWORD = 8
_reset_log = defaultdict(deque)
GENERIC_RESET_MSG = "If an account exists for that email, we've sent a link to reset the password."


def _frontend_url():
    return (request.env["ir.config_parameter"].sudo()
            .get_param("sunpower.frontend_url", "http://localhost:5173")).rstrip("/")


def _engine_url():
    return request.env["ir.config_parameter"].sudo().get_param("web.base.url", "").rstrip("/")


def _rate_limited(key):
    now = time.time()
    log = _reset_log[key]
    while log and now - log[0] > RESET_WINDOW:
        log.popleft()
    if len(log) >= RESET_LIMIT:
        return True
    log.append(now)
    return False


class SunpowerAuthApi(http.Controller):

    @http.route("/api/sunpower/me", type="json", auth="public", csrf=False)
    def me(self, **kw):
        user = request.env.user
        if not request.session.uid or user._is_public():
            return {"authenticated": False}
        role = user._sunpower_role()
        home = user._sunpower_home(engine_url=_engine_url())
        return {"authenticated": True, "name": user.name, "login": user.login,
                "role": role, "home": home}

    @http.route("/api/sunpower/auth/providers", type="json", auth="public", csrf=False)
    def providers(self, **kw):
        """Google (and any other enabled OAuth provider) with a ready sign-in link.
        Empty until a Client ID has been entered in Settings."""
        request.params["redirect"] = "/api/sunpower/auth/after-login"
        out = []
        for p in OAuthLogin().list_providers():
            # only Google; the built-in Odoo.com provider is never offered
            if "google" in (p.get("auth_endpoint") or "") and p.get("client_id") and p.get("auth_link"):
                out.append({"id": p["id"], "name": p["name"], "url": p["auth_link"]})
        return out

    @http.route("/api/sunpower/auth/after-login", type="http", auth="user")
    def after_login(self, **kw):
        home = request.env.user._sunpower_home(engine_url=_engine_url())
        target = _frontend_url() + home if home.startswith("/") else home
        return request.redirect(target, local=False)

    @http.route("/api/sunpower/auth/reset", type="json", auth="public", csrf=False)
    def reset_request(self, email="", **kw):
        email = (email or "").strip().lower()[:200]
        if not email or "@" not in email:
            return {"ok": False, "error": _("Please enter your email address.")}
        if _rate_limited(email):
            return {"ok": True, "message": GENERIC_RESET_MSG}
        Users = request.env["res.users"].sudo()
        user = Users.search(["|", ("login", "=ilike", email), ("email", "=ilike", email)], limit=1)
        if user and user.active and user.email:
            try:
                user._sunpower_send_account_email("reset")
            except Exception:  # never reveal internals to the caller
                _logger.exception("SunPower: password reset email failed for user %s", user.id)
        return {"ok": True, "message": GENERIC_RESET_MSG}

    @http.route("/api/sunpower/auth/reset/check", type="json", auth="public", csrf=False)
    def reset_check(self, token="", **kw):
        try:
            partner = request.env["res.partner"].sudo()._signup_retrieve_partner(token) if token else None
        except Exception:  # malformed or tampered token
            partner = None
        if not partner or not partner.user_ids:
            return {"ok": False, "error": _("This reset link is invalid or has expired.")}
        return {"ok": True, "name": partner.name}

    @http.route("/api/sunpower/auth/reset/confirm", type="json", auth="public", csrf=False)
    def reset_confirm(self, token="", password="", **kw):
        if len(password or "") < MIN_PASSWORD:
            return {"ok": False, "error": _("Use at least %s characters.", MIN_PASSWORD)}
        try:
            partner = request.env["res.partner"].sudo()._signup_retrieve_partner(token, check_validity=True)
            if not partner or not partner.user_ids:
                raise UserError("invalid")
            request.env["res.users"].sudo().signup({"password": password}, token)
        except Exception:
            return {"ok": False, "error": _("This reset link is invalid or has expired. Ask for a new one.")}
        return {"ok": True}
