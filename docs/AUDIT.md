# SunPower: code audit (22 Nov 2026)

Scope, honestly stated:
- **Read in full:** every back-end router (`auth`, `account`, `public`, `printing`, `staff_sales`, `staff_ops`, `staff_admin`), `security.py`, `access.py`, the money, dispatch, job and ticket parts of `rules.py`, and on the website `api.js`, `auth.jsx`, the role guard, the staff layout and the sign-in pages.
- **Only skimmed (not line-by-line):** `staff/Sales.jsx`, `staff/Ops.jsx` (checked the buttons against the new rules), `staff/Admin.jsx`, `staff/Overview.jsx`, `pages/QuoteReview.jsx`, the payment parts of `pages/Account.jsx`, `db.py`, `seed.py`.
- **Not done:** a full mobile and accessibility pass, and real Google sign-in (needs the origin set in Google Console).

Every item below was found by reading the code. **Confirmed** = reproduced or proven from the code (most have a test). **Assumption** = depends on how the site is deployed or used.

Severity: **P0** money or security broken in normal use · **P1** serious bug or exploitable · **P2** wrong or contradictory behaviour · **P3** confusing or weak · **P4** polish.

Line numbers refer to the code *before* the fixes; function names are given so they can still be found.

---

## Fixed in this pass (each has a test in `backend/tests/test_api.py` unless noted)

| # | Sev | Where | Problem (evidence) | Impact | Fix |
|---|---|---|---|---|---|
| 1 | **P0** | `catalog.py` `DEFAULT_SETTINGS["test_payments"] = "1"`; `routers/account.py` `test_confirm` | Fake-card payments were **on by default**. Any customer could mark their own order "paid" with card `4111…` on a real install. | Free dispatch of a ₹2–3 lakh kit; books wrong. | Off by default; only the demo data switches it on (`seed.load_demo`). |
| 2 | **P1** | `rules.complete_online_payment` | Read "pending", deleted the row, then recorded it. Two confirmations at once (double click, two tabs, retry) **both recorded the money**. | Paid amount doubled; dispatch unlocked early. | Atomic `DELETE … WHERE state='pending'`; the loser gets "already completed". |
| 3 | **P1** | `rules.record_payment`, `staff_sales.order_action('payment')` | No upper limit, and no protection against a double click. Staff could record more than the order total, or the same cash twice. | Over-collection, invoices beyond the order value, wrong profit. | Refuses more than the balance owed; refuses an identical payment by the same person within 2 minutes. |
| 4 | **P1** | `staff_ops.job_photo` + `attachment` | The file type was taken from the browser's label: an **SVG/HTML posing as a photo** was stored and served back as `image/svg+xml` on the site's own domain (stored XSS for any staff member who opens it). | Script runs with a director's session. | Real type read from the file's first bytes (JPEG/PNG/WebP only); served with `nosniff` and a sandbox CSP. |
| 5 | **P1** | `staff_sales.add_note` | Checked only the *area*, not ownership. A technician could add notes to **any** job, survey or ticket by id, including ones that don't exist. | IDOR: tampering with other crews' records. | Record must exist; technicians only on their own surveys, jobs and repairs. |
| 6 | **P1** | `rules.validate_delivery`, `rules.job_finish`, `rules.confirm_order` | Check-then-act: two clicks at once **dispatched twice** (stock deducted twice), **finished a job twice** (double timesheets and pay), or **confirmed twice** (two deliveries and two jobs). | Wrong stock, double technician pay, duplicate work. | `rules.claim()`: an atomic state change; only one request wins. |
| 7 | **P1** | `rules.allocate_payments`, `rules.final_invoice` | Repair (service) invoices carry the order id, so order money was spread over them and the final kit invoice was reduced by repair charges. Service invoices could never be paid at all. | Kit under-invoiced; repair invoices stuck "unpaid" forever. | Service invoices are kept out of order money. New `POST /api/staff/invoices/{id}/payment` and a "Record payment received" button on the request page. |
| 8 | **P1** | `routers/printing.py` `_order_access` | Any staff role (e.g. a technician) could open **any quotation with prices** by id; a customer could open their *draft* quotes. Token compared with `==`. | Price and margin leak across roles. | Staff need read access to orders (or jobs for certificates); customers only non-draft; constant-time token check. |
| 9 | **P1** | `mailer.branded` | Paragraphs went into email HTML unescaped; customer names come from the public form. | HTML or phishing links injected into SunPower emails. | All email text is escaped. |
| 10 | **P2** | `staff_ops.ticket_action` | Any stage could jump to any other: "diagnose" re-opened closed or cancelled requests; a technician could cancel requests. | Contradictory statuses; customer sees a closed repair reopen. | Allowed moves only (new→diagnosed→repair; reopen only when finished); only the service desk cancels. |
| 11 | **P2** | `create_ticket`, `update_ticket`, `update_survey`, `schedule_survey`, `update_lead` | Assignee ids were never checked: a ticket could be "assigned" to a customer or a deactivated user; a lead's salesperson to anyone. | Work assigned to nobody who can see it. | Must be an active user with the right role. |
| 12 | **P2** | `update_ticket`, `order_lines`, `update_survey`, `update_lead`, `update_subsidy` | No numeric validation: negative labour hours (negative charge), zero-quantity lines (₹0 quote that can be confirmed and dispatched with no advance), text in amount fields. | Wrong bills; free kits. | Ranges enforced; quotes need every quantity above 0 and a total above 0 before send or confirm. |
| 13 | **P2** | `staff_sales.survey_action('reset'/'reject')` | An approved survey that a quotation depends on could be reset or rejected; the order could then no longer be confirmed. | Stuck orders. | Refused while a non-cancelled quotation uses the survey. |
| 14 | **P2** | `update_lead` | Stage could be set to "won" by hand with no order. | Pipeline and reports show sales that don't exist. | "Won" only comes from a confirmed order. |
| 15 | **P2** | `rules.cancel_order` | Cancelling left the subsidy file open forever, the enquiry "won", delivery lines orphaned, and said nothing about money already received. It also cancelled orders whose crew was already on site. | Ghost subsidy work; refunds forgotten. | Subsidy file closed, enquiry lost, orphans removed, a note with the amount to refund; refused once the crew has started. |
| 16 | **P2** | `rules.confirm_order`, quote PDF, My Account quote | A subsidy file was created for **Off-Grid** orders (the scheme is on-grid only); the amount ignored the customer's state (special-category states get 10% more). | Wrong subsidy promised. | On-grid only; amount uses the enquiry's or customer's state. |
| 17 | **P2** | `update_subsidy`, `subsidy_action` | Closed (disbursed or rejected) files could still be edited, and "reject" worked on a disbursed file. | Audit trail broken. | Closed files are locked; reject only on open files. |
| 18 | **P2** | `routers/auth.login` | The rate limit was per email+IP only (rotate IPs = unlimited guesses on one account). An unknown email answered faster than a wrong password (shows which emails exist). Google-only accounts got a misleading "wrong password". | Brute force; account discovery. | Extra per-email limit; same work for unknown emails; a clear message for Google accounts. |
| 19 | **P2** | `routers/public.enquiry` | Unlimited anonymous enquiries. | The sales pipeline can be flooded. | 20 per hour per connection (the phone duplicate guard already existed). |
| 20 | **P2** | `frontend/src/api.js`, `auth.jsx` | An expired or ended session left the app thinking you were signed in: every screen failed with "Please sign in." and no way forward. | Users stuck on broken screens. | Any 401 re-checks the session, so the page guards send you to sign in. |
| 21 | **P3** | `frontend/src/App.jsx` | A crash in one page blanked the whole site (seen during testing). | White screen. | An error screen with "Try again" and "Home". |
| 22 | **P3** | `security.set_session_cookie` | No `Secure` flag on the sign-in cookie. | Cookie can travel over plain HTTP. | `SUNPOWER_SECURE_COOKIES=1` (set it on the live HTTPS site). |
| 23 | **P2** | All "per visitor" limits (`request.client.host`) | Behind the website's dev server (or any reverse proxy) every visitor looked like `127.0.0.1`, so one person could use up everyone's limit (e.g. 20 enquiries per hour for the whole site). | Real customers blocked by someone else's traffic. | `security.client_ip()` uses the forwarded address only when the request comes from this machine; the dev server now forwards it (`xfwd`). |
| 24 | **P2** | Google sign-in at the "SunPower team" door | A new Google address at the team door would have been given a customer account, then refused. | Stray accounts. | Refused before any account is made: team accounts come only from the Director. |

