"""SQLite storage: one file, no server. Set SUNPOWER_DB to move it.

Small helpers keep SQL readable:  q() many rows, one() single row,
insert() returns the new id, update() writes a dict of fields.
"""
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("SUNPOWER_DB", Path(__file__).resolve().parent.parent / "data" / "sunpower.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS sequences (name TEXT PRIMARY KEY, next INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS customers (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT, phone TEXT, street TEXT, city TEXT,
  created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_customers_email ON customers(email COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
  phone TEXT, password_hash TEXT, role TEXT NOT NULL,
  customer_id INTEGER REFERENCES customers(id), hourly_rate REAL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1, last_login TEXT, created_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tokens (
  token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), kind TEXT NOT NULL,
  expires_at TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0);

CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY, code TEXT UNIQUE, name TEXT NOT NULL, category TEXT NOT NULL,
  tracking TEXT NOT NULL DEFAULT 'none', cost REAL NOT NULL DEFAULT 0, price REAL NOT NULL DEFAULT 0,
  tax_rate REAL NOT NULL DEFAULT 12, warranty_months INTEGER NOT NULL DEFAULT 0,
  qty_on_hand REAL NOT NULL DEFAULT 0, min_qty REAL NOT NULL DEFAULT 0,
  is_kit INTEGER NOT NULL DEFAULT 0, kw REAL, system_type TEXT, is_service INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS kit_lines (
  kit_id INTEGER NOT NULL REFERENCES products(id), product_id INTEGER NOT NULL REFERENCES products(id),
  qty REAL NOT NULL);

CREATE TABLE IF NOT EXISTS leads (
  id INTEGER PRIMARY KEY, ref TEXT, customer_id INTEGER REFERENCES customers(id),
  contact_name TEXT NOT NULL, phone TEXT, email TEXT, street TEXT, city TEXT,
  channel TEXT NOT NULL DEFAULT 'web', requested_kw REAL DEFAULT 0, system_type TEXT DEFAULT 'on_grid',
  subsidy_requested INTEGER DEFAULT 0, monthly_bill REAL DEFAULT 0, monthly_units REAL DEFAULT 0,
  roof_area_sqft REAL DEFAULT 0, grid_suitable TEXT DEFAULT 'unknown', discom TEXT, consumer_no TEXT,
  notes TEXT, stage TEXT NOT NULL DEFAULT 'new', lost_reason TEXT,
  salesperson_id INTEGER REFERENCES users(id), next_action TEXT, next_action_due TEXT,
  created_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS surveys (
  id INTEGER PRIMARY KEY, ref TEXT, lead_id INTEGER NOT NULL REFERENCES leads(id),
  technician_id INTEGER REFERENCES users(id), survey_date TEXT, state TEXT NOT NULL DEFAULT 'scheduled',
  roof_type TEXT, roof_direction TEXT, roof_tilt REAL, usable_area_sqft REAL DEFAULT 0,
  shading TEXT DEFAULT 'none', cable_distance_m REAL, earthing_possible INTEGER DEFAULT 1,
  latitude REAL, longitude REAL, recommended_kw REAL DEFAULT 0, notes TEXT, rejection_reason TEXT,
  created_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY, ref TEXT, lead_id INTEGER REFERENCES leads(id),
  customer_id INTEGER NOT NULL REFERENCES customers(id), survey_id INTEGER REFERENCES surveys(id),
  state TEXT NOT NULL DEFAULT 'draft', kit_product_id INTEGER REFERENCES products(id),
  kw REAL DEFAULT 0, system_type TEXT, salesperson_id INTEGER REFERENCES users(id),
  date_order TEXT NOT NULL, valid_until TEXT, confirmed_at TEXT, note TEXT,
  amount_untaxed REAL DEFAULT 0, amount_tax REAL DEFAULT 0, amount_total REAL DEFAULT 0,
  accepted_by TEXT, accepted_at TEXT, access_token TEXT,
  est_kwh_year REAL, est_savings_year REAL, est_payback_years REAL, est_source TEXT,
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS order_lines (
  id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  product_id INTEGER REFERENCES products(id), description TEXT, qty REAL NOT NULL DEFAULT 1,
  price_unit REAL NOT NULL DEFAULT 0, discount REAL NOT NULL DEFAULT 0, tax_rate REAL NOT NULL DEFAULT 0,
  subtotal REAL NOT NULL DEFAULT 0);

CREATE TABLE IF NOT EXISTS invoices (
  id INTEGER PRIMARY KEY, ref TEXT, order_id INTEGER REFERENCES orders(id),
  ticket_id INTEGER, customer_id INTEGER NOT NULL REFERENCES customers(id), kind TEXT NOT NULL,
  amount_untaxed REAL NOT NULL, amount_tax REAL NOT NULL, amount_total REAL NOT NULL,
  amount_paid REAL NOT NULL DEFAULT 0, date TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'posted');
CREATE TABLE IF NOT EXISTS payments (
  id INTEGER PRIMARY KEY, ref TEXT, order_id INTEGER REFERENCES orders(id), invoice_id INTEGER REFERENCES invoices(id),
  customer_id INTEGER REFERENCES customers(id), amount REAL NOT NULL, method TEXT NOT NULL,
  provider_ref TEXT, state TEXT NOT NULL DEFAULT 'pending', purpose TEXT, date TEXT NOT NULL,
  created_by INTEGER REFERENCES users(id));

CREATE TABLE IF NOT EXISTS deliveries (
  id INTEGER PRIMARY KEY, ref TEXT, order_id INTEGER NOT NULL REFERENCES orders(id),
  state TEXT NOT NULL DEFAULT 'waiting', date_done TEXT, done_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS delivery_lines (
  id INTEGER PRIMARY KEY, delivery_id INTEGER NOT NULL REFERENCES deliveries(id) ON DELETE CASCADE,
  product_id INTEGER NOT NULL REFERENCES products(id), qty REAL NOT NULL, serials TEXT);
CREATE TABLE IF NOT EXISTS serials (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, product_id INTEGER NOT NULL REFERENCES products(id),
  state TEXT NOT NULL DEFAULT 'in_stock', delivery_id INTEGER REFERENCES deliveries(id),
  customer_id INTEGER REFERENCES customers(id), order_id INTEGER REFERENCES orders(id),
  created_at TEXT NOT NULL, UNIQUE(name, product_id));
CREATE TABLE IF NOT EXISTS stock_moves (
  id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id), qty REAL NOT NULL,
  kind TEXT NOT NULL, delivery_id INTEGER, note TEXT, user_id INTEGER, date TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS warranties (
  id INTEGER PRIMARY KEY, serial_id INTEGER NOT NULL REFERENCES serials(id),
  product_id INTEGER NOT NULL REFERENCES products(id), customer_id INTEGER NOT NULL REFERENCES customers(id),
  order_id INTEGER REFERENCES orders(id), delivery_id INTEGER REFERENCES deliveries(id),
  start_date TEXT NOT NULL, months INTEGER NOT NULL, end_date TEXT NOT NULL,
  UNIQUE(serial_id, customer_id));

CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY, ref TEXT, order_id INTEGER NOT NULL REFERENCES orders(id),
  customer_id INTEGER NOT NULL REFERENCES customers(id), kw_planned REAL, kw_confirmed REAL,
  scheduled_at TEXT, state TEXT NOT NULL DEFAULT 'planned', site_start TEXT, site_end TEXT,
  chk_stands INTEGER DEFAULT 0, chk_panels INTEGER DEFAULT 0, chk_wiring INTEGER DEFAULT 0,
  chk_earthing INTEGER DEFAULT 0, chk_generation INTEGER DEFAULT 0, generation_reading_kw REAL,
  signed_by TEXT, signature TEXT, signed_on TEXT, photo_check TEXT, notes TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS job_techs (
  job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE, user_id INTEGER NOT NULL REFERENCES users(id),
  PRIMARY KEY (job_id, user_id));
CREATE TABLE IF NOT EXISTS timesheets (
  id INTEGER PRIMARY KEY, job_id INTEGER REFERENCES jobs(id), user_id INTEGER NOT NULL REFERENCES users(id),
  hours REAL NOT NULL, rate REAL NOT NULL, date TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS attachments (
  id INTEGER PRIMARY KEY, owner_type TEXT NOT NULL, owner_id INTEGER NOT NULL, filename TEXT,
  mime TEXT, data BLOB NOT NULL, note TEXT, created_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS tickets (
  id INTEGER PRIMARY KEY, ref TEXT, customer_id INTEGER NOT NULL REFERENCES customers(id),
  serial_id INTEGER REFERENCES serials(id), warranty_id INTEGER REFERENCES warranties(id),
  product_id INTEGER REFERENCES products(id), order_id INTEGER REFERENCES orders(id),
  technician_id INTEGER REFERENCES users(id), stage TEXT NOT NULL DEFAULT 'new', priority TEXT DEFAULT '0',
  reported_on TEXT NOT NULL, closed_on TEXT, fault_code TEXT, description TEXT, resolution TEXT,
  ai_diagnosis TEXT, labour_hours REAL DEFAULT 0, labour_rate REAL DEFAULT 500,
  invoice_id INTEGER REFERENCES invoices(id), customer_confirmed INTEGER DEFAULT 0, channel TEXT);
CREATE TABLE IF NOT EXISTS ticket_lines (
  id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  product_id INTEGER NOT NULL REFERENCES products(id), qty REAL NOT NULL DEFAULT 1,
  price_unit REAL NOT NULL DEFAULT 0, cost REAL NOT NULL DEFAULT 0, new_serial TEXT);

CREATE TABLE IF NOT EXISTS subsidies (
  id INTEGER PRIMARY KEY, ref TEXT, order_id INTEGER NOT NULL REFERENCES orders(id),
  customer_id INTEGER NOT NULL REFERENCES customers(id), kw REAL,
  scheme TEXT DEFAULT 'PM Surya Ghar Muft Bijli Yojana', application_no TEXT,
  state TEXT NOT NULL DEFAULT 'draft', applied_on TEXT, inspection_on TEXT, disbursed_on TEXT,
  amount_expected REAL DEFAULT 0, amount_received REAL DEFAULT 0,
  doc_id_proof INTEGER DEFAULT 0, doc_bill INTEGER DEFAULT 0, doc_bank INTEGER DEFAULT 0,
  doc_photo INTEGER DEFAULT 0, doc_net_meter INTEGER DEFAULT 0);

CREATE TABLE IF NOT EXISTS notes (
  id INTEGER PRIMARY KEY, model TEXT NOT NULL, res_id INTEGER NOT NULL, author_id INTEGER,
  body TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'log', created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_notes ON notes(model, res_id);

CREATE TABLE IF NOT EXISTS mail_queue (
  id INTEGER PRIMARY KEY, email_to TEXT NOT NULL, subject TEXT NOT NULL, html TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'queued', error TEXT, created_at TEXT NOT NULL, sent_at TEXT);
"""

_local = threading.local()


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def today():
    return datetime.now().strftime("%Y-%m-%d")


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # One connection per request; FastAPI may run the dependency and the endpoint
    # on different worker threads, so allow that (it is never used concurrently).
    conn = sqlite3.connect(DB_PATH, timeout=15, detect_types=0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


# Columns added after the first release: added in place to existing databases.
MIGRATIONS = [
    ("users", "recovery_code_hash", "TEXT"),          # 4-digit code for "forgot password"
    ("users", "onboarded", "INTEGER NOT NULL DEFAULT 0"),  # welcome tour shown once
]


def init_db(conn=None):
    own = conn is None
    conn = conn or connect()
    conn.executescript(SCHEMA)
    for table, column, kind in MIGRATIONS:
        if column not in [r[1] for r in conn.execute("PRAGMA table_info(%s)" % table)]:
            conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, column, kind))
    conn.commit()
    if own:
        conn.close()


class DB:
    """Thin wrapper around one connection (one per request)."""

    def __init__(self, conn):
        self.conn = conn

    def q(self, sql, *args):
        return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def one(self, sql, *args):
        r = self.conn.execute(sql, args).fetchone()
        return dict(r) if r else None

    def val(self, sql, *args):
        r = self.conn.execute(sql, args).fetchone()
        return r[0] if r else None

    def exec(self, sql, *args):
        return self.conn.execute(sql, args)

    def insert(self, table, data):
        cols = ", ".join(data)
        marks = ", ".join("?" for _ in data)
        cur = self.conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(data.values()))
        return cur.lastrowid

    def update(self, table, rid, data):
        if not data:
            return
        sets = ", ".join(f"{k} = ?" for k in data)
        self.conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*data.values(), rid))

    def get(self, table, rid):
        return self.one(f"SELECT * FROM {table} WHERE id = ?", rid)

    def next_ref(self, name, prefix, width=5):
        row = self.one("SELECT next FROM sequences WHERE name = ?", name)
        n = row["next"] if row else 1
        if row:
            self.exec("UPDATE sequences SET next = ? WHERE name = ?", n + 1, name)
        else:
            self.exec("INSERT INTO sequences (name, next) VALUES (?, ?)", name, n + 1)
        return f"{prefix}{n:0{width}d}"

    def setting(self, key, default=None):
        v = self.val("SELECT value FROM settings WHERE key = ?", key)
        return default if v is None else v

    def set_setting(self, key, value):
        self.exec("INSERT INTO settings (key, value) VALUES (?, ?) "
                  "ON CONFLICT(key) DO UPDATE SET value = excluded.value", key, None if value is None else str(value))

    def note(self, model, res_id, body, author_id=None, kind="log"):
        self.insert("notes", {"model": model, "res_id": res_id, "author_id": author_id,
                              "body": body, "kind": kind, "created_at": now()})

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()


@contextmanager
def session():
    conn = connect()
    db = DB(conn)
    try:
        yield db
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_db():
    """FastAPI dependency: one connection per request, committed at the end."""
    conn = connect()
    db = DB(conn)
    try:
        yield db
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
