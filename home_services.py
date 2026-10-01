import config
import database as db
from common import (BackendError, check_booking_window, create_invoice, get_user, name_of, new_id, notify,
                    notify_role, now, patient_status, require_role)

FINISHED = ("Cancelled", "Completed", "Not Suitable")
STATUS_CHOICES = ["Paid - Awaiting Assignment", "Assigned", "In Progress", "Completed"]


def can_book_directly(patient_id):
    """Returning clients, and new clients whose home assessment was approved, can book home services."""
    patient = get_user(patient_id)
    if not patient or patient["role"] != "patient":
        return False
    return patient_status(patient_id) == "Returning Client" or patient["home_assessment_status"] == "approved"


def provider_is_busy(provider_id, date, time):
    return bool(db.fetch_one(
        "SELECT id FROM home_services WHERE provider_id = ? AND date = ? AND time = ? "
        "AND status NOT IN ('Cancelled', 'Completed')", (provider_id, date, time)))


def list_providers(date=None, time=None):
    nurses = db.fetch_all("SELECT id, name, phone FROM users WHERE role = 'nurse' AND enabled = 1")
    for nurse in nurses:
        nurse["available"] = not (date and time and provider_is_busy(nurse["id"], date, time))
    return nurses


def _check_provider(provider_id, date, time):
    nurse = db.fetch_one("SELECT id FROM users WHERE id = ? AND role = 'nurse' AND enabled = 1", (provider_id,))
    if not nurse:
        raise BackendError("Please choose a nursing officer.")
    if provider_is_busy(provider_id, date, time):
        raise BackendError("That nursing officer is already busy at the selected time. Choose another officer or time.")


def request_assessment(patient, provider_id, date, time, address, reason):
    """New clients pay for a home assessment first. The nurse decides if home care is suitable."""
    patient = require_role(patient, "patient")
    if patient_status(patient["id"]) == "Returning Client":
        raise BackendError("You are a returning client. You can request a home service directly.")
    if not (address.strip() and reason.strip()):
        raise BackendError("Please enter the address and the reason for the assessment.")
    check_booking_window(date, time)
    _check_provider(provider_id, date, time)
    active = db.fetch_one(
        "SELECT id FROM home_services WHERE patient_id = ? AND request_type = 'assessment' "
        "AND status NOT IN ('Cancelled', 'Completed', 'Not Suitable')", (patient["id"],))
    if active:
        raise BackendError("You already have an active home assessment request.")

    fee = db.get_setting("home_assessment_fee", config.HOME_ASSESSMENT_FEE)
    request = {"id": new_id("assessment"), "patient_id": patient["id"], "provider_id": provider_id,
               "request_type": "assessment", "service": "Home Assessment", "date": date, "time": time,
               "address": address, "service_fee": fee, "transport_fee": 0, "total": fee, "notes": reason,
               "status": "Pending Payment", "created_at": now()}
    db.insert("home_services", request)
    invoice = create_invoice("Home Assessment", "ASSESS", patient["id"], request["id"],
                             [{"description": "Home Assessment", "quantity": 1, "unit_price": fee}])
    db.update("home_services", request["id"], {"invoice_id": invoice["id"]})
    db.update("users", patient["id"], {"home_assessment_status": "paid_pending"})
    notify_role("admin", f"New Home Assessment request {request['id']} from {patient['name']}.")
    notify(provider_id, f"A new Home Assessment has been requested for {date} at {time}.")
    return {"request": request, "invoice": invoice}


def request_service(patient, service_id, provider_id, date, time, address, transport_option, notes=""):
    patient = require_role(patient, "patient")
    if not can_book_directly(patient["id"]):
        raise BackendError("A home assessment is required before you can request a home service.")
    service = db.fetch_one("SELECT * FROM services WHERE id = ? AND category = ? AND active = 1",
                           (service_id, config.HOME_CATEGORY))
    if not service:
        raise BackendError("Choose a home service.")
    if transport_option not in config.HOME_TRANSPORT:
        raise BackendError("Choose a transport fee option.")
    if not address.strip():
        raise BackendError("Enter the home address.")
    check_booking_window(date, time)
    _check_provider(provider_id, date, time)

    transport_label, transport_fee = config.HOME_TRANSPORT[transport_option]
    is_quotation = transport_option == "quotation"
    request = {"id": new_id("home"), "patient_id": patient["id"], "provider_id": provider_id,
               "request_type": "service", "service": service["name"], "date": date, "time": time,
               "address": address, "service_fee": service["price"], "transport_fee": transport_fee,
               "transport_quotation": int(is_quotation), "total": service["price"] + transport_fee,
               "notes": notes, "status": "Pending Payment", "created_at": now()}
    db.insert("home_services", request)
    invoice = create_invoice("Home Service", "HOME", patient["id"], request["id"], [
        {"description": service["name"], "quantity": 1, "unit_price": service["price"]},
        {"description": "Transport - quotation based on distance" if is_quotation else f"Transport ({transport_label})",
         "quantity": 1, "unit_price": transport_fee}])
    db.update("home_services", request["id"], {"invoice_id": invoice["id"]})
    notify_role("admin", f"New home service request {request['id']} needs payment/processing.")
    return {"request": request, "invoice": invoice}