**Reproduction for the P0 and P1 items** (before the fix):
1. *Test payments:* fresh install; as a customer, accept a quote, choose "Test payment", card `4111 1111 1111 1111` → the order shows the advance paid and the warehouse can dispatch.
2. *Double completion:* open the payment confirmation in two tabs (or replay the `/api/my/payment/test/confirm` request twice quickly) → "Paid" shows twice the amount.
3. *Over-payment / double click:* on a confirmed order, Record payment with more than the balance, or double-click Save → both accepted.
4. *SVG photo:* on a job, upload a file `x.png` containing `<svg onload=alert(document.cookie)>`; open `/api/staff/attachments/<id>` → the script runs on the site's domain.
5. *Note IDOR:* as tech01, `POST /api/staff/notes {"model":"job","res_id":<another crew's job>,"body":"x"}` → saved.
6. *Double dispatch / finish / confirm:* fire two `validate` (or `finish`, or `confirm`) requests at the same moment → stock deducted twice, or two timesheets, or two deliveries.
7. *Service invoice mixed in:* resolve an out-of-warranty repair on an order that still owes money, then issue the final invoice → the final invoice is short by the repair amount, and the repair invoice never shows as paid.
8. *Quote leak:* as a technician, open `/print/quote/<any id>` → full prices.
9. *Email injection:* send an enquiry with the name `<a href="https://evil.example">Click</a>` → the confirmation and quote emails contain a live link.

