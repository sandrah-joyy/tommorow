import config
import database as db
from common import hash_password, now


def setup_database():
    """Creates the tables and, on the first run only, fills in demo data."""
    db.init_db()
    if db.fetch_one("SELECT id FROM users LIMIT 1"):
        return

    password_hash = hash_password(config.DEMO_PASSWORD)
    for demo in config.DEMO_USERS:
        db.insert("users", {
            **demo,
            "password_hash": password_hash,
            "enabled": 1,
            "max_bookings_per_day": config.DEFAULT_MAX_BOOKINGS if demo["role"] == "doctor" else None,
            "created_at": now(),
        })

    for medicine in config.DEMO_MEDICINES:
        db.insert("inventory", medicine)

    for service in config.DEFAULT_SERVICES:
        db.insert("services", {**service, "active": 1})

    db.set_setting("delivery_bands", config.DEFAULT_DELIVERY_BANDS)
    db.set_setting("home_assessment_fee", config.HOME_ASSESSMENT_FEE)
