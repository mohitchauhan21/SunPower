"""Passwords, sessions, one-time links, roles and rate limits.

- Passwords: scrypt (standard library), per-user salt.
- Sessions: random token in an httpOnly, SameSite=Lax cookie; only its hash
  is stored, and it expires after 14 days.
- One-time links (reset / invite / claim): random token, stored hashed,
  single use, 24 h.
- Every state-changing API call must carry the `X-SunPower: 1` header, which a
  cross-site form cannot send (CSRF protection on top of SameSite).

WHO USES IT
  routers/auth.py (sign in, sign up, reset), routers/account.py (change password)
  and every router through the dependencies at the bottom (current_user,
  staff_only, director_only, require(...)).
"""
import base64                                    # turn raw bytes into printable text and back
import hashlib                                   # scrypt (password hashing) and sha256
import hmac                                      # compare_digest: a timing-safe equality check
import secrets                                   # cryptographically secure random tokens
import time                                      # time.time() for the rate limiter
from collections import defaultdict, deque       # dict with a default value; fast double-ended list
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request   # FastAPI building blocks (see bottom)

from .db import get_db                           # "." = from this same package (app/)

COOKIE = "sp_session"        # name of the sign-in cookie in the browser
SESSION_DAYS = 14            # how long a sign-in lasts
TOKEN_HOURS = 24             # how long an emailed link works
MIN_PASSWORD = 8             # minimum password length
# Recovery codes that are refused because they are too easy to guess. {...} = a set.
WEAK_CODES = {"0000", "1111", "2222", "3333", "4444", "5555", "6666", "7777", "8888", "9999",
              "1234", "2345", "3456", "4567", "5678", "6789", "4321", "9876", "0123", "1212", "1122"}


def password_problem(password):
    """None if the password is strong enough, else what to fix (shown to the user).
    Same rules as frontend/src/password.js."""
    p = password if isinstance(password, str) else ""   # treat None (or a non-text value) as empty
    if len(p) < MIN_PASSWORD:
        return "Use at least %s characters." % MIN_PASSWORD   # "%s" % x inserts x into the text
    if len(p) > 128:
        return "Use at most 128 characters."
    # any(...) is True if at least one character passes the test.
    if not any(c.isupper() for c in p):
        return "Add a capital letter (A–Z)."
    if not any(c.islower() for c in p):
        return "Add a small letter (a–z)."
    if not any(c.isdigit() for c in p):
        return "Add a number (0–9)."
    if not any(not c.isalnum() for c in p):              # isalnum = letter or digit; "not" = a symbol
        return "Add a symbol, like ! @ # or $."
    return None                                          # all rules passed


def code_problem(code):
    """Recovery code: exactly 4 digits, not an obvious one like 1234 or 0000."""
    c = str(code or "")
    if len(c) != 4 or not c.isdigit():
        return "Choose a 4-digit recovery code."
    if c in WEAK_CODES:
        return "That code is too easy to guess. Pick a less obvious one."
    return None

# Every role a user can have, and the subset that counts as staff. (...) = a tuple (fixed list).
ROLES = ("director", "sales", "warehouse", "technician", "support", "customer")
STAFF = ("director", "sales", "warehouse", "technician", "support")
ROLE_HOME = {  # every staff member starts on Today (their own to-do list)
    "director": "/app", "sales": "/app", "warehouse": "/app", "technician": "/app", "support": "/app",
    "customer": "/account",
}


def _ts(dt):
    """datetime -> "YYYY-MM-DD HH:MM:SS" text (the format stored in the database).
    A leading underscore means "for use inside this file only"."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def utcnow():
    """The current UTC time, without fractions of a second."""
    return datetime.now(timezone.utc).replace(microsecond=0)


# ------------------------------------------------------------------ passwords
def hash_password(password):
    """Turn a password (or recovery code) into a one-way hash to store.

    The real password is never stored. A random "salt" makes two users with the
    same password get different hashes. scrypt is deliberately slow and
    memory-hungry (n, r, p settings) so guessing many passwords is expensive.
    Stored as "scrypt$<salt>$<hash>" in base64 text.
    """
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)   # .encode(): text -> bytes
    return "scrypt$%s$%s" % (base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def check_password(password, stored):
    """True if `password` matches a hash made by hash_password()."""
    try:
        # Split the stored text back into its 3 parts; _algo is not needed (only "scrypt").
        _algo, salt_b64, hash_b64 = (stored or "").split("$")
        # Hash the typed password with the same salt and settings...
        digest = hashlib.scrypt((password or "").encode(), salt=base64.b64decode(salt_b64),
                                n=2 ** 14, r=8, p=1, dklen=32)
        # ...and compare. compare_digest takes the same time whether the first or the
        # last byte differs, so an attacker can't learn anything from response times.
        return hmac.compare_digest(digest, base64.b64decode(hash_b64))
    except Exception:          # malformed or missing hash: just "no match"
        return False


def _sha(token):
    """SHA-256 of a token. Session and link tokens are stored only as this hash, so a
    leaked database can't be used to sign in."""
    return hashlib.sha256(token.encode()).hexdigest()


# ------------------------------------------------------------------- sessions
def create_session(db, user_id):
    """Sign a user in: make a random token, store its hash, return the token (for the cookie)."""
    token = secrets.token_urlsafe(32)          # ~43 random URL-safe characters
    db.insert("sessions", {"token_hash": _sha(token), "user_id": user_id,
                           "created_at": _ts(utcnow()),
                           "expires_at": _ts(utcnow() + timedelta(days=SESSION_DAYS))})   # timedelta = a duration
    db.exec("UPDATE users SET last_login = ? WHERE id = ?", _ts(utcnow()), user_id)
    return token


