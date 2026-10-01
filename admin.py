import csv
import io

import config
import database as db
from auth import generate_login_code
from common import BackendError, hash_password, new_id, notify, now, patient_status, public_user, require_role, get_user, name_of


def list_users(admin):
    require_role(admin, "admin")
    users = db.fetch_all("SELECT * FROM users ORDER BY role, name")
    for user in users:
        user["patient_status"] = patient_status(user["id"]) if user["role"] == "patient" else None
    return [public_user(user) for user in users]


def add_user(admin, name, email, phone, role, address="", specialty=None, vehicle=None):
    """Creates an account with a one-time login code. The user must set their own password at first sign-in."""
    require_role(admin, "admin")
    email = email.strip().lower()
    if not name.strip() or "@" not in email:
        raise BackendError("Enter a name and a valid email address.")
    if role not in config.ROLES:
        raise BackendError("Choose a valid role.")
    if db.fetch_one("SELECT id FROM users WHERE email = ?", (email,)):
        raise BackendError("That email already exists.")
    if role == "doctor" and specialty not in config.SPECIALTIES:
        raise BackendError("Choose a specialty for the doctor.")

    login_code = generate_login_code()
    user = {"id": new_id(role), "name": name.strip(), "email": email, "phone": phone.strip(), "address": address,
            "password_hash": hash_password(login_code), "must_change_password": 1, "role": role, "enabled": 1,
            "specialty": specialty if role == "doctor" else None,
            "max_bookings_per_day": config.DEFAULT_MAX_BOOKINGS if role == "doctor" else None,
            "vehicle": vehicle if role == "rider" else None, "created_at": now()}
    db.insert("users", user)
    notify(user["id"], "Welcome to Beacon of Hope Hospital. Sign in with your email and the login code from the administrator.")
    return {"user": public_user(get_user(user["id"])), "login_code": login_code}


def regenerate_login_code(admin, user_id):
    require_role(admin, "admin")
    if not get_user(user_id):
        raise BackendError("User not found.")
    login_code = generate_login_code()
    db.update("users", user_id, {"password_hash": hash_password(login_code), "must_change_password": 1})
    return login_code


def toggle_user(admin, user_id):
    admin = require_role(admin, "admin")
    user = get_user(user_id)
    if not user:
        raise BackendError("User not found.")
    if user["id"] == admin["id"]:
        raise BackendError("You cannot disable your own administrator account.")
    db.update("users", user_id, {"enabled": 0 if user["enabled"] else 1})
    return not user["enabled"]


def toggle_returning_client(admin, patient_id):
    """Admin confirms a patient already has a hospital record, so they count as a Returning Client."""
    require_role(admin, "admin")
    patient = get_user(patient_id)
    if not patient or patient["role"] != "patient":
        raise BackendError("Patient not found.")
    new_value = None if patient["patient_status_override"] == "returning" else "returning"
    db.update("users", patient_id, {"patient_status_override": new_value})
    return patient_status(patient_id)


def list_services(category=None, include_removed=False):
    sql, params = "SELECT * FROM services WHERE 1 = 1", []
    if category:
        sql += " AND category = ?"
        params.append(category)
    if not include_removed:
        sql += " AND active = 1"
    return db.fetch_all(sql + " ORDER BY category, name", tuple(params))


def save_service(admin, category, name, description, price, price_label=None, service_id=None):
    """Adds a new service, or edits one when service_id is given."""
    require_role(admin, "admin")
    if category not in (config.CONSULT_CATEGORY, config.HOME_CATEGORY):
        raise BackendError("Choose a valid service category.")
    if not (name.strip() and description.strip()) or price < 0:
        raise BackendError("Enter a service name, a description and a valid charge.")
    label = price_label or f"KES {price:,.0f}"

    if service_id:
        if not db.fetch_one("SELECT id FROM services WHERE id = ?", (service_id,)):
            raise BackendError("Service not found.")
        db.update("services", service_id, {"category": category, "name": name.strip(), "description": description.strip(),
                                           "price": price, "price_label": label, "active": 1})
        return service_id
    if db.fetch_one("SELECT id FROM services WHERE lower(name) = ? AND active = 1", (name.strip().lower(),)):
        raise BackendError("A service with this name already exists.")
    service_id = new_id("service")
    db.insert("services", {"id": service_id, "category": category, "name": name.strip(),
                           "description": description.strip(), "price": price, "price_label": label, "active": 1})
    return service_id


def toggle_service(admin, service_id):
    """Remove or restore a service. Existing bookings are not changed."""
    require_role(admin, "admin")
    service = db.fetch_one("SELECT * FROM services WHERE id = ?", (service_id,))
    if not service:
        raise BackendError("Service not found.")
    db.update("services", service_id, {"active": 0 if service["active"] else 1})


