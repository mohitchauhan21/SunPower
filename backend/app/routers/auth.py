"""Sign in / out, who am I, customer sign-up, password reset, Google sign-in.

- The reset request always gives the same answer (no account fishing) and is
  rate-limited per email.
- Signing up with an email that already belongs to an account or a known
  customer never signs anyone in: a single-use link is emailed instead.
- Staff accounts are only created by the Director; sign-up and Google create
  customers.
"""
import re
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Body, Depends, Request, Response
from fastapi.responses import RedirectResponse

from .. import rules
from ..access import modules_for
from ..db import get_db, now
from ..security import (MIN_PASSWORD, ROLE_HOME, STAFF, check_password, create_session, end_all_sessions,
                        end_session, hash_password, make_token, optional_user, rate_limited, read_token,
                        set_session_cookie, use_token)

router = APIRouter(prefix="/api/auth")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
GENERIC_RESET = "If an account exists for that email, we've sent a link to reset the password."
CHECK_EMAIL = "This email already has a SunPower account. We've emailed you a link to choose a password and sign in."
GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"


def me_payload(user):
    if not user:
        return {"authenticated": False}
    out = {"authenticated": True, "id": user["id"], "name": user["name"], "login": user["email"],
           "role": user["role"], "home": ROLE_HOME.get(user["role"], "/")}
    if user["role"] in STAFF:
        out["modules"] = modules_for(user)
    return out


@router.get("/me")
def me(user=Depends(optional_user)):
    return me_payload(user)


@router.post("/login")
def login(request: Request, response: Response, body: dict = Body(default={}), db=Depends(get_db)):
    email = (body.get("login") or "").strip().lower()[:200]
    password = body.get("password") or ""
    ip = request.client.host if request.client else "?"
    if rate_limited("login:%s:%s" % (email, ip), limit=10, window=300):
        return {"ok": False, "error": "Too many attempts. Wait a few minutes and try again."}
    user = db.one("SELECT * FROM users WHERE email = ? COLLATE NOCASE AND active = 1", email)
    if not user or not user["password_hash"] or not check_password(password, user["password_hash"]):
        return {"ok": False, "error": "That email and password don't match. Try again or reset your password."}
    set_session_cookie(response, create_session(db, user["id"]))
    return {"ok": True, "uid": user["id"], **me_payload(user)}


@router.post("/logout")
def logout(request: Request, response: Response, db=Depends(get_db)):
    end_session(db, request, response)
    return {"ok": True}


@router.post("/signup")
def signup(response: Response, body: dict = Body(default={}), db=Depends(get_db)):
    name = (body.get("name") or "").strip()[:120]
    email = (body.get("email") or "").strip().lower()[:200]
    phone = (body.get("phone") or "").strip()[:40] or None
    password = body.get("password") or ""
    if not name:
        return {"ok": False, "field": "name", "error": "Please enter your name."}
    if not EMAIL_RE.match(email):
        return {"ok": False, "field": "email", "error": "Please enter a valid email address."}
    if len(password) < MIN_PASSWORD:
        return {"ok": False, "field": "password", "error": "Use at least %s characters for your password." % MIN_PASSWORD}
    if rate_limited("signup:" + email):
        return {"ok": False, "error": "Too many attempts. Please try again in an hour."}
    user = db.one("SELECT * FROM users WHERE email = ? COLLATE NOCASE", email)
    if user:
        if user["active"]:
            rules.send_account_email(db, user["id"], "claim", make_token(db, user["id"], "claim"))
        return {"ok": True, "status": "check_email", "message": CHECK_EMAIL}
    known = db.one("SELECT * FROM customers WHERE email = ? COLLATE NOCASE", email)
    if known:  # enquired or bought before: only the inbox owner may claim it
        uid = db.insert("users", {"name": known["name"], "email": email, "phone": known["phone"],
                                  "role": "customer", "customer_id": known["id"], "created_at": now()})
        rules.send_account_email(db, uid, "claim", make_token(db, uid, "claim"))
        return {"ok": True, "status": "check_email", "message": CHECK_EMAIL}
    cid = db.insert("customers", {"name": name, "email": email, "phone": phone, "created_at": now()})
    uid = db.insert("users", {"name": name, "email": email, "phone": phone, "password_hash": hash_password(password),
                              "role": "customer", "customer_id": cid, "created_at": now()})
    set_session_cookie(response, create_session(db, uid))
    return {"ok": True, "status": "created", "home": "/account"}


