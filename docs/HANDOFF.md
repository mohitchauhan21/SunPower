# SunPower: handoff

Written 22 Nov 2026. Read this first, then `PLAN.md` (what's done and what's left) and `README.md` (roles, demo logins, set-up).

## 1. Where things stand

- **Branch:** `native-backend` on `github.com/mohitchauhan21/SunPower`. Last pushed commit: `398be0a` (survey, inventory, flow, invoices).
- **Not committed yet** (made after that push):
  - **Inventory in the sidebar:** it has its own entry, and "Stock" is renamed to "Inventory".
  - **Booking form:** a signed-in customer's name, mobile and email are locked; guests sign up with their details pre-filled and come back to the filled form.
- **Tests:** 61 back-end tests, all passing. There are no front-end tests.
- **`main`:** has none of this work; nothing has been merged and no pull request is open.

## 2. Run it

| What | Command | Address |
|---|---|---|
| Back end (FastAPI + SQLite) | `powershell -ExecutionPolicy Bypass -File backend/run.ps1` | http://localhost:8001 (API docs `/api/docs`) |
| Website (React + Vite) | `npm --prefix frontend run dev` | http://localhost:5173 |
| Tests | `cd backend; .venv\Scripts\python.exe -m pytest -q` | — |

- **The back end does not auto-reload.** Restart it after every back-end change, or the website talks to old code. If a survey page says "server is out of date", this is why.
- **Database:** a single SQLite file, `backend/data/sunpower.db`. It is git-ignored. Open it read-only (for example in DB Browser for SQLite).
- **Testing on a copy:** set `SUNPOWER_DB` to a copy of the database, start the back end on another port (for example 8003), and start Vite with `SUNPOWER_BACKEND=http://localhost:8003` on another port (for example 5178). Never experiment on the real file.
- **Environment variables:**

  | Variable | Default | What it does |
  |---|---|---|
  | `SUNPOWER_DB` | `backend/data/sunpower.db` | Database file to use |
  | `SUNPOWER_DEMO` | `1` | Fill an *empty* database with demo data and demo accounts |
  | `SUNPOWER_DOCS` | `1` | Serve the API docs; set `0` in production |
  | `SUNPOWER_BACKEND` | `http://localhost:8001` | Back end that Vite proxies `/api` and `/print` to |
- **Secrets:** the Google Client ID and the HF token live only in `backend/.env`, which git ignores. Never commit or paste them. Razorpay keys and the Gmail app password are entered by the owner in **Settings**, never in code or chat.
- **Don't touch:** the `odoo18` folder and its database.

## 3. Code map

| Area | File |
|---|---|
| Business rules (all of them) | `backend/app/rules.py` |
| Tables + start-up column upgrades (`MIGRATIONS`) | `backend/app/db.py` |
| Catalogue, packages, GST, default settings | `backend/app/catalog.py` |
| Who can open what (roles) | `backend/app/access.py` |
| State subsidy table, GST state codes | `backend/app/subsidy.py` |
| Start-up (migrations, new parts, one-time rate upgrade) | `backend/app/main.py` |
| API routes | `backend/app/routers/` — `public` (estimate, enquiry, Razorpay webhook), `auth`, `account` (customer portal), `staff_sales`, `staff_ops`, `staff_admin`, `printing` (quote, invoice, certificate pages) |
| Staff screens | `frontend/src/staff/` — `Sales.jsx` (enquiries, surveys, quotes), `Ops.jsx` (dispatch, inventory, jobs, service), `Admin.jsx` (settings), `Layout.jsx` (sidebar) |
| Public / customer screens | `frontend/src/pages/` |
| Test helper for a complete survey | `backend/tests/survey_helper.py` |

## 4. The flow as built

1. **Booking:** the customer books a survey on `/book-survey`.
   - **Guests** are sent to sign up with their details pre-filled, then return to the filled form to confirm.
   - **Signed-in customers** book with locked name, mobile and email; the address is editable for another property.
2. **Survey booked:** Sales confirms the call and assigns an area technician, with the date and a morning, afternoon or evening slot.
3. **Site survey:** the technician fills it in on `/app/surveys/:id`.
   - The form has 8 tabs: Roof, Shade, Electrical, Cabling & mounting, Battery (off-grid only), Site & safety, Photos, Issues & summary.
   - Required fields, 5 required photos and a result are needed before **Submit visit**.
   - **Save & next** saves first and warns about missing required fields.