def save_charges(admin, band_fees, per_km, assessment_fee):
    """band_fees is a dict like {"delivery_0_3": 100, ...}. per_km is the rate above 30 km."""
    require_role(admin, "admin")
    if per_km < 0 or assessment_fee < 0 or any(fee < 0 for fee in band_fees.values()):
        raise BackendError("Enter valid amounts (zero or more).")
    bands = db.get_setting("delivery_bands")
    for band in bands:
        if band.get("quotation"):
            band["per_km"] = per_km
        elif band["id"] in band_fees:
            band["fee"] = band_fees[band["id"]]
    db.set_setting("delivery_bands", bands)
    db.set_setting("home_assessment_fee", assessment_fee)


REPORT_TYPES = ["financial", "appointments", "pharmacy", "deliveries", "home-services", "laboratory", "users"]


def _in_range(text, start, end):
    day = (text or "")[:10]
    return not ((start and day < start) or (end and day > end))


def generate_report(admin, report_type, start=None, end=None):
    """Returns {"title", "columns", "rows", "summary"}. start and end are optional YYYY-MM-DD dates."""
    require_role(admin, "admin")
    if report_type not in REPORT_TYPES:
        raise BackendError("Choose a valid report type.")

    summary = None
    if report_type == "financial":
        invoices = [i for i in db.fetch_all("SELECT * FROM invoices ORDER BY created_at") if _in_range(i["created_at"], start, end)]
        columns = ["Invoice", "Type", "Patient", "Total (KES)", "Status", "Created"]
        rows = [[i["number"], i["type"], name_of(i["patient_id"]), i["total"], i["status"], i["created_at"]] for i in invoices]
        paid = [i for i in invoices if i["status"] == "Paid"]
        summary = {"paid_invoices": len(paid), "paid_total": sum(i["total"] for i in paid)}
    elif report_type == "appointments":
        found = [a for a in db.fetch_all("SELECT * FROM appointments ORDER BY date, time") if _in_range(a["date"], start, end)]
        columns = ["Date", "Time", "Patient", "Doctor", "Type", "Status"]
        rows = [[a["date"], a["time"], name_of(a["patient_id"]), name_of(a["doctor_id"]), a["type"], a["status"]] for a in found]
    elif report_type == "pharmacy":
        found = [o for o in db.fetch_all("SELECT * FROM pharmacy_orders ORDER BY created_at") if _in_range(o["created_at"], start, end)]
        columns = ["Order", "Patient", "Type", "Medicines", "Status"]
        rows = [[o["id"], name_of(o["patient_id"]), o["type"],
                 ", ".join(f"{i['medicine_name']} x{i['quantity']}" for i in o["items"]), o["status"]] for o in found]
    elif report_type == "deliveries":
        found = [d for d in db.fetch_all("SELECT * FROM deliveries ORDER BY created_at") if _in_range(d["created_at"], start, end)]
        columns = ["Delivery", "Order", "Patient", "Rider", "Fee (KES)", "Status"]
        rows = [[d["id"], d["order_id"], name_of(d["patient_id"]), name_of(d["rider_id"]), d["fee"], d["status"]] for d in found]
    elif report_type == "home-services":
        found = [h for h in db.fetch_all("SELECT * FROM home_services ORDER BY created_at") if _in_range(h["created_at"], start, end)]
        columns = ["Request", "Patient", "Service", "Date", "Total (KES)", "Status"]
        rows = [[h["id"], name_of(h["patient_id"]), h["service"], h["date"], h["total"], h["status"]] for h in found]
    elif report_type == "laboratory":
        found = [l for l in db.fetch_all("SELECT * FROM lab_requests ORDER BY created_at") if _in_range(l["created_at"], start, end)]
        columns = ["Request", "Patient", "Test", "Status"]
        rows = [[l["id"], name_of(l["patient_id"]), l["test_name"], l["status"]] for l in found]
    else:
        columns = ["Name", "Email", "Role", "Specialty", "Account"]
        rows = [[u["name"], u["email"], u["role"], u["specialty"] or "-", "Enabled" if u["enabled"] else "Disabled"]
                for u in db.fetch_all("SELECT * FROM users ORDER BY role, name")]

    return {"title": report_type.replace("-", " ").title() + " Report", "columns": columns, "rows": rows, "summary": summary}


def report_to_csv(report):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(report["columns"])
    writer.writerows(report["rows"])
    return buffer.getvalue()


def dashboard_summary(admin):
    require_role(admin, "admin")
    paid = db.fetch_all("SELECT type, SUM(total) AS total, COUNT(*) AS count FROM invoices WHERE status = 'Paid' GROUP BY type")
    return {
        "revenue_by_type": {row["type"]: row["total"] for row in paid},
        "total_revenue": sum(row["total"] for row in paid),
        "patients": db.fetch_one("SELECT COUNT(*) AS n FROM users WHERE role = 'patient'")["n"],
        "appointments_today": db.fetch_one("SELECT COUNT(*) AS n FROM appointments WHERE date = date('now', 'localtime')")["n"],
        "orders_waiting_for_pharmacy": db.fetch_one("SELECT COUNT(*) AS n FROM pharmacy_orders WHERE status = 'Pending'")["n"],
        "deliveries_in_progress": db.fetch_one(
            "SELECT COUNT(*) AS n FROM deliveries WHERE status NOT IN ('Delivered', 'Awaiting Delivery Details')")["n"],
    }
