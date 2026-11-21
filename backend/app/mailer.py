"""Emails are queued in the database and sent by a background thread, so a
web request never waits for SMTP. Nothing is sent until the Director turns on
outgoing email (Settings > Email) with an SMTP password (e.g. a Gmail app
password)."""
import logging
import smtplib
import threading
from email.message import EmailMessage
from html import escape

from .db import now, session

_log = logging.getLogger("sunpower.mail")
_stop = threading.Event()


def queue(db, email_to, subject, html):
    if not email_to:
        return None
    return db.insert("mail_queue", {"email_to": email_to, "subject": subject, "html": html,
                                    "created_at": now()})


def branded(db, title, paragraphs, button=None, link=None, footer=None):
    """Simple, consistent email layout (matches the website)."""
    company = escape(db.setting("company_name", "SunPower"))
    body = "".join("<p>%s</p>" % p for p in paragraphs)
    btn = ""
    if button and link:
        btn = ('<p><a href="%s" style="display:inline-block;background:#1d1d1f;color:#fff;'
               'padding:12px 22px;border-radius:999px;text-decoration:none;font-weight:600">%s</a></p>'
               % (escape(link), escape(button)))
    foot = '<p style="color:#6e6e73;font-size:13px">%s</p>' % escape(footer) if footer else ""
    return ('<div style="font-family:-apple-system,Segoe UI,Inter,sans-serif;max-width:520px;margin:auto;'
            'color:#1d1d1f"><p style="font-size:13px;color:#e8740c;font-weight:600">%s</p>'
            '<p style="font-size:20px;font-weight:600">%s</p>%s%s%s</div>'
            % (company, escape(title), body, btn, foot))


def send_pending(limit=20):
    """Send queued emails if outgoing email is configured. Returns (sent, failed)."""
    with session() as db:
        if db.setting("smtp_enabled") != "1" or not db.setting("smtp_password"):
            return 0, 0
        cfg = {k: db.setting("smtp_" + k) for k in ("host", "port", "user", "password", "from")}
        rows = db.q("SELECT * FROM mail_queue WHERE state = 'queued' ORDER BY id LIMIT ?", limit)
    sent = failed = 0
    if not rows:
        return 0, 0
    try:
        smtp = smtplib.SMTP(cfg["host"], int(cfg["port"] or 587), timeout=20)
        smtp.starttls()
        smtp.login(cfg["user"], cfg["password"])
    except Exception as e:  # wrong password / no network: keep emails queued
        _log.warning("SMTP connection failed: %s", e)
        with session() as db:
            db.set_setting("smtp_last_error", str(e)[:300])
        return 0, 0
    with session() as db:
        db.set_setting("smtp_last_error", "")
        for row in rows:
            msg = EmailMessage()
            msg["Subject"] = row["subject"]
            msg["From"] = cfg["from"] or cfg["user"]
            msg["To"] = row["email_to"]
            msg.set_content("Please view this email in an HTML-capable mail app.")
            msg.add_alternative(row["html"], subtype="html")
            try:
                smtp.send_message(msg)
                db.exec("UPDATE mail_queue SET state = 'sent', sent_at = ?, error = NULL WHERE id = ?",
                        now(), row["id"])
                sent += 1
            except Exception as e:
                db.exec("UPDATE mail_queue SET state = 'failed', error = ? WHERE id = ?", str(e)[:300], row["id"])
                failed += 1
    try:
        smtp.quit()
    except Exception:
        pass
    return sent, failed


def _loop(interval):
    while not _stop.wait(interval):
        try:
            send_pending()
        except Exception:
            _log.exception("mail worker")


def start_worker(interval=20):
    t = threading.Thread(target=_loop, args=(interval,), daemon=True, name="mail-worker")
    t.start()
    return t


def stop_worker():
    _stop.set()
