# SunPower: Solar Installation Management System

Everything a rooftop-solar company needs to run, from the first customer enquiry to the 20-year panel warranty. It is built on **Odoo 18**, with a **FastAPI AI service** and a **React website**.

```
 Customer ──► React website (frontend/, :5173) ──┐
                                                   ├──► Odoo 18 engine (addons/, :8069) ──► PostgreSQL
 Staff / crew ──► Odoo backend + /technician ─────┘            │
                                                                └──► AI service (ai_service/, :8000)
```

---

## How to run

You need **Windows**, **Python 3.11–3.13**, **Node 18+**, **PostgreSQL 14+** and **Odoo 18 Community** (installed from source or with the Windows installer).

### 1. Odoo engine (required)

1. In your `odoo.conf`, add this repo's `addons` folder to `addons_path`:
   ```ini
   addons_path = <odoo>\odoo\addons,<odoo>\addons,<this repo>\addons
   ```
2. Create the database. This installs all three modules and loads realistic demo data:
   ```powershell
   & "<odoo venv>\Scripts\python.exe" scripts\rebuild_db.py        # add --no-demo for an empty company
   ```
   Or, from the Odoo UI: create a database (country **India**) → Apps → install **SunPower Solar Operations**, then **SunPower Website** and **SunPower AI Helpers** → *SunPower → Configuration → Load Demo Data*.
3. Start Odoo and open **http://localhost:8069**:
   ```powershell
   .\run_odoo.ps1             # add -Update after changing module code
   ```
   `run_odoo.ps1` and `scripts\rebuild_db.py` have the original developer's paths written into them (`C:\Users\...\odoo18`). Change `$root` / `ODOO_ROOT` to match your machine.

**Demo logins:** `admin` / `admin` (director); technicians `tech01@sunpower.demo` … `tech15@sunpower.demo` / `sunpower`.

### 2. React website (optional, the public site and staff console)

```powershell
cd frontend
npm install
npm run dev                 # http://localhost:5173
```
The dev server forwards `/api` and `/web` to Odoo on `:8069` and `/ai` to the AI service on `:8000`. Override these with the `SUNPOWER_ENGINE` and `SUNPOWER_AI` environment variables. Use `npm run build` and then `npm run preview` (:4173) for a production build; it forwards requests the same way.

### 3. AI service (optional, used for bill reading, voice/WhatsApp intake, fault diagnosis and photo checks)

```powershell
cd ai_service
powershell -ExecutionPolicy Bypass -File .\run.ps1      # creates .venv, installs, serves :8000
```
It runs for free on CPU. The first start downloads about 2 GB of models. `HF_TOKEN` in a root `.env` file is optional. Everything still works when the service is off: users just fill fields in by hand. See [ai_service/README.md](ai_service/README.md).

### 4. Checks

```powershell
# Odoo unit tests
& "<odoo venv>\Scripts\python.exe" "<odoo>\odoo-bin" -c odoo.conf -d sunpower --test-tags sunpower -u sunpower_solar --stop-after-init
# End-to-end phase checks (roll back their own data)
Get-Content scripts\phase_checks.py | & "<odoo venv>\Scripts\python.exe" "<odoo>\odoo-bin" shell -c odoo.conf -d sunpower
```

---

## The business flow

1. **Enquiry.** It comes from the website, WhatsApp or a phone call. A lead is created, the least-busy salesperson is assigned, and a "call within 2 hours" task is set.
2. **Phone screening.** Roof area, bill and grid suitability are recorded. A suggested system size is worked out from the bill (units ÷ 120).
3. **Roof survey.** It is scheduled, visited and then approved. **No quote can be made before the survey is approved.**
4. **Quote.** The matching package (1–5 kW, On-Grid or Off-Grid) is picked automatically. GST is added: 12% on goods, 18% on installation. A PVGIS generation and payback estimate goes on the PDF.
5. **Order confirmed.** This creates the warehouse delivery, a crew installation job and a PM Surya Ghar subsidy file.
6. **Dispatch.** It is blocked until a **30% advance** is paid. Serial and lot numbers are scanned, and **warranties start automatically** for each serial (panels 20 years; inverter, battery and controller 2 years).
7. **Installation.** The crew completes a checklist, uploads photos, confirms the kW and gets the customer's signature. Hours are logged against the job and a certificate PDF is emailed to the customer.
8. **Service tickets.** Tickets can be found by phone number or serial number. Repairs under warranty are free; outside warranty they are invoiced automatically. The customer confirms the fix on the portal.
9. **Director dashboard.** Shows profit per job (revenue − material − labour − repairs), collections, subsidies, stock and overdue repairs. The report can be downloaded or emailed as a PDF.