### Added because you asked
- **Sign-in portal choice:** "Customer" or "SunPower team" on the sign-in page. The portal is only the door; access always comes from the account's role on the server, so choosing a portal can't grant anything. A mismatch (a customer at the team door, or staff at the customer door) is refused with a clear message and **no session**, for both email and Google sign-in. Staff links (`/login?next=/app…`) open on the team side.
- **Google sign-in with only your Client ID:** Google's own button (Google Identity Services). Google returns a signed ID token; the server checks it with Google (`/api/auth/google/token`): issued for our client ID, by Google, not expired, verified email. New Google emails get a **customer** account only, never staff. The Client ID is in `backend/.env` (git-ignored). A Client ID is public by design (the browser button needs it); no secret is involved.

---

## Not fixed yet: practical order

| Order | Sev | Where | Problem | Recommended fix |
|---|---|---|---|---|
| 1 | **P1** (assumption: real payments) | `rules.start_online_payment` / Razorpay | No Razorpay **webhook**: if the customer pays and closes the tab before the browser confirms, the money is taken but the payment stays "pending". | Add `/api/webhooks/razorpay` (signature-checked) that completes pending payments; a daily check of stale pending payments. |
| 2 | **P1** (assumption: live site) | `security.rate_limited` | Rate limits live in memory: they reset on restart and don't work across several server processes. | Store attempts in SQLite (or Redis) with timestamps. |
| 3 | **P2** | `auth.recover` | A 4-digit recovery code is guessable over time: 5 tries per 15 minutes per email is about 480 a day, so about 10 days for even odds, and less with restarts (see 2). | Lock the code after 10 failures and require email reset; or 6+ digits. |
| 4 | **P2** | Roles | No **Finance**, **Surveyor** or **Installer** roles: surveys and installs are both "technician", and payments are "sales". One role per account, no switching. | Add `finance` (payments, invoices, refunds) and, if needed, split `technician` into surveyor and installer in `access.py` plus a role switcher for people with two jobs. |
| 5 | **P2** | `rules.validate_delivery` (lots) | A panel *batch* (lot) delivered to a second customer moves the lot's `customer_id` to the new customer, so a staff ticket "by serial" for that batch goes to the latest customer. | Keep one serial row per (lot, delivery) or look up warranties instead of `serials.customer_id`. |
| 6 | **P2** | Refunds | Cancelling a paid order only adds a note; there is no refund record, so "collected" stays overstated until someone voids the payment. | A refund action (amount, method, reference) that creates a negative payment and updates invoices. |
| 7 | **P2** | My Account | No payment history or receipts behind "Paid"; subsidy says "Documents pending" without saying which documents or who uploads them. | A payment list with receipt PDFs; the subsidy document checklist shown to the customer with an upload. |
| 8 | **P3** | My Account order tracker | Only "Installation scheduled" has a date; checklist (5 tasks) and milestones (6 steps) look like the same measure. | Dates for every milestone; label "Installation checklist" separately. |
| 9 | **P3** | Sessions | Expired sessions are never deleted; no "sign out everywhere" button. | Delete expired rows at start-up; a button in My account. |
| 10 | **P3** | `customer/profile` | Customers can't set their state (it drives their subsidy). | Add a state field to the profile. |
| 11 | **P3** | `account.password` | Google-only users can't set a password from My account (it asks for the current one). | If no password exists, allow setting one without the old password (signed-in session plus recovery code). |
| 12 | **P3** | Staff serial lookup | Technicians (stock: read) can list every serial with customer names. | Limit technicians to serials on their own jobs. |
| 13 | **P4** | Back end | FastAPI `on_event` is deprecated (test warnings). | Switch to a lifespan handler. |
| 14 | **P4** | Legal | Invoices aren't GST tax invoices (no HSN per line, place of supply, sequential tax invoice series per financial year). | Add when invoicing goes live. |

### Assumptions to confirm
- **Google Console:** the button only signs people in from origins you've allowed. Add `http://localhost:5173` (and the live address later) under **Authorised JavaScript origins** for this Client ID, otherwise Google shows "origin not allowed".
- **Deployment:** for an HTTPS site, set `SUNPOWER_SECURE_COOKIES=1`, keep `test_payments` off, and put the `.env` and `backend/data/sunpower.db` outside the web root with backups.

### Design choice: two sign-in doors, not one per role
You asked for a portal per role. I built two: **Customer** and **SunPower team**. Inside the team door, the server already sends each person to their own screens and hides everything their role can't use. A role picker would let someone choose "Director" and then be refused, and it adds no security, because the role always comes from the account. If you still want per-role doors, `PORTALS` in `routers/auth.py` takes the five roles directly.

Note: your current database keeps test payments **on** (it was created before this change). Switch them off in Settings → Payments before going live.

## Tests
`backend/tests/test_api.py`: 37 pass. New: portal mismatch, cancelled quote keeps the enquiry, refused dispatch changes nothing, online money never refused, one login error for every failure, Google token rejected, technician note IDOR, payment cap and double click, online payment completes once, ticket transitions and assignee check, service invoices kept separate, email escaping, SVG upload refused.