4. **Quote:** **Build quote** creates the quote and sends it to the customer automatically.
   - The size must be 1–100 kW and fit the shadow-free area (about 100 sq ft per kW). Sizes without a package get one built on demand from the same parts.
   - Measured cable runs, earthing, conduit, elevated or metal-roof mounting and waterproofing add extra quote lines.
5. **Confirmation:** the customer accepts in the portal. While **Payment required** is off (the current default), acceptance confirms the order. When it's on, they pay the advance or the full amount first.
6. **Scheduling:** Sales schedules the installation from the order page; there is no automatic date. Today shows "Installations to schedule", and the customer gets an email.
7. **Dispatch:** the warehouse packs and dispatches from **Dispatch**.
   - Each order shows a stock tally.
   - The serial or batch number of every unit is recorded.
   - Short stock blocks dispatch.
8. **Installation:** the surveying technician (assigned automatically) starts on or after the scheduled day, once the kit has shipped. They complete the checklist, installed kW, photo and customer signature.
9. **Warranties and final invoice:** completing the installation starts every unit's warranty that day and issues the final invoice.

## 5. Settings and rules worth knowing

- **GST:**
  - **5%** on solar equipment, the rate since 22 Sep 2025.
  - **18%** on installation and service.
  - Existing products and unaccepted quotes were upgraded once at start-up (setting `upgrade_gst5_2025`). Confirmed orders keep 12%.
- **Warranties:** panels 15 years; inverter, battery and controller 2 years.
- **Payment and invoice settings:**

  | Setting | Value |
  |---|---|
  | `payment_required` | `0` (payment step skipped) |
  | `test_payments` | test cards on, for demos |
  | `advance_pct` | 30 |
  | `full_upfront_discount_pct` | 2 |
  | `discount_approval_pct` | 5; a bigger discount needs Sales or Director approval |
- **Invoices:** GST pages at `/print/invoice/:id`, with CGST + SGST inside Gujarat (the company GSTIN starts 24) and IGST elsewhere. Customers see them in My account and get them by email.
- **Warehouse workspace:** Dispatch and Inventory only.
  - Inventory has three tabs: items (unique codes; add, edit, correct stock with a reason, retire), demand from surveys, and serial numbers.
  - Prices, GST and warranty stay with the Director.
- **Subsidy:** PM Surya Ghar central rate per state category, capped at 3 kW, on-grid only. State top-ups are shown only when the customer switches them on.

## 6. Needs the owner (can't be done from code)

1. **Stock:** receive stock for the five site parts, which are at 0 on the real database: `STR-ELV`, `CND-25`, `ERT-CBL`, `WPF-KIT`, `CLMP-MTL`. The same goes for any new large-size inverter such as `INV-35KW`. Dispatch refuses until there is stock.
2. **Razorpay:**
   - Enter the key id and secret (test mode first) in **Settings → Online payments**.
   - Add the webhook URL shown there with the event `payment.captured`, and paste its secret.
   - Then switch **Payment required** on and **Test payments** off.
3. **SMTP:** set it up in Settings; quote, invoice and schedule emails wait in the queue until then.
4. **Website address:** set `frontend_url` in Settings to the real site address, so links in emails and on invoices work.

## 7. Known gaps and risks

- **Deployment blockers:**
  - Demo accounts with a public password (`SUNPOWER_DEMO` defaults on, and the sign-in page has one-click demo buttons; the owner wants them kept for now).
  - No production build or hosting set-up; the back end runs as a single development process.
  - API docs are on by default.
- **Webhook:** Razorpay can't reach `localhost`, so the webhook only works once the site is online.
- **Old dates:** jobs created before the "Sales schedules" change still have automatic dates, and one shows as overdue.
- **Bad test surveys:** SRV-00046 and SRV-00047 on the real database have impossible sizes or areas. Correct them, or mark them Not feasible.
- **Not checked:** phone-width layouts of the survey, inventory and dispatch screens. The ☀ symbol on printed pages isn't the real logo.
- **Still to build** (details in `PLAN.md`):
  - supplier purchase orders
  - installation readings and switch-on after full payment
  - repair visit fee and estimate approval
  - Admin vs Director split with Director charts
  - a project timeline
  - `docs/WORKFLOW.md`

## 8. Working agreements from the owner

- Keep `PLAN.md` updated after each task.
- Test on copies of the database.
- Don't commit or push unless asked.
- Never commit secrets.
- When asked for a review, don't change anything.
- Plain, consistent wording on every screen; customer details stay the same from enquiry to invoice.
