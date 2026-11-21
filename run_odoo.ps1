# Starts Odoo 18 (installed from source in C:\Users\Ankit Kumar\odoo18) with the SunPower addons.
# Uses a private PostgreSQL 18 server on port 5433 (data in odoo18\pgdata); starts it if needed.
# Usage:  .\run_odoo.ps1                 -> run server on http://localhost:8069
#         .\run_odoo.ps1 -Update         -> upgrade sunpower_solar first
param([switch]$Update, [string]$Db = "sunpower")
$root = "C:\Users\Ankit Kumar\odoo18"
$pgctl = "C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe"
& $pgctl -D "$root\pgdata" status *> $null
if ($LASTEXITCODE -ne 0) {
    & $pgctl -D "$root\pgdata" -o "-p 5433" -l "$root\pg.log" start -w
}
$py = "$root\venv\Scripts\python.exe"
$odooArgs = @("$root\odoo\odoo-bin", "-c", "$root\odoo.conf", "-d", $Db)
if ($Update) { $odooArgs += @("-u", "sunpower_solar") }
& $py @odooArgs
