"""Sign in / out, who am I, customer sign-up, password reset, Google sign-in.

- The reset request always gives the same answer (no account fishing) and is
  rate-limited per email.
- Signing up with an email that already belongs to an account or a known
  customer never signs anyone in: a single-use link is emailed instead.
- Staff accounts are only created by the Director; sign-up and Google create
  customers.
"""
import os
import re
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Body, Depends, Request, Response
from fastapi.responses import RedirectResponse

from .. import rules
from ..access import modules_for
from ..db import get_db, now
from ..security import (ROLE_HOME, STAFF, check_password, check_password_or_dummy, client_ip, code_problem, create_session,
                        current_user,
                        end_all_sessions, end_session, hash_password, make_token, optional_user, password_problem,
                        rate_limited, read_token, set_session_cookie, use_token)

router = APIRouter(prefix="/api/auth")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
GENERIC_RESET = "If an account exists for that email, we've sent a link to reset the password."
CHECK_EMAIL = "This email already has a SunPower account. We've emailed you a link to choose a password and sign in."
GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"
PORTALS = {"customer": ("customer",), "team": STAFF}       # sign-in page: "I am a customer" / "SunPower team"
PORTAL_NAMES = {"customer": "customer", "team": "SunPower team"}


def portal_mismatch(user, portal):
    """None if the account belongs to the portal chosen on the sign-in page, else a clear message.
    The portal is only a choice of door: what a person may do always comes from their role."""
    if portal not in PORTALS or user["role"] in PORTALS[portal]:
        return None
    if user["role"] == "customer":
        return "This is a customer account. Choose \"Customer\" above to sign in."
    return "This is a SunPower team account. Choose \"SunPower team\" above to sign in."


def me_payload(user):
    if not user:
        return {"authenticated": False}
    out = {"authenticated": True, "id": user["id"], "name": user["name"], "login": user["email"],
           "role": user["role"], "home": ROLE_HOME.get(user["role"], "/"),
           "onboarded": bool(user.get("onboarded")), "has_recovery_code": bool(user.get("recovery_code_hash")),
           "has_password": bool(user.get("password_hash"))}
    if user["role"] in STAFF:
        out["modules"] = modules_for(user)
    return out


@router.get("/me")
def me(user=Depends(optional_user)):
    return me_payload(user)


@router.post("/login")
def login(request: Request, response: Response, body: dict = Body(default={}), db=Depends(get_db)):
    email = rules.text(body.get("login")).strip().lower()[:200]
    password = rules.text(body.get("password"))
    portal = body.get("portal")
    ip = client_ip(request)
    # per email+device, and per email from anywhere (stops guessing one account from many addresses)
    if rate_limited("login:%s:%s" % (email, ip), limit=10, window=300) or rate_limited("login-email:" + email, limit=30, window=900):
        return {"ok": False, "error": "Too many attempts. Wait a few minutes and try again."}
    user = db.one("SELECT * FROM users WHERE email = ? COLLATE NOCASE AND active = 1", email)
    if not check_password_or_dummy(password, user["password_hash"] if user else None):
        # one answer for every failure, so it never reveals which emails have accounts
        return {"ok": False, "error": "That email and password don't match. If you signed up with Google, use "
                                      "\"Continue with Google\". Otherwise try again or reset your password."}
    problem = portal_mismatch(user, portal)
    if problem:
        return {"ok": False, "field": "portal", "error": problem}
    set_session_cookie(response, create_session(db, user["id"]))
    return {"ok": True, "uid": user["id"], **me_payload(user)}


@router.post("/logout")
def logout(request: Request, response: Response, db=Depends(get_db)):
    end_session(db, request, response)
    return {"ok": True}


@router.post("/onboarded")
def onboarded(user=Depends(current_user), db=Depends(get_db)):
    """The welcome tour is shown once per account."""
    db.update("users", user["id"], {"onboarded": 1})
    return {"ok": True}


