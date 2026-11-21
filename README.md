# SunPower – Solar Installation Management System

## Local setup (no Docker)

1. Install **Odoo 18 Community for Windows** (nightly.odoo.com → 18.0 → Windows). Keep the bundled PostgreSQL.
2. Open the installer's `server\odoo.conf` and append this repo's addons folder to `addons_path`, e.g.
   `addons_path = C:\Program Files\Odoo 18.0\server\odoo\addons,C:\Users\Ankit Kumar\OneDrive\Desktop\SunPower\addons`
3. Restart the "odoo-server-18.0" Windows service, open http://localhost:8069, create a database, and install **SunPower Solar**.
4. AI service (optional):
   ```powershell
   cd ai_service; python -m venv .venv; .venv\Scripts\activate; pip install -r requirements.txt; uvicorn main:app --port 8000
   ```
   Odoo calls it at `http://localhost:8000`. `HF_TOKEN` is read from `.env`.