@router.post("/reset")
def reset_request(body: dict = Body(default={}), db=Depends(get_db)):
    email = (body.get("email") or "").strip().lower()[:200]
    if not EMAIL_RE.match(email):
        return {"ok": False, "error": "Please enter your email address."}
    if not rate_limited("reset:" + email):
        user = db.one("SELECT * FROM users WHERE email = ? COLLATE NOCASE AND active = 1", email)
        if user:
            rules.send_account_email(db, user["id"], "reset", make_token(db, user["id"], "reset"))
    return {"ok": True, "message": GENERIC_RESET}


@router.post("/reset/check")
def reset_check(body: dict = Body(default={}), db=Depends(get_db)):
    tok = read_token(db, body.get("token"))
    if not tok:
        return {"ok": False, "error": "This reset link is invalid or has expired."}
    return {"ok": True, "name": tok["user_name"]}


@router.post("/reset/confirm")
def reset_confirm(body: dict = Body(default={}), db=Depends(get_db)):
    password = body.get("password") or ""
    if len(password) < MIN_PASSWORD:
        return {"ok": False, "error": "Use at least %s characters." % MIN_PASSWORD}
    tok = read_token(db, body.get("token"))
    if not tok:
        return {"ok": False, "error": "This reset link is invalid or has expired. Ask for a new one."}
    db.update("users", tok["user_id"], {"password_hash": hash_password(password)})
    use_token(db, body.get("token"))
    end_all_sessions(db, tok["user_id"])
    return {"ok": True}


# ----------------------------------------------------------------- Google
def _google_cfg(db):
    cid, secret = db.setting("google_client_id"), db.setting("google_client_secret")
    return (cid, secret) if cid and secret else (None, None)


def _redirect_uri(db):
    return rules.frontend(db) + "/api/auth/google/callback"


@router.get("/providers")
def providers(db=Depends(get_db)):
    cid, _secret = _google_cfg(db)
    return [{"id": "google", "name": "Google", "url": "/api/auth/google/start"}] if cid else []


@router.get("/google/start")
def google_start(db=Depends(get_db)):
    cid, _secret = _google_cfg(db)
    if not cid:
        return RedirectResponse(rules.frontend(db) + "/login?error=google_off")
    state = secrets.token_urlsafe(24)
    url = GOOGLE_AUTH + "?" + urlencode({"client_id": cid, "redirect_uri": _redirect_uri(db), "response_type": "code",
                                         "scope": "openid email profile", "state": state, "prompt": "select_account"})
    resp = RedirectResponse(url)
    resp.set_cookie("sp_oauth_state", state, max_age=600, httponly=True, samesite="lax", path="/")
    return resp


@router.get("/google/callback")
def google_callback(request: Request, code: str = "", state: str = "", db=Depends(get_db)):
    front = rules.frontend(db)
    cid, secret = _google_cfg(db)
    if not cid or not code or not state or state != request.cookies.get("sp_oauth_state"):
        return RedirectResponse(front + "/login?error=google")
    try:
        tok = httpx.post(GOOGLE_TOKEN, timeout=15, data={
            "code": code, "client_id": cid, "client_secret": secret, "redirect_uri": _redirect_uri(db),
            "grant_type": "authorization_code"}).json()
        info = httpx.get(GOOGLE_USERINFO, timeout=15,
                         headers={"Authorization": "Bearer %s" % tok["access_token"]}).json()
    except Exception:
        return RedirectResponse(front + "/login?error=google")
    email = (info.get("email") or "").lower()
    if not email or not info.get("email_verified"):
        return RedirectResponse(front + "/login?error=google")
    user = db.one("SELECT * FROM users WHERE email = ? COLLATE NOCASE", email)
    if user and not user["active"]:
        return RedirectResponse(front + "/login?error=inactive")
    if not user:  # Google sign-up creates customers only
        name = info.get("name") or email.split("@")[0]
        cid_ = db.val("SELECT id FROM customers WHERE email = ? COLLATE NOCASE", email) or db.insert(
            "customers", {"name": name, "email": email, "created_at": now()})
        uid = db.insert("users", {"name": name, "email": email, "role": "customer", "customer_id": cid_,
                                  "created_at": now()})
        user = db.get("users", uid)
    resp = RedirectResponse(front + ROLE_HOME.get(user["role"], "/"))
    set_session_cookie(resp, create_session(db, user["id"]))
    resp.delete_cookie("sp_oauth_state", path="/")
    return resp