---

## What does what

| Path | What it is |
|---|---|
| **`addons/sunpower_solar/`** | **The core Odoo module.** Contains all the business logic above. |
| `├─ hooks.py` | Install-time setup: company, GST taxes and HSN codes, product categories with warranty terms, components, 10 kits as phantom BoMs, quotation templates and the project template |
| `├─ models/crm_lead.py` | Enquiry intake (`solar_create_enquiry`), screening, survey gating, automatic template choice |
| `├─ models/site_survey.py` | `solar.site.survey`: roof measurements and the approval flow |
| `├─ models/sale_order.py` | Survey gate, actions after confirmation, PVGIS estimate, job profitability, job stage |
| `├─ models/stock.py` | Advance-payment check before dispatch; warranty creation for each delivered serial |
| `├─ models/warranty.py` | `solar.warranty`: register of warranties per serial |
| `├─ models/project_task.py` | Crew installation job: checklist, signature, timesheets, certificate |
| `├─ models/service_ticket.py` | `solar.service.ticket`: repair flow, free vs billable, automatic invoice, portal confirmation |
| `├─ models/subsidy.py` | `solar.subsidy.application`: PM Surya Ghar pipeline and expected amount |
| `├─ models/dashboard.py` | Director dashboard data plus the shareable PDF/email report |
| `├─ models/demo_data.py` | One-click realistic demo: about 40 jobs, 15 technicians, tickets and subsidies |
| `├─ wizards/enquiry_wizard.py` | "Log WhatsApp / Call" wizard, for both enquiries and complaints |
| `├─ controllers/main.py` | `/solar-quote` web form and the `/my/solar-ticket` portal confirmation |
| `├─ static/src/dashboard/` | OWL director dashboard (JS, XML template, SCSS) |
| `├─ report/` | Installation certificate, director report, solar box added to the quote PDF |
| `├─ views/`, `data/`, `security/` | Backend screens and menus, sequences, cron, email template, access rights |
| `└─ tests/test_solar_flow.py` | Unit tests for the main flow |
| **`addons/sunpower_ai/`** | Connects Odoo to the AI service: buttons that read a bill, fill an enquiry from text or voice, diagnose a fault and check install photos. They fall back to manual entry when the service is off. The service URL is the system parameter `sunpower_ai.url`. |
| **`addons/sunpower_website/`** | Odoo website pages: home page, `/solar/estimate`, the `/my/solar` customer portal, the `/technician` crew page, branding. Also holds **the JSON API used by the React site**: `/api/sunpower/estimate` and `/api/sunpower/enquiry`. |
| **`ai_service/`** | FastAPI service: `/bill/parse`, `/lead/parse`, `/fault/diagnose`, `/photo/check`, `/health`. It tries remote Hugging Face first, then local CPU models (Qwen2.5, Whisper, MiniLM, RapidOCR, ConvNeXt), then regex or the knowledge base. `kb/fault_codes.json` has 31 inverter faults. |
| **`frontend/`** | React 18 + Vite website in a minimalist light design. |
| `├─ src/pages/` | `Home`, `Estimate` (live calculator, bill upload, survey booking), `Quote`, `NotFound` |
| `├─ src/console/Console.jsx` | Staff login and live director dashboard (uses the Odoo session) |
| `├─ src/components/ui/` | Arc UI-style components written for this app: `Tabs`, `ElasticSlider`, `Switch`, `Toast`, `Reveal` |
| `├─ src/components/reactbits/` | ReactBits components: MaskedHeading, ScrollStack, AccordionGallery, BubbleMenu, FuzzyText and others |
| `├─ src/api.js`, `src/solar.js` | Client for the engine and AI service; the estimate rules shared with the backend |
| `└─ vite.config.js` | Proxy settings: `/api`, `/web` → Odoo, `/ai` → AI service |
| **`scripts/`** | `rebuild_db.py` (fresh database plus demo data), `phase_checks.py` (end-to-end checks) |
| **`docs/`** | Final report (`sunpower_report.html`) and sample PDFs: quote, certificate, director report |
| `run_odoo.ps1` | Starts the local PostgreSQL and Odoo |
| `HANDOFF.md` | Current state, known issues and next steps for whoever picks this up |

## Tech stack

Odoo 18 Community (Python, OWL, QWeb) · PostgreSQL · FastAPI + Transformers/TensorFlow/RapidOCR · React 18 + Vite + GSAP · PVGIS (EU JRC) for generation estimates.