@router.post("/signup")
def signup(response: Response, body: dict = Body(default={}), db=Depends(get_db)):
    name = rules.text(body.get("name")).strip()[:120]
    email = rules.text(body.get("email")).strip().lower()[:200]
    phone = rules.text(body.get("phone")).strip()[:40] or None
    password = rules.text(body.get("password"))
    code = rules.text(body.get("recovery_code")).strip()
    if not name:
        return {"ok": False, "field": "name", "error": "Please enter your name."}
    if not EMAIL_RE.match(email):
        return {"ok": False, "field": "email", "error": "Please enter a valid email address."}
    problem = password_problem(password)
    if problem:
        return {"ok": False, "field": "password", "error": problem}
    if body.get("confirm") != password:
        return {"ok": False, "field": "confirm", "error": "The two passwords don't match."}
    problem = code_problem(code)
    if problem:
        return {"ok": False, "field": "recovery_code", "error": problem}
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
                              "recovery_code_hash": hash_password(code),
                              "role": "customer", "customer_id": cid, "created_at": now()})
    set_session_cookie(response, create_session(db, uid))
    return {"ok": True, "status": "created", "home": "/account"}


@router.post("/recover")
def recover(request: Request, body: dict = Body(default={}), db=Depends(get_db)):
    """Forgot password: email + the 4-digit recovery code chosen at sign-up + a new password.
    Rate-limited hard, because a 4-digit code alone could be guessed."""
    email = rules.text(body.get("email")).strip().lower()[:200]
    code = rules.text(body.get("code")).strip()
    password = rules.text(body.get("password"))
    ip = client_ip(request)
    if not EMAIL_RE.match(email):
        return {"ok": False, "field": "email", "error": "Please enter your email address."}
    if len(code) != 4 or not code.isdigit():
        return {"ok": False, "field": "code", "error": "Enter your 4-digit recovery code."}
    problem = password_problem(password)
    if problem:
        return {"ok": False, "field": "password", "error": problem}
    if body.get("confirm") != password:
        return {"ok": False, "field": "confirm", "error": "The two passwords don't match."}
    if rate_limited("recover:" + email, limit=5, window=900) or rate_limited("recover-ip:" + ip, limit=20, window=900):
        return {"ok": False, "error": "Too many attempts. For your safety, wait 15 minutes or reset by email instead."}
    user = db.one("SELECT * FROM users WHERE email = ? COLLATE NOCASE AND active = 1", email)
    if not user or not user["recovery_code_hash"] or not check_password(code, user["recovery_code_hash"]):
        return {"ok": False, "error": "That email and recovery code don't match."}
    db.update("users", user["id"], {"password_hash": hash_password(password)})
    end_all_sessions(db, user["id"])
    return {"ok": True}


@router.post("/recovery-code")
def set_recovery_code(body: dict = Body(default={}), user=Depends(current_user), db=Depends(get_db)):
    """Set or change the 4-digit recovery code (needs the current password if there is one)."""
    if user["password_hash"] and not check_password(rules.text(body.get("password")), user["password_hash"]):
        return {"ok": False, "field": "password", "error": "Your current password is not correct."}
    problem = code_problem(body.get("code"))
    if problem:
        return {"ok": False, "field": "code", "error": problem}
    db.update("users", user["id"], {"recovery_code_hash": hash_password(str(body["code"]))})
    return {"ok": True}


@router.post("/reset")
def reset_request(body: dict = Body(default={}), db=Depends(get_db)):
    email = rules.text(body.get("email")).strip().lower()[:200]
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
    user = db.get("users", tok["user_id"])
    return {"ok": True, "name": tok["user_name"], "needs_code": not user["recovery_code_hash"]}


@router.post("/reset/confirm")
def reset_confirm(body: dict = Body(default={}), db=Depends(get_db)):
    password = rules.text(body.get("password"))
    problem = password_problem(password)
    if problem:
        return {"ok": False, "field": "password", "error": problem}
    if body.get("confirm") != password:
        return {"ok": False, "field": "confirm", "error": "The two passwords don't match."}
    tok = read_token(db, body.get("token"))
    if not tok:
        return {"ok": False, "error": "This reset link is invalid or has expired. Ask for a new one."}
    user = db.get("users", tok["user_id"])
    vals = {"password_hash": hash_password(password)}
    if not user["recovery_code_hash"] or body.get("code"):
        problem = code_problem(body.get("code"))
        if problem:
            return {"ok": False, "field": "code", "error": problem}
        vals["recovery_code_hash"] = hash_password(str(body["code"]))
    db.update("users", tok["user_id"], vals)
    use_token(db, body.get("token"))
    end_all_sessions(db, tok["user_id"])
    return {"ok": True}