def _secure_cookies():
    """Send cookies only over HTTPS when the site runs on HTTPS (set SUNPOWER_SECURE_COOKIES=1)."""
    import os
    return os.environ.get("SUNPOWER_SECURE_COOKIES", "0") == "1"


def set_session_cookie(response, token):
    """Put the session token in the browser as a cookie.
    httponly=True: JavaScript on the page can't read it (protects against XSS).
    samesite="lax": other websites can't send it along with their own forms.
    secure (when configured): the browser only sends it over HTTPS."""
    response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True,
                        samesite="lax", path="/", secure=_secure_cookies())


# Checked against when the email is unknown, so a wrong email takes as long as a wrong password
# (otherwise response times would reveal which emails have accounts).
_DUMMY_HASH = None


def check_password_or_dummy(password, stored):
    global _DUMMY_HASH
    if stored:
        return check_password(password, stored)
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password(secrets.token_urlsafe(12))
    check_password(password, _DUMMY_HASH)
    return False


def end_session(db, request, response):
    """Sign out this browser: delete its session row and its cookie."""
    token = request.cookies.get(COOKIE)
    if token:
        db.exec("DELETE FROM sessions WHERE token_hash = ?", _sha(token))
    response.delete_cookie(COOKIE, path="/")


def end_all_sessions(db, user_id, keep_token=None):
    """Sign a user out everywhere (after a password change), optionally keeping the current browser."""
    if keep_token:
        db.exec("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?", user_id, _sha(keep_token))
    else:
        db.exec("DELETE FROM sessions WHERE user_id = ?", user_id)


def session_user(db, request):
    """Who is signed in on this request? Returns the users row (dict) or None.
    JOIN combines each session with its user; only unexpired sessions of active users count."""
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    row = db.one("SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
                 "WHERE s.token_hash = ? AND s.expires_at > ? AND u.active = 1",
                 _sha(token), _ts(utcnow()))
    return row


# ------------------------------------------------------------- one-time links
def make_token(db, user_id, kind):
    """Create a single-use link token (kind = reset / invite / claim / staff).
    Any older unused link for the same user stops working."""
    token = secrets.token_urlsafe(32)
    db.exec("UPDATE tokens SET used = 1 WHERE user_id = ? AND used = 0", user_id)
    db.insert("tokens", {"token_hash": _sha(token), "user_id": user_id, "kind": kind,
                         "expires_at": _ts(utcnow() + timedelta(hours=TOKEN_HOURS))})
    return token


def read_token(db, token):
    """The token row (plus the user's name) if the link is still valid, else None."""
    if not token or len(token) > 200:          # reject empty or absurdly long input early
        return None
    return db.one("SELECT t.*, u.name AS user_name FROM tokens t JOIN users u ON u.id = t.user_id "
                  "WHERE t.token_hash = ? AND t.used = 0 AND t.expires_at > ? AND u.active = 1",
                  _sha(token), _ts(utcnow()))


def use_token(db, token):
    """Mark a link as used so it can't be opened again."""
    db.exec("UPDATE tokens SET used = 1 WHERE token_hash = ?", _sha(token))


# --------------------------------------------------------------- rate limits
# For each key (e.g. "login:email:ip") a deque of the times it was tried.
# defaultdict(deque): looking up a new key creates an empty deque automatically.
# Kept in memory, so it resets when the server restarts.
_hits = defaultdict(deque)


def rate_limited(key, limit=3, window=3600):
    """True if `key` was already tried `limit` times in the last `window` seconds.
    Otherwise records this attempt and returns False."""
    now = time.time()                           # seconds since 1970
    log = _hits[key]
    while log and now - log[0] > window:        # forget attempts older than the window
        log.popleft()
    if len(log) >= limit:
        return True
    log.append(now)
    return False


def client_ip(request):
    """The visitor's address. Behind our own proxy (the website dev server or a reverse proxy on
    this machine) every request comes from 127.0.0.1, so then the forwarded address is used;
    from anywhere else the header is ignored (it could be faked)."""
    host = request.client.host if request.client else "?"
    fwd = request.headers.get("x-forwarded-for")
    if fwd and host in ("127.0.0.1", "::1", "localhost"):
        return fwd.split(",")[0].strip()[:64]
    return host


def reset_rate_limits():
    """Forget all attempts (used by the tests)."""
    _hits.clear()


# --------------------------------------------------------------- dependencies
# A FastAPI "dependency" is a function an endpoint asks for with Depends(...).
# FastAPI runs it before the endpoint and passes in its return value. If it raises
# HTTPException, the endpoint never runs and the browser gets that error.
# `request: Request` is a type hint telling FastAPI to pass the incoming request.

def current_user(request: Request, db=Depends(get_db)):
    """The signed-in user, or a 401 "Please sign in." error."""
    user = session_user(db, request)
    if not user:
        raise HTTPException(401, "Please sign in.")
    return user


def optional_user(request: Request, db=Depends(get_db)):
    """The signed-in user, or None for visitors (no error)."""
    return session_user(db, request)


def require(*roles):
    """Dependency: the signed-in user must have one of `roles`.

    This is a function that *builds* a dependency: require("director") returns
    a new function `dep` that checks the role. Used as  user=Depends(require("customer")).
    403 = signed in, but not allowed.
    """
    def dep(user=Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(403, "You don't have access to this.")
        return user
    return dep


staff_only = require(*STAFF)           # any staff role; *STAFF spreads the tuple into arguments
director_only = require("director")