def on_invoice_paid(invoice):
    request = db.fetch_one("SELECT * FROM home_services WHERE id = ?", (invoice["related_id"],))
    if not request:
        return
    if request["request_type"] == "assessment":
        db.update("home_services", request["id"], {"status": "Paid - Awaiting Assessment"})
        notify(request["patient_id"], "Assessment payment received. Your nursing officer will visit at the scheduled time.")
        notify(request["provider_id"], f"Home Assessment {request['id']} has been paid. Please complete the assessment.")
        notify_role("admin", f"Home Assessment {request['id']} has been paid and is awaiting assessment.")
    else:
        db.update("home_services", request["id"], {"status": "Paid - Awaiting Assignment"})
        notify_role("admin", f"Home service {request['id']} has been paid and is ready for assignment.")


def save_assessment_outcome(user, request_id, outcome, notes):
    user = require_role(user, "nurse", "admin")
    request = db.fetch_one("SELECT * FROM home_services WHERE id = ? AND request_type = 'assessment'", (request_id,))
    if not request:
        raise BackendError("Assessment not found.")
    if user["role"] == "nurse" and request["provider_id"] != user["id"]:
        raise BackendError("This assessment is assigned to another nursing officer.")
    if request["status"] != "Paid - Awaiting Assessment":
        raise BackendError("The assessment must be paid before it can be completed.")
    if outcome not in ("approved", "completed_not_suitable"):
        raise BackendError("Choose an assessment outcome.")
    if not notes.strip():
        raise BackendError("Enter the assessment notes.")

    db.update("home_services", request_id, {
        "status": "Completed" if outcome == "approved" else "Not Suitable", "assessment_notes": notes})
    db.update("users", request["patient_id"], {"home_assessment_status": outcome})
    if outcome == "approved":
        notify(request["patient_id"], "Your Home Assessment is complete. Home care is approved and you may now request a home service.")
    else:
        notify(request["patient_id"], "Your Home Assessment is complete. The nursing officer advises that you attend "
                                      "Beacon of Hope Hospital for further assessment or treatment.")


def update_status(user, request_id, status):
    user = require_role(user, "nurse", "admin")
    request = db.fetch_one("SELECT * FROM home_services WHERE id = ? AND request_type = 'service'", (request_id,))
    if not request:
        raise BackendError("Home service request not found.")
    if user["role"] == "nurse" and request["provider_id"] != user["id"]:
        raise BackendError("This request is assigned to another nursing officer.")
    if status not in STATUS_CHOICES:
        raise BackendError("Choose a valid status.")
    if request["status"] == "Pending Payment":
        raise BackendError("The patient has not paid for this service yet.")
    db.update("home_services", request_id, {"status": status})
    notify(request["patient_id"], f"Your home service '{request['service']}' status is now {status}.")


def list_requests(user):
    user = require_role(user, "patient", "nurse", "admin")
    if user["role"] == "patient":
        rows = db.fetch_all("SELECT * FROM home_services WHERE patient_id = ? ORDER BY created_at DESC", (user["id"],))
    elif user["role"] == "nurse":
        rows = db.fetch_all("SELECT * FROM home_services WHERE provider_id = ? ORDER BY created_at DESC", (user["id"],))
    else:
        rows = db.fetch_all("SELECT * FROM home_services ORDER BY created_at DESC")
    for row in rows:
        patient = get_user(row["patient_id"])
        row["patient_name"] = patient["name"]
        row["patient_phone"] = patient["phone"]
        row["provider_name"] = name_of(row["provider_id"])
    return rows
