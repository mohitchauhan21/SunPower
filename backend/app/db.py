"""SQLite storage: one file, no server. Set SUNPOWER_DB to move it.

Small helpers keep SQL readable:  q() many rows, one() single row,
insert() returns the new id, update() writes a dict of fields.

WHAT THIS FILE DOES
  * Defines every table of the app (SCHEMA) and creates them on start-up (init_db).
  * Opens a connection to the database file (connect).
  * Wraps that connection in a small helper class (DB) so the rest of the code can
    write  db.q("SELECT ...")  instead of dealing with cursors.
  * Gives FastAPI one connection per web request (get_db) and scripts one per
    "with session() as db:" block (session).

WHO USES IT
  Every router (app/routers/*.py) gets a DB object through `db=Depends(get_db)`;
  rules.py, seed.py and mailer.py receive that same object as their `db` argument.

SQLite in one sentence: a whole SQL database stored in a single file
(backend/data/sunpower.db), with no separate database server to install.
"""
import os                                   # read environment variables (SUNPOWER_DB)
import sqlite3                              # Python's built-in SQLite driver
import threading                            # only for the unused _local below (kept for compatibility)
from contextlib import contextmanager       # turns a generator function into a "with ...:" block
from datetime import datetime, timezone     # timestamps
from pathlib import Path                    # file paths that work on Windows and macOS

# Where the database file lives. os.environ.get(NAME, default) reads an environment
# variable and falls back to the default: backend/data/sunpower.db.
# Path(__file__) is this file; .resolve().parent.parent climbs app/ -> backend/.
DB_PATH = Path(os.environ.get("SUNPOWER_DB", Path(__file__).resolve().parent.parent / "data" / "sunpower.db"))

# ---------------------------------------------------------------------------
# SCHEMA: the CREATE TABLE statements for the whole app, run on every start.
# "IF NOT EXISTS" makes that safe: existing tables (and their data) are kept.
# Column types: TEXT (strings, also dates as "YYYY-MM-DD HH:MM:SS"), INTEGER,
# REAL (decimal numbers), BLOB (raw bytes, used for photos).
# "REFERENCES other(id)" = a foreign key: the value must be an id in that table.
#
#   settings      key/value company settings (advance %, SMTP, keys ...)
#   sequences     counters for readable references (ENQ-00001, SO-00001 ...)
#   customers     homeowners / businesses
#   users         everyone who can sign in: staff (with a role) and customers
#   sessions      signed-in browsers (only a hash of the cookie is stored)
#   tokens        one-time links (password reset, invites), stored hashed
#   products      components, the 10 solar packages (is_kit=1) and services
#   kit_lines     which components (and how many) make up each package
#   leads         enquiries
#   surveys       roof surveys for an enquiry
#   orders        quotations (state draft/sent) and confirmed orders (sale)
#   order_lines   the lines of a quotation/order
#   invoices      advance, final and service invoices
#   payments      money received (or pending online payments)
#   deliveries    the warehouse delivery for an order; delivery_lines = what to pack
#   serials       every serial / batch number in stock or delivered
#   stock_moves   history of stock in (+) and out (-)
#   warranties    one per delivered serial: start and end date
#   jobs          installation jobs; job_techs = which technicians are on the crew
#   timesheets    hours worked per technician per job (labour cost)
#   attachments   uploaded photos (stored inside the database as bytes)
#   tickets       service / repair requests; ticket_lines = parts used
#   subsidies     PM Surya Ghar subsidy files
#   notes         the activity timeline shown on every record
#   mail_queue    emails waiting to be sent by the background mail worker
# ---------------------------------------------------------------------------
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

# threading.local() = a storage box that each thread sees separately. Not used any
# more (every request gets its own connection), kept so old imports keep working.
_local = threading.local()


