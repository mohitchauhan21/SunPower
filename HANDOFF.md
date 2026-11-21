# Handoff: SunPower

*Last updated: 21 Nov 2026*

## Where things stand

| Part | Status |
|---|---|
| Back end (`backend/`, FastAPI + SQLite) | **Working.** It replaces Odoo and covers the whole flow (enquiry → survey → quote → advance → dispatch and warranties → installation → service → profit), with roles and permissions, sign-in, password reset, Google sign-in (needs keys), online payments (test mode now, Razorpay once keys are set), email queue, and printable documents. 8 API tests pass. |
| Website (`frontend/`) | **Working.** The public site, customer account and quote/payment page, and the staff workspace `/app` for all five staff roles. Every list and detail screen was opened in a browser against the live back end. A full scenario was run: sales → technician survey → approval → quote → customer accepts and pays (declined test card, then success) → warehouse dispatch → technician installation with checklist, photo, signature and certificate. |
| AI service (`ai_service/`) | Unchanged and optional. **Not re-tested in this round**: the AI buttons (fill enquiry from text, AI diagnose, photo check, bill upload) were only checked to fall back cleanly when the service is off. |
| Odoo version | Removed from this branch; kept on the **`legacy-odoo`** branch. |

## Latest round (UI/UX and accounts)

- **Top bar:** "Sign in" and "Get started" are the same size and shape. Signed-in people see a name badge and a "Sign out" button of the same size.
- **Welcome tour:** written separately for visitors, customers and each staff role. Visitors see it once per browser (`localStorage`); signed-in people once per account (`users.onboarded`, `POST /api/auth/onboarded`).
- **Workspace:** at most 5 groups (Today, Sales, Operations, Service, Business), with pages as tabs. **Today** (`GET /api/staff/today`) shows only what needs acting on now. History moved to **Insights**.
- **Passwords:** strong-password rules in `backend/app/security.py` (`password_problem`) and `frontend/src/password.js`. **Keep them identical.** Every password is typed twice.
- **Recovery code:** 4 digits chosen at sign-up, stored hashed (`users.recovery_code_hash`), used by `POST /api/auth/recover`, rate-limited to 5 tries per email per 15 minutes.
- **Google sign-in:** keys from Settings, or `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` in `backend/.env` (loaded at start-up).
- **Database:** new columns are added automatically to existing databases (`MIGRATIONS` in `db.py`).
- **Fixes:** the home page no longer scrolls sideways on narrow screens (ReactBits image layers are now clipped). Motion is switched off for people who ask their device for reduced motion.

## How the pieces connect

- The browser only talks to the website's origin. Vite forwards `/api/*` and `/print/*` to the back end (:8001) and `/ai/*` to the AI service (:8000).
- **Sign-in:** an httpOnly session cookie (`sp_session`, 14 days). Every state-changing call must send `X-SunPower: 1`, which a cross-site form can't send.
- **Permissions:** `backend/app/access.py` is the single table of role × module (`rw` / `r` / `own`). The server enforces it, and the sidebar is built from the same table (`me.modules`).
- **Estimate rules:** they exist twice, in `backend/app/rules.py` (`estimate`) and `frontend/src/solar.js` (so the page updates instantly). **Change both together.**
- **Times:** event times (created, paid, dispatched, on site) are stored in UTC. Appointment times (`scheduled_at`, `survey_date`) are stored as local time.

## Known issues and risks

1. **No production deployment yet.** The proxy only exists in `vite`/`vite preview`. In production, put the built website and the back end behind one reverse proxy (nginx/Caddy) with the same `/api`, `/print` and `/ai` routes, run uvicorn without `--reload`, and back up `backend/data/sunpower.db`.
2. **SQLite** is fine for one company and a few dozen users. For many simultaneous users, move to PostgreSQL. The SQL in `db.py` and `rules.py` is plain SQL, so the move is contained.
3. **Payments:** test mode is on by default (`Settings → Email, payments & sign-in`). Switch it off before going live and enter Razorpay keys. Razorpay webhooks are not implemented; payment confirmation relies on the browser callback.
4. **Email** is queued but not sent until the Director turns on SMTP in Settings.
5. **Photos and signatures** are stored inside the database file. With many jobs, move them to disk or object storage.
6. **The AI service** wasn't re-tested against the new website (see above).
7. **Odoo-only features not carried over:** full double-entry accounting (journals, ledgers, GST returns), multi-warehouse stock and Odoo's report designer. Invoices here are simple records (number, amount, tax, paid).
8. An empty `addons/` folder may linger on the original Windows machine (it was locked by another program during removal). It isn't in git; delete it when convenient.

## Suggested next steps

0. **Security of the 4-digit code:** with only 10,000 possible codes, it relies on the rate limit. For production, also send a one-time code by SMS or email at reset time, or ask for a longer code.

1. Re-test the AI helpers end to end with the AI service running (bill upload, fill from text, AI diagnose, photo check).
2. Production setup: reverse proxy, HTTPS, nightly copy of `sunpower.db`, `SUNPOWER_DEMO=0` for a clean company.
3. Razorpay webhook endpoint for reliable payment confirmation.
4. A Playwright smoke test of the main screens per role.
5. Optional: GST invoice PDF (`/print/invoice/{id}`) using the same print layout.

## Repository history

- `main` on GitHub: the Odoo version as first pushed (Next.js prototype before that, tag `phase-0a-approved`).
- `native-backend`: the new FastAPI back end and staff workspace (this work).
- `legacy-odoo`: the last Odoo version, including the sign-in, roles and customer-account work built on Odoo.
