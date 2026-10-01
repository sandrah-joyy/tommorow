import json
import sqlite3
from contextlib import closing

import config

JSON_COLUMNS = ("items",)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY, name TEXT, email TEXT UNIQUE, password_hash TEXT, role TEXT,
    phone TEXT, address TEXT, enabled INTEGER DEFAULT 1, specialty TEXT,
    max_bookings_per_day INTEGER, vehicle TEXT, must_change_password INTEGER DEFAULT 0,
    patient_status_override TEXT, home_assessment_status TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS appointments (
    id TEXT PRIMARY KEY, patient_id TEXT, doctor_id TEXT, specialty TEXT, date TEXT, time TEXT,
    end_time TEXT, type TEXT, service TEXT, fee REAL, reason TEXT, status TEXT,
    payment_status TEXT, paid_at TEXT, rescheduled_at TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS consultations (
    id TEXT PRIMARY KEY, appointment_id TEXT, patient_id TEXT, doctor_id TEXT,
    clinical_notes TEXT, ended_at TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS prescriptions (
    id TEXT PRIMARY KEY, patient_id TEXT, doctor_id TEXT, appointment_id TEXT,
    items TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS pharmacy_orders (
    id TEXT PRIMARY KEY, prescription_id TEXT, patient_id TEXT, type TEXT,
    items TEXT, status TEXT, note TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS inventory (
    id TEXT PRIMARY KEY, name TEXT UNIQUE, price REAL, quantity INTEGER, expiry TEXT
);
CREATE TABLE IF NOT EXISTS invoices (
    id TEXT PRIMARY KEY, number TEXT, type TEXT, patient_id TEXT, related_id TEXT,
    items TEXT, total REAL, status TEXT, payment_method TEXT, reference TEXT,
    paid_at TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS payments (
    id TEXT PRIMARY KEY, invoice_id TEXT, patient_id TEXT, method TEXT, phone TEXT,
    reference TEXT, amount REAL, status TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS deliveries (
    id TEXT PRIMARY KEY, order_id TEXT, patient_id TEXT, rider_id TEXT, status TEXT,
    location TEXT, directions TEXT, receiver_phone TEXT, fee REAL, charge_band TEXT,
    is_quotation INTEGER DEFAULT 0, payment_status TEXT, otp TEXT, invoice_id TEXT,
    confirmed_by TEXT, created_at TEXT, assigned_at TEXT, picked_up_at TEXT,
    started_at TEXT, delivered_at TEXT
);
CREATE TABLE IF NOT EXISTS lab_requests (
    id TEXT PRIMARY KEY, patient_id TEXT, doctor_id TEXT, test_name TEXT, notes TEXT,
    status TEXT, result TEXT, invoice_id TEXT, created_at TEXT, result_date TEXT
);
CREATE TABLE IF NOT EXISTS home_services (
    id TEXT PRIMARY KEY, patient_id TEXT, provider_id TEXT, request_type TEXT, service TEXT,
    date TEXT, time TEXT, address TEXT, service_fee REAL, transport_fee REAL,
    transport_quotation INTEGER DEFAULT 0, total REAL, notes TEXT, status TEXT,
    invoice_id TEXT, assessment_notes TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY, user_id TEXT, message TEXT, kind TEXT, is_read INTEGER DEFAULT 0,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS doctor_schedules (
    id TEXT PRIMARY KEY, doctor_id TEXT, date TEXT, max_bookings INTEGER
);
CREATE TABLE IF NOT EXISTS services (
    id TEXT PRIMARY KEY, category TEXT, name TEXT, description TEXT, price REAL,
    price_label TEXT, active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
"""


def connect():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(connect()) as conn:
        with conn:
            conn.executescript(SCHEMA)


def _to_dict(row):
    data = dict(row)
    for column in JSON_COLUMNS:
        if isinstance(data.get(column), str):
            data[column] = json.loads(data[column])
    return data


def _prepare(values):
    return {key: json.dumps(v) if isinstance(v, (list, dict)) else v for key, v in values.items()}


def fetch_all(sql, params=()):
    with closing(connect()) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_to_dict(row) for row in rows]


def fetch_one(sql, params=()):
    rows = fetch_all(sql, params)
    return rows[0] if rows else None


def execute(sql, params=()):
    with closing(connect()) as conn:
        with conn:
            conn.execute(sql, params)


def insert(table, values):
    values = _prepare(values)
    columns = ", ".join(values)
    marks = ", ".join("?" * len(values))
    execute(f"INSERT INTO {table} ({columns}) VALUES ({marks})", tuple(values.values()))


def update(table, row_id, changes):
    changes = _prepare(changes)
    assignments = ", ".join(f"{column} = ?" for column in changes)
    execute(f"UPDATE {table} SET {assignments} WHERE id = ?", (*changes.values(), row_id))


def get_setting(key, default=None):
    row = fetch_one("SELECT value FROM settings WHERE key = ?", (key,))
    return json.loads(row["value"]) if row else default


def set_setting(key, value):
    execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, json.dumps(value)))