def now():
    """Current time in UTC as text, e.g. "2026-11-21 09:30:00".

    Used for every *event* time (created, paid, dispatched...). UTC avoids
    confusion when the server and the user are in different time zones; the
    website converts it back to local time for display.
    .replace(microsecond=0) drops the fractions of a second; strftime formats it.
    """
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def today():
    """Today's date on the server, in local time, as "YYYY-MM-DD"."""
    return datetime.now().strftime("%Y-%m-%d")


def connect():
    """Open the database file and return a ready-to-use sqlite3 connection."""
    # Create backend/data/ if it doesn't exist yet. exist_ok=True: no error if it does.
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # One connection per request; FastAPI may run the dependency and the endpoint
    # on different worker threads, so allow that (it is never used concurrently).
    # timeout=15: if another request is writing, wait up to 15 s instead of failing.
    conn = sqlite3.connect(DB_PATH, timeout=15, detect_types=0, check_same_thread=False)
    # row_factory = sqlite3.Row makes each row behave like a dict: row["name"].
    conn.row_factory = sqlite3.Row
    # PRAGMA = an SQLite setting. foreign_keys=ON makes REFERENCES actually enforced.
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL ("write-ahead log") lets readers keep reading while one request writes.
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


# Columns added after the first release: added in place to existing databases.
MIGRATIONS = [
    ("users", "recovery_code_hash", "TEXT"),          # 4-digit code for "forgot password"
    ("users", "onboarded", "INTEGER NOT NULL DEFAULT 0"),  # welcome tour shown once
    ("leads", "state", "TEXT"),                       # state / UT (sets the subsidy)
    ("customers", "state", "TEXT"),
    ("leads", "preferred_date", "TEXT"),             # survey: the day the customer prefers
    ("leads", "preferred_slot", "TEXT"),             # survey: morning / afternoon / evening
    ("leads", "project_ref", "TEXT"),                # one project ID for the whole journey, e.g. SP-26-00042
    ("leads", "booking_confirmed_at", "TEXT"),       # Sales called and confirmed the survey booking
    ("users", "service_area", "TEXT"),               # technicians: cities / states they cover, comma separated
    ("orders", "payment_plan", "TEXT"),              # advance (30% now, rest later) or full (100% upfront)
    ("orders", "approval_state", "TEXT"),            # pending / approved: discount above the limit needs approval
    ("orders", "created_by", "INTEGER"),             # who built the quote (technician or sales)
    ("deliveries", "packed_at", "TEXT"),             # warehouse: kit packed
    ("deliveries", "delivered_at", "TEXT"),          # kit received at the customer's site
    ("deliveries", "vehicle", "TEXT"),               # vehicle / courier and tracking note
    ("deliveries", "expected_on", "TEXT"),           # expected delivery day
    ("products", "location", "TEXT"),                 # warehouse rack / bin, e.g. "A-03"
    ("products", "unit", "TEXT"),                     # pcs, m, set...
    ("surveys", "project_ref", "TEXT"),   # the enquiry's universal project ID (kept by triggers)
    ("orders", "project_ref", "TEXT"),
    ("deliveries", "project_ref", "TEXT"),
    ("jobs", "project_ref", "TEXT"),
    ("subsidies", "project_ref", "TEXT"),
    ("invoices", "project_ref", "TEXT"),
    ("payments", "project_ref", "TEXT"),
    ("warranties", "project_ref", "TEXT"),
    ("tickets", "project_ref", "TEXT"),
    ("surveys", "details", "TEXT"),                   # full site survey (JSON): electrical, cabling, mounting, issues...
    ("surveys", "result", "TEXT"),                    # technician's conclusion: feasible / conditional / not_feasible
]


