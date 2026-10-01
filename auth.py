import secrets

import config

import database as db
from common import BackendError, check_password, hash_password, new_id, now, public_user, require_role, get_user

LOGIN_CODE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
MIN_PASSWORD_LENGTH = 6


def _check_new_password(password, confirm):
    if password != confirm:
        raise BackendError("The passwords do not match.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise BackendError(f"The password must be at least {MIN_PASSWORD_LENGTH} characters.")


def register_patient(name, email, phone, address, password, confirm):
    name, email, phone, address = name.strip(), email.strip().lower(), phone.strip(), address.strip()
    if not (name and email and phone and address):
        raise BackendError("Please fill in all the fields.")
    if "@" not in email:
        raise BackendError("Enter a valid email address.")
    _check_new_password(password, confirm)
    if db.fetch_one("SELECT id FROM users WHERE email = ?", (email,)):
        raise BackendError("An account with this email already exists.")

    user = {
        "id": new_id("patient"), "name": name, "email": email, "phone": phone, "address": address,
        "password_hash": hash_password(password), "role": "patient", "enabled": 1, "created_at": now(),
    }
    db.insert("users", user)
    return public_user(get_user(user["id"]))


def login(email, password):
    """Returns {"status": "ok" | "change_password_required", "user": {...}}."""
    user = db.fetch_one("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
    if not user or not check_password(password, user["password_hash"]):
        raise BackendError("Invalid email or password.")
    if not user["enabled"]:
        raise BackendError("This account has been disabled. Please contact the administrator.")
    status = "change_password_required" if user["must_change_password"] else "ok"
    return {"status": status, "user": public_user(user)}


def set_first_password(user_id, new_password, confirm):
    """Used after a first sign-in with an administrator login code."""
    user = get_user(user_id)
    if not user or not user["must_change_password"]:
        raise BackendError("A password change is not required for this account.")
    _check_new_password(new_password, confirm)
    db.update("users", user_id, {"password_hash": hash_password(new_password), "must_change_password": 0})
    return public_user(get_user(user_id))


def reset_password(email, phone, new_password, confirm):
    """Demo-only reset using email + phone. A real system should send a code by SMS or email."""
    user = db.fetch_one("SELECT * FROM users WHERE email = ? AND phone = ?", (email.strip().lower(), phone.strip()))
    if not user:
        raise BackendError("No account matched that email and phone number.")
    _check_new_password(new_password, confirm)
    db.update("users", user["id"], {"password_hash": hash_password(new_password), "must_change_password": 0})


def update_profile(user, name, phone, address):
    user = require_role(user, *config.ROLES)
    if not name.strip():
        raise BackendError("Name cannot be empty.")
    db.update("users", user["id"], {"name": name.strip(), "phone": phone.strip(), "address": address.strip()})
    return public_user(get_user(user["id"]))


def generate_login_code():
    return "".join(secrets.choice(LOGIN_CODE_LETTERS) for _ in range(8))
