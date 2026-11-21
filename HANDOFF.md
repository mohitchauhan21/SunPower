# Handoff: SunPower

*Last updated: 21 Nov 2026*

## Where things stand

| Part | Status |
|---|---|
| Odoo modules (`sunpower_solar`, `sunpower_website`, `sunpower_ai`) | **Working.** Phases 1–10 are done. Unit tests and `scripts/phase_checks.py` pass (see `docs/sunpower_report.html`). |
| AI service | **Working locally on CPU.** Remote Hugging Face models return 402 (no credits), so the local models are used. |
| React frontend | **New.** Redesigned in a minimalist light style and connected to Odoo. Enquiries, the estimate and the console were tested in a browser against a live Odoo. **Bill upload through `/ai` has not been tested end to end** (the AI service wasn't running at the time). |
| Odoo website (`/`, `/solar/estimate`, `/my/solar`, `/technician`) | Working. The customer portal and crew page still live only in Odoo; the React site links to them. |

## How the pieces connect

- The React site talks to **one origin**. Vite forwards `/api/*` and `/web/*` to Odoo (:8069) and `/ai/*` to the AI service (:8000), with the `/ai` prefix stripped.
- `POST /api/sunpower/enquiry` (JSON-RPC, public) calls `crm.lead.solar_create_enquiry`, the same function the Odoo web form uses. It returns `{ok, id, contact}` or `{ok: false, error}`.
- `POST /api/sunpower/estimate` (JSON-RPC, public) returns `solar_estimate(units, bill)` from `sunpower_website/controllers/main.py`. `frontend/src/solar.js` repeats the same formula so the page updates instantly. **If you change one, change the other.**
- The console signs in with `/web/session/authenticate` (database `sunpower`, set in `frontend/src/api.js`) and calls `solar.dashboard.get_data`.

## Known issues and risks

1. **Creating an enquiry takes about 8 seconds** inside Odoo, and the existing `/solar-quote` form is just as slow. This probably comes from the activity or notification sending in `solar_create_enquiry` (it may be trying to send email through an unconfigured mail server). It needs profiling.
2. **No production setup for the React site.** The proxy only exists in `vite`/`vite preview`. In production you need a reverse proxy (nginx/IIS) that routes `/api`, `/web` and `/ai` the same way. Otherwise you have to add CORS to Odoo and the AI service.
3. **Public enquiry endpoint has no rate limit or captcha.** It is protected against CSRF because it requires a JSON body, but bots could still fill the CRM with spam.
4. **Hard-coded paths** in `run_odoo.ps1` and `scripts/rebuild_db.py` point at the original developer's machine.
5. **Links in the React site are hard-coded** to `http://localhost:8069`: the My Solar link, the crew app link and the console's "Open in Odoo" link.
6. **AI quality.** The 0.5B model can make up street names for Hindi input. The photo classifier gives mixed results on real photos, so treat its flag as a hint only.
7. The quote's `est_payback_years` uses the total *including* GST, while the website estimate uses the price before GST.

## Suggested next steps

1. Profile and fix the slow `solar_create_enquiry` (issue 1).
2. Put a reverse proxy in front of the React build, and move the hard-coded `localhost:8069` links into an environment variable such as `VITE_ENGINE_URL`.
3. Add rate limiting or a honeypot field to `/api/sunpower/enquiry`.
4. Bring the customer portal (`/my/solar`) and the crew page into React using the same JSON-RPC pattern.
5. Add a Playwright smoke test for the React flows (estimate → book survey, quote, console login).

## Repository history note

Before this push, `main` on GitHub held a separate **Next.js/Prisma prototype** (3 commits, tag `phase-0a-approved`). Its files were removed from the working tree by a normal merge commit, *without* a force push. Its history and the tag are still in the repository. To look at that code:
```powershell
git checkout phase-0a-approved
```