_FROM_LEAD = "(SELECT project_ref FROM leads WHERE id = NEW.lead_id)"
_FROM_ORDER = "(SELECT project_ref FROM orders WHERE id = NEW.order_id)"
PROJECT_TRIGGERS = "".join(
    "CREATE TRIGGER IF NOT EXISTS %s_project_ins AFTER INSERT ON %s BEGIN "
    "UPDATE %s SET project_ref = %s WHERE id = NEW.id; END;\n"
    "CREATE TRIGGER IF NOT EXISTS %s_project_upd AFTER UPDATE OF %s ON %s BEGIN "
    "UPDATE %s SET project_ref = %s WHERE id = NEW.id; END;\n" % (t, t, t, src, t, key, t, t, src)
    for t, key, src in [("surveys", "lead_id", _FROM_LEAD), ("orders", "lead_id", _FROM_LEAD)]
    + [(t, "order_id", _FROM_ORDER) for t in ("deliveries", "jobs", "subsidies", "invoices", "payments", "warranties", "tickets")]
) + (
    # an enquiry gets its ID just after it is created: pass it on to anything already linked
    "CREATE TRIGGER IF NOT EXISTS leads_project_set AFTER UPDATE OF project_ref ON leads BEGIN "
    "UPDATE surveys SET project_ref = NEW.project_ref WHERE lead_id = NEW.id; "
    "UPDATE orders SET project_ref = NEW.project_ref WHERE lead_id = NEW.id; END;\n"
)
PROJECT_BACKFILL = [
    "UPDATE surveys SET project_ref = (SELECT project_ref FROM leads WHERE id = surveys.lead_id) WHERE project_ref IS NULL",
    "UPDATE orders SET project_ref = (SELECT project_ref FROM leads WHERE id = orders.lead_id) WHERE project_ref IS NULL",
] + ["UPDATE %s SET project_ref = (SELECT project_ref FROM orders WHERE id = %s.order_id) WHERE project_ref IS NULL" % (t, t)
     for t in ("deliveries", "jobs", "subsidies", "invoices", "payments", "warranties", "tickets")]


def init_db(conn=None):
    """Create all tables (and add any newer columns). Called once at start-up by main.bootstrap()."""
    own = conn is None                 # True when we opened the connection ourselves (so we close it)
    conn = conn or connect()           # "a or b": use the given connection, else open one
    conn.executescript(SCHEMA)         # run every CREATE TABLE statement in one go
    # Migrations: PRAGMA table_info(t) lists a table's columns; r[1] is the column name.
    # If a column from MIGRATIONS is missing (an older database), add it with ALTER TABLE.
    for table, column, kind in MIGRATIONS:
        if column not in [r[1] for r in conn.execute("PRAGMA table_info(%s)" % table)]:
            conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, column, kind))
    # Give older enquiries their project ID (same rule as rules.create_enquiry).
    conn.execute("UPDATE leads SET project_ref = 'SP-' || substr(created_at, 3, 2) || '-' || printf('%05d', id) "
                 "WHERE project_ref IS NULL")
    # One universal ID per enquiry: every record made from it carries the same project ID, filled in by the
    # database itself whenever a record is created or re-linked, so no code path can forget it.
    conn.executescript(PROJECT_TRIGGERS)
    for sql in PROJECT_BACKFILL:   # records made before this existed
        conn.execute(sql)
    conn.commit()                      # save the changes to the file
    if own:
        conn.close()


