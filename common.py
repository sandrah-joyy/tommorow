import hashlib
import hmac
import secrets
import uuid
from datetime import date, datetime

import config
import database as db


class BackendError(Exception):
    """A normal problem the user can understand: bad input, not allowed, not found."""


def new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def now():
    return datetime.now().isoformat(timespec="seconds")


def today():
    return date.today().isoformat()


def money(amount):
    return f"KES {amount:,.0f}"


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000)
    return f"{salt}${digest.hex()}"


def check_password(password, stored):
    salt, digest = stored.split("$")
    test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000)
    return hmac.compare_digest(test.hex(), digest)


def get_user(user_id):
    return db.fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))


def name_of(user_id):
    user = get_user(user_id) if user_id else None
    return user["name"] if user else "-"


def public_user(user):
    return {key: value for key, value in user.items() if key != "password_hash"}


def require_role(user, *roles):
    """Re-reads the user from the database so a changed role or disabled account takes effect at once."""
    if not user:
        raise BackendError("Please sign in first.")
    fresh = get_user(user["id"])
    if not fresh or not fresh["enabled"]:
        raise BackendError("This account is not active.")
    if fresh["role"] not in roles:
        raise BackendError("You are not allowed to do this.")
    return fresh


def to_minutes(time_text):
    try:
        hours, minutes = time_text.split(":")
        return int(hours) * 60 + int(minutes)
    except (ValueError, AttributeError):
        raise BackendError("Enter the time as HH:MM, for example 09:30.")


def to_time(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def check_booking_window(date_text, time_text):
    """Every bookable service: Monday to Saturday, start time between 08:00 and 17:00."""
    try:
        day = date.fromisoformat(date_text)
    except (ValueError, TypeError):
        raise BackendError("Enter the date as YYYY-MM-DD.")
    if day < date.today():
        raise BackendError("You cannot book a date in the past.")
    if day.weekday() == config.SUNDAY:
        raise BackendError("There are no services on Sunday. Please choose Monday to Saturday.")
    minutes = to_minutes(time_text)
    if not config.OPEN_MINUTES <= minutes <= config.CLOSE_MINUTES:
        raise BackendError("Services are available from 8:00 AM to 5:00 PM, Monday to Saturday.")
    now_time = datetime.now()
    if day == date.today() and minutes < now_time.hour * 60 + now_time.minute:
        raise BackendError("That time has already passed today.")


def create_invoice(kind, prefix, patient_id, related_id, items):
    invoice = {
        "id": new_id("invoice"),
        "number": f"{prefix}-{secrets.token_hex(3).upper()}",
        "type": kind,
        "patient_id": patient_id,
        "related_id": related_id,
        "items": items,
        "total": sum(item["quantity"] * item["unit_price"] for item in items),
        "status": "Pending",
        "created_at": now(),
    }
    db.insert("invoices", invoice)
    return invoice


def notify(user_id, message, kind="info"):
    db.insert("notifications", {
        "id": new_id("note"), "user_id": user_id, "message": message,
        "kind": kind, "is_read": 0, "created_at": now(),
    })


def notify_role(role, message, kind="info"):
    for user in db.fetch_all("SELECT id FROM users WHERE role = ? AND enabled = 1", (role,)):
        notify(user["id"], message, kind)


def list_notifications(user):
    user = require_role(user, *config.ROLES)
    return db.fetch_all("SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC", (user["id"],))


def mark_notifications_read(user):
    user = require_role(user, *config.ROLES)
    db.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user["id"],))


def patient_status(patient_id):
    """New Client or Returning Client, based on completed hospital care."""
    patient = get_user(patient_id)
    if not patient or patient["role"] != "patient":
        return "Not a patient"
    if patient["patient_status_override"] == "returning":
        return "Returning Client"
    if patient["patient_status_override"] == "new":
        return "New Client"
    finished_visit = db.fetch_one(
        "SELECT 1 AS found FROM appointments WHERE patient_id = ? AND status = 'Completed'", (patient_id,))
    finished_consultation = db.fetch_one(
        "SELECT 1 AS found FROM consultations WHERE patient_id = ? AND ended_at IS NOT NULL", (patient_id,))
    finished_home_care = db.fetch_one(
        "SELECT 1 AS found FROM home_services WHERE patient_id = ? AND status = 'Completed' "
        "AND request_type != 'assessment'", (patient_id,))
    if finished_visit or finished_consultation or finished_home_care:
        return "Returning Client"
    return "New Client"
