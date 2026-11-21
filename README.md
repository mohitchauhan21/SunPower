# SunPower: Solar Installation Management System

Everything a rooftop-solar company needs, from the first customer enquiry to the 20-year panel warranty: a public website, a customer account, and one workspace for every role in the company (Director, Sales, Warehouse, Technicians, Service desk).

```
 Visitors & customers ─┐
                       ├─► Website (React, :5173) ──/api, /print──► Back end (FastAPI + SQLite, :8001)
 Staff (every role) ───┘                          ──/ai──────────► AI service (FastAPI, :8000, optional)
```

No Odoo, no database server: the back end keeps everything in one SQLite file and fills it with realistic demo data on first start.

---

## How to run

You need **Python 3.11–3.13** and **Node 18+**. Run each part in its own terminal.

### macOS

```bash
git clone https://github.com/mohitchauhan21/SunPower.git && cd SunPower
./scripts/setup_mac.sh             # one time: Python, Node, back-end venv, npm install
./backend/run.sh                   # 1st terminal: API on http://localhost:8001
cd frontend && npm run dev         # 2nd terminal: website on http://localhost:5173
```

### Windows (PowerShell)

```powershell
git clone https://github.com/mohitchauhan21/SunPower.git; cd SunPower
powershell -ExecutionPolicy Bypass -File .\backend\run.ps1     # 1st terminal: creates .venv on first run, API on :8001
cd frontend; npm install; npm run dev                         # 2nd terminal: website on :5173
```

Open **http://localhost:5173** and sign in. Every demo account uses the password **`Sunpower@2026`** and the recovery code **`2580`**:

| Role | Login | Their Today page shows |
|---|---|---|
| Director | `director@sunpower.demo` | Sales to move forward, money to collect, work on site, warehouse, service. Trends are under Business → Insights. |
| Sales | `sales@sunpower.demo` | Enquiries to call, surveys to approve, quotes to send, money to collect |
| Warehouse | `warehouse@sunpower.demo` | Kits ready to dispatch, kits waiting for the advance, items to reorder |
| Service desk | `support@sunpower.demo` | New requests, repairs in progress, customers to confirm |
| Technician | `tech01@sunpower.demo` … `tech15@sunpower.demo` | My installations, my roof surveys, my repairs |
| Customer | `customer@sunpower.demo` | (My account) installation tracker, warranties, service, quotes & payments |

Everyone sees a short welcome tour the first time they sign in (visitors: the first time they open the site). It never comes back after that.

**Optional AI helpers** (bill reading, "fill from WhatsApp text", fault diagnosis, panel-photo check), in a 3rd terminal:

```bash
./ai_service/run.sh                                               # macOS
powershell -ExecutionPolicy Bypass -File .\ai_service\run.ps1      # Windows
```
The first start downloads about 2.2 GB of free models. Without the AI service everything still works; the AI buttons just ask you to fill the details in by hand. See [ai_service/README.md](ai_service/README.md).