class DB:
    """Thin wrapper around one connection (one per request).

    Every method takes SQL with "?" placeholders plus the values separately, e.g.
        db.q("SELECT * FROM leads WHERE stage = ?", "new")
    sqlite3 fills the "?" safely, which prevents SQL injection (a user typing SQL
    into a form can never change the query).
    """

    def __init__(self, conn):
        # __init__ runs when you write DB(conn); it just remembers the connection.
        self.conn = conn

    def q(self, sql, *args):
        """Many rows -> list of dicts. *args collects all extra arguments into a tuple."""
        return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def one(self, sql, *args):
        """First row as a dict, or None when there is no row."""
        r = self.conn.execute(sql, args).fetchone()
        return dict(r) if r else None

    def val(self, sql, *args):
        """A single value (first column of the first row), e.g. a COUNT(*). None if no row."""
        r = self.conn.execute(sql, args).fetchone()
        return r[0] if r else None

    def exec(self, sql, *args):
        """Run any statement (UPDATE, DELETE...) and return the cursor."""
        return self.conn.execute(sql, args)

    def insert(self, table, data):
        """INSERT a dict as one row; returns the new row's id.

        Example: db.insert("notes", {"model": "lead", "body": "Hi"}) builds
        INSERT INTO notes (model, body) VALUES (?, ?)  with the dict's values.
        """
        cols = ", ".join(data)                      # iterating a dict gives its keys
        marks = ", ".join("?" for _ in data)        # one "?" per column; _ = "value not needed"
        # f"..." is an f-string: {table} etc. are replaced by the variables' values.
        # Only our own table/column names go into the f-string; user data goes through "?".
        cur = self.conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(data.values()))
        return cur.lastrowid                        # the id SQLite gave the new row

    def update(self, table, rid, data):
        """UPDATE the row with id=rid, setting each key of `data` to its value."""
        if not data:                                # nothing to change: do nothing
            return
        sets = ", ".join(f"{k} = ?" for k in data)  # "name = ?, phone = ?"
        # (*data.values(), rid) unpacks the values into a tuple and appends the id.
        self.conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*data.values(), rid))

    def get(self, table, rid):
        """One row by id (or None)."""
        return self.one(f"SELECT * FROM {table} WHERE id = ?", rid)

    def next_ref(self, name, prefix, width=5):
        """Next readable reference for a sequence, e.g. next_ref("order", "SO-") -> "SO-00042"."""
        row = self.one("SELECT next FROM sequences WHERE name = ?", name)
        n = row["next"] if row else 1               # first use of a sequence starts at 1
        if row:
            self.exec("UPDATE sequences SET next = ? WHERE name = ?", n + 1, name)
        else:
            self.exec("INSERT INTO sequences (name, next) VALUES (?, ?)", name, n + 1)
        # {n:0{width}d} formats n as a whole number padded with zeros to `width` digits.
        return f"{prefix}{n:0{width}d}"

    def setting(self, key, default=None):
        """Read a company setting (always text), or `default` if it was never set."""
        v = self.val("SELECT value FROM settings WHERE key = ?", key)
        return default if v is None else v

    def set_setting(self, key, value):
        """Save a setting. "ON CONFLICT ... DO UPDATE" = insert it, or overwrite if the key exists
        ("upsert"); `excluded.value` means "the value we tried to insert"."""
        self.exec("INSERT INTO settings (key, value) VALUES (?, ?) "
                  "ON CONFLICT(key) DO UPDATE SET value = excluded.value", key, None if value is None else str(value))

    def note(self, model, res_id, body, author_id=None, kind="log"):
        """Add a line to a record's activity timeline.
        model/res_id say which record ("lead", 12); kind is "log" (automatic) or "note" (typed by a person)."""
        self.insert("notes", {"model": model, "res_id": res_id, "author_id": author_id,
                              "body": body, "kind": kind, "created_at": now()})

    def commit(self):
        """Save everything done since the last commit."""
        self.conn.commit()

    def rollback(self):
        """Undo everything done since the last commit."""
        self.conn.rollback()


# @contextmanager is a *decorator*: it wraps the function below so it can be used as
#     with session() as db:
#         ...
# Everything before `yield` runs when the block starts, `yield db` hands db to the
# block, and the code after it runs when the block ends. Used by start-up, the
# demo-data loader and the mail worker (code that is not part of a web request).
@contextmanager
def session():
    conn = connect()
    db = DB(conn)
    try:
        yield db                 # the "with" block runs here
        conn.commit()            # block finished without error: save
    except Exception:
        conn.rollback()          # an error happened: undo the half-done changes...
        raise                    # ...and let the error continue upwards
    finally:
        conn.close()             # "finally" always runs, error or not


def get_db():
    """FastAPI dependency: one connection per request, committed at the end.

    Routers declare a parameter  db=Depends(get_db).  For each web request FastAPI
    calls get_db(), passes the yielded DB to the endpoint, and after the response
    runs the rest of this function: commit if all went well, roll back on an error.
    So one request = one transaction: it is saved completely or not at all.
    """
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