# ----------------------------------------------------------------- Google
def _google_client_id(db):
    """Settings (Director) first, else GOOGLE_CLIENT_ID in backend/.env."""
    return (db.setting("google_client_id") or os.environ.get("GOOGLE_CLIENT_ID", "")).strip() or None


def _google_cfg(db):
    """Client ID + secret, needed only for the redirect flow (the button flow needs just the ID)."""
    cid = _google_client_id(db)
    secret = db.setting("google_client_secret") or os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    return (cid, secret) if cid and secret else (None, None)


def _google_user(db, email, name):
    """The account for a Google-verified email; a new email gets a customer account (never staff)."""
    user = db.one("SELECT * FROM users WHERE email = ? COLLATE NOCASE", email)
    if user:
        return user
    name = (name or email.split("@")[0])[:120]
    cid_ = db.val("SELECT id FROM customers WHERE email = ? COLLATE NOCASE", email) or db.insert(
        "customers", {"name": name, "email": email, "created_at": now()})
    uid = db.insert("users", {"name": name, "email": email, "role": "customer", "customer_id": cid_, "created_at": now()})
    return db.get("users", uid)


def _redirect_uri(db):
    return rules.frontend(db) + "/api/auth/google/callback"


@router.get("/providers")
def providers(db=Depends(get_db)):
    """Google sign-in for the website button. The client ID is public by design (Google's
    button needs it in the browser); the secret, if any, never leaves the server."""
    cid = _google_client_id(db)
    return [{"id": "google", "name": "Google", "enabled": bool(cid), "client_id": cid,
             "url": "/api/auth/google/start" if _google_cfg(db)[0] else None}]


@router.post("/google/token")
def google_token(request: Request, response: Response, body: dict = Body(default={}), db=Depends(get_db)):
    """Sign in with the ID token from Google's button. Google signs the token; we ask Google to
    verify it and check it was issued for our client ID, recently, for a verified email."""
    cid = _google_client_id(db)
    credential = rules.text(body.get("credential"))
    ip = client_ip(request)
    if not cid:
        return {"ok": False, "error": "Google sign-in is not set up yet."}
    if not credential or len(credential) > 4096 or rate_limited("google:" + ip, limit=30, window=300):
        return {"ok": False, "error": "Google sign-in didn't complete. Please try again."}
    try:
        info = httpx.get(GOOGLE_TOKENINFO, params={"id_token": credential}, timeout=10).json()
    except Exception:
        return {"ok": False, "error": "We couldn't reach Google. Please try again or use your email."}
    import time as _time
    email = (info.get("email") or "").lower()
    valid = (info.get("aud") == cid and info.get("iss") in ("accounts.google.com", "https://accounts.google.com")
             and str(info.get("email_verified")).lower() == "true" and email
             and int(info.get("exp") or 0) > _time.time())
    if not valid:
        return {"ok": False, "error": "Google sign-in didn't complete. Please try again or use your email."}
    if body.get("portal") == "team" and not db.val("SELECT id FROM users WHERE email = ? COLLATE NOCASE", email):
        # nobody new joins the team through Google: team accounts are created by the Director
        return {"ok": False, "field": "portal", "error": "There's no SunPower team account for this Google address. "
                                                         "Customers choose \"Customer\" above."}
    user = _google_user(db, email, info.get("name"))
    if not user["active"]:
        return {"ok": False, "error": "This account is switched off. Please contact SunPower."}
    problem = portal_mismatch(user, body.get("portal"))
    if problem:
        return {"ok": False, "field": "portal", "error": problem}
    set_session_cookie(response, create_session(db, user["id"]))
    return {"ok": True, **me_payload(user)}


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
    user = _google_user(db, email, info.get("name"))
    if not user["active"]:
        return RedirectResponse(front + "/login?error=inactive")
    resp = RedirectResponse(front + ROLE_HOME.get(user["role"], "/"))
    set_session_cookie(resp, create_session(db, user["id"]))
    resp.delete_cookie("sp_oauth_state", path="/")
    return resp