**Turn on "Sign in with Google"** (optional)
1. In [Google Cloud Console](https://console.cloud.google.com/) → *APIs & Services* → *OAuth consent screen*: set it up (External, app name SunPower, your email).
2. *Credentials* → *Create credentials* → *OAuth client ID* → type **Web application**.
   - Authorised JavaScript origin: `http://localhost:5173`
   - Authorised redirect URI: `http://localhost:5173/api/auth/google/callback`
3. Copy the **Client ID** and **Client secret** into either:
   - **the website:** sign in as Director → Business → Settings → *Email, payments & sign-in* → Google, then Save; or
   - **a file:** create `backend/.env` (it is git-ignored) containing
     ```
     GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
     GOOGLE_CLIENT_SECRET=your-client-secret
     ```
     and restart the back end.
4. A "Continue with Google" button appears on the sign-in and sign-up pages. Never commit or share the secret.

**Useful extras**
- Fresh demo data: `./backend/run.sh --reset` (Windows: `run.ps1 -Reset`).
- Empty company (no demo data): set `SUNPOWER_DEMO=0` before the first start.
- API documentation: http://localhost:8001/api/docs
- Tests: `cd backend && .venv/bin/python -m pytest -q` (Windows: `.venv\Scripts\python -m pytest -q`).
- Production build of the website: `cd frontend && npm run build && npm run preview` (:4173, same proxy).

---

## Accounts and passwords

- **Passwords** need at least 8 characters with a capital letter, a small letter, a number and a symbol, typed twice. The forms show the rules ticking off as you type.
- **Recovery code:** everyone chooses a 4-digit code when they create their account (staff when they set their first password from the invite email). Obvious codes like 1234 or 0000 are refused.
- **Forgot password:** email + recovery code + new password (twice). Five wrong tries lock that email for 15 minutes. People without their code can still ask for an emailed reset link.
- Change your password or recovery code: customers in My account → Profile, staff in Workspace → My account.

## The workspace: five groups

| Group | Pages inside (tabs) |
|---|---|
| **Today** | Your to-do list for today: up to 4 numbers and up to 5 groups of things to act on |
| **Sales** | Enquiries · Surveys · Quotes & orders · Customers · Subsidy |
| **Operations** | Installations · Dispatch · Stock |
| **Service** | Requests · Warranties |
| **Business** (Director) | Insights (week / month / year trends) · Reports · Settings |

Each person only sees the groups and pages their role may open. Every staff member lands on **Today** after signing in.

## The business flow

1. **Enquiry.** It comes from the website, a call or WhatsApp (Sales can paste the message and let the AI fill the form). It is assigned to the least-busy salesperson with a "call within 2 hours" reminder.
2. **Phone screening.** Roof area, bill or units, and grid suitability. The system suggests a size (units ÷ 120, 1–5 kW).
3. **Roof survey.** Sales books a technician. The technician records the measurements and marks it visited; **only Sales or the Director can approve it**. No quote before approval.
4. **Quote.** The matching package (1–5 kW, On-Grid or Off-Grid) is picked automatically. GST is added: 12% on goods, 18% on installation. There is a PVGIS generation estimate, and discounts above 10% need the Director.
5. **Order.** The customer accepts online and pays the advance (test card or Razorpay), or Sales confirms and records the payment. Confirming creates the **delivery**, the **installation job** and the **subsidy file**, and invites the customer to their account.
6. **Dispatch.** It is blocked until the **30% advance** is paid (the Director can override). Every serial and batch is scanned, which **starts its warranty** (panels 20 years; inverter, battery and controller 2 years).
7. **Installation.** The technician starts on site, ticks the checklist, adds roof photos (AI-checked), confirms the kW and the generation reading, and gets the customer's on-screen signature. Hours are logged, and the certificate is emailed and printable.
8. **Service.** Requests are found by phone, name or serial. AI suggests the cause and safe steps. Warranty repairs are free; outside warranty an invoice is created automatically. The customer confirms the fix in their account.
9. **Money.** Profit per job = revenue − material − labour − warranty repairs. The Director sees the dashboard, technician pay, unpaid invoices, and a printable report that can also be emailed.

---

## What does what

| Path | What it is |
|---|---|
| **`backend/`** | **The back end** (FastAPI + SQLite). All business rules and permissions live here. |
| `├─ app/main.py` | App setup, CSRF guard (`X-SunPower` header), startup seeding and mail worker |
| `├─ app/rules.py` | **The business rules**: enquiries, surveys, quotes, payments, dispatch and warranties, jobs, tickets, profit |
| `├─ app/db.py` | SQLite schema and small query helpers (database at `backend/data/sunpower.db`) |
| `├─ app/security.py` | Passwords (scrypt), session cookies, one-time links, roles, rate limits |
| `├─ app/access.py` | **Who can open what**: one table of role → module → read / write / own records |
| `├─ app/catalog.py` | Components, the 10 packages and their parts lists, GST rates, default settings |
| `├─ app/seed.py` | Demo data: about 40 jobs over 3 months, 15 technicians, every role, tickets, subsidies |
| `├─ app/mailer.py` | Email queue and SMTP sender (off until the Director turns it on in Settings) |
| `├─ app/routers/public.py` | `/api/sunpower/estimate` and `/enquiry` (the public website) |
| `├─ app/routers/auth.py` | Sign in and out, sign-up, password reset, Google sign-in |
| `├─ app/routers/account.py` | `/api/my/*`: the customer's account, quotes, online payments, service requests |
| `├─ app/routers/staff_sales.py` | Enquiries, surveys, orders, customers, subsidy files |
| `├─ app/routers/staff_ops.py` | Stock and serials, dispatch, installation jobs and photos, service tickets, warranties |
| `├─ app/routers/staff_admin.py` | Dashboard, per-role summary, reports, settings, staff accounts, prices |
| `├─ app/routers/printing.py` | Printable quotation, installation certificate and Director report (save as PDF from the browser) |
| `├─ tests/test_api.py` | End-to-end API tests on a fresh demo database |
| `└─ run.sh`, `run.ps1` | Create the venv, install and start the back end |
| **`frontend/`** | **The website** (React 18 + Vite), minimalist Apple-style design |
| `├─ src/pages/` | Public pages (`Home`, `Estimate`, `Quote`), sign-in pages, customer `Account` and `QuoteReview` |
| `├─ src/staff/` | **The staff workspace `/app`**: `Layout` (role-based sidebar), `Overview` (Director dashboard or per-role to-do list), `Sales` (enquiries, surveys, orders, customers, subsidy), `Ops` (dispatch, stock, installations, service, warranties), `Admin` (reports, settings), `ui.jsx` (shared table, form and notes components) |
| `├─ src/components/ui/` | Arc UI-style components: `Tabs`, `ElasticSlider`, `Switch`, `Toast`, `Reveal` |
| `├─ src/components/reactbits/` | ReactBits components (MaskedHeading, ScrollStack, AccordionGallery, BubbleMenu…) |
| `├─ src/api.js`, `src/auth.jsx` | API client (back end + AI service) and who-is-signed-in |
| `└─ vite.config.js` | Proxy: `/api`, `/print` → back end :8001; `/ai` → AI service :8000 |
| **`ai_service/`** | Optional AI helpers (FastAPI): `/bill/parse`, `/lead/parse`, `/fault/diagnose`, `/photo/check`. Remote Hugging Face first, then free local CPU models, then regex or the knowledge base |
| **`scripts/setup_mac.sh`** | One-time macOS setup |
| `HANDOFF.md` | Current state, known issues and next steps |

The previous Odoo 18 version of this project is kept on the **`legacy-odoo`** branch.

## Tech stack

FastAPI · SQLite · React 18 + Vite + GSAP · Transformers / TensorFlow / RapidOCR (AI service) · PVGIS (EU JRC) for generation estimates.
