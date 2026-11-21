"""Passwords, sessions, one-time links, roles and rate limits.

- Passwords: scrypt (standard library), per-user salt.
- Sessions: random token in an httpOnly, SameSite=Lax cookie; only its hash
  is stored, and it expires after 14 days.
- One-time links (reset / invite / claim): random token, stored hashed,
  single use, 24 h.
- Every state-changing API call must carry the `X-SunPower: 1` header, which a
  cross-site form cannot send (CSRF protection on top of SameSite).
"""
import base64
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request

from .db import get_db

COOKIE = "sp_session"
SESSION_DAYS = 14
TOKEN_HOURS = 24
MIN_PASSWORD = 8
WEAK_CODES = {"0000", "1111", "2222", "3333", "4444", "5555", "6666", "7777", "8888", "9999",
              "1234", "2345", "3456", "4567", "5678", "6789", "4321", "9876", "0123", "1212", "1122"}


def password_problem(password):
    """None if the password is strong enough, else what to fix (shown to the user).
    Same rules as frontend/src/password.js."""
    p = password or ""
    if len(p) < MIN_PASSWORD:
        return "Use at least %s characters." % MIN_PASSWORD
    if len(p) > 128:
        return "Use at most 128 characters."
    if not any(c.isupper() for c in p):
        return "Add a capital letter (A–Z)."
    if not any(c.islower() for c in p):
        return "Add a small letter (a–z)."
    if not any(c.isdigit() for c in p):
        return "Add a number (0–9)."
    if not any(not c.isalnum() for c in p):
        return "Add a symbol, like ! @ # or $."
    return None


def code_problem(code):
    """Recovery code: exactly 4 digits, not an obvious one like 1234 or 0000."""
    c = str(code or "")
    if len(c) != 4 or not c.isdigit():
        return "Choose a 4-digit recovery code."
    if c in WEAK_CODES:
        return "That code is too easy to guess. Pick a less obvious one."
    return None

ROLES = ("director", "sales", "warehouse", "technician", "support", "customer")
STAFF = ("director", "sales", "warehouse", "technician", "support")
ROLE_HOME = {  # every staff member starts on Today (their own to-do list)
    "director": "/app", "sales": "/app", "warehouse": "/app", "technician": "/app", "support": "/app",
    "customer": "/account",
}


def _ts(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0)


# ------------------------------------------------------------------ passwords
def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return "scrypt$%s$%s" % (base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def check_password(password, stored):
    try:
        _algo, salt_b64, hash_b64 = (stored or "").split("$")
        digest = hashlib.scrypt((password or "").encode(), salt=base64.b64decode(salt_b64),
                                n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(digest, base64.b64decode(hash_b64))
    except Exception:
        return False


def _sha(token):
    return hashlib.sha256(token.encode()).hexdigest()


# ------------------------------------------------------------------- sessions
def create_session(db, user_id):
    token = secrets.token_urlsafe(32)
    db.insert("sessions", {"token_hash": _sha(token), "user_id": user_id,
                           "created_at": _ts(utcnow()),
                           "expires_at": _ts(utcnow() + timedelta(days=SESSION_DAYS))})
    db.exec("UPDATE users SET last_login = ? WHERE id = ?", _ts(utcnow()), user_id)
    return token


def set_session_cookie(response, token):
    response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True,
                        samesite="lax", path="/")


def end_session(db, request, response):
    token = request.cookies.get(COOKIE)
    if token:
        db.exec("DELETE FROM sessions WHERE token_hash = ?", _sha(token))
    response.delete_cookie(COOKIE, path="/")


def end_all_sessions(db, user_id, keep_token=None):
    if keep_token:
        db.exec("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?", user_id, _sha(keep_token))
    else:
        db.exec("DELETE FROM sessions WHERE user_id = ?", user_id)


def session_user(db, request):
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    row = db.one("SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
                 "WHERE s.token_hash = ? AND s.expires_at > ? AND u.active = 1",
                 _sha(token), _ts(utcnow()))
    return row


# ------------------------------------------------------------- one-time links
def make_token(db, user_id, kind):
    token = secrets.token_urlsafe(32)
    db.exec("UPDATE tokens SET used = 1 WHERE user_id = ? AND used = 0", user_id)
    db.insert("tokens", {"token_hash": _sha(token), "user_id": user_id, "kind": kind,
                         "expires_at": _ts(utcnow() + timedelta(hours=TOKEN_HOURS))})
    return token


def read_token(db, token):
    if not token or len(token) > 200:
        return None
    return db.one("SELECT t.*, u.name AS user_name FROM tokens t JOIN users u ON u.id = t.user_id "
                  "WHERE t.token_hash = ? AND t.used = 0 AND t.expires_at > ? AND u.active = 1",
                  _sha(token), _ts(utcnow()))


def use_token(db, token):
    db.exec("UPDATE tokens SET used = 1 WHERE token_hash = ?", _sha(token))


# --------------------------------------------------------------- rate limits
_hits = defaultdict(deque)


def rate_limited(key, limit=3, window=3600):
    now = time.time()
    log = _hits[key]
    while log and now - log[0] > window:
        log.popleft()
    if len(log) >= limit:
        return True
    log.append(now)
    return False


def reset_rate_limits():
    _hits.clear()


# --------------------------------------------------------------- dependencies
def current_user(request: Request, db=Depends(get_db)):
    user = session_user(db, request)
    if not user:
        raise HTTPException(401, "Please sign in.")
    return user


def optional_user(request: Request, db=Depends(get_db)):
    return session_user(db, request)


def require(*roles):
    """Dependency: the signed-in user must have one of `roles`."""
    def dep(user=Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(403, "You don't have access to this.")
        return user
    return dep


staff_only = require(*STAFF)
director_only = require("director")
