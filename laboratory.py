import config
import database as db
from common import BackendError, create_invoice, name_of, new_id, notify, notify_role, now, require_role


def list_tests():
    return config.LAB_TESTS


def request_test(doctor, patient_id, test_name, notes=""):
    """Only doctors request tests. The patient receives the invoice and pays before the lab works on it."""
    doctor = require_role(doctor, "doctor")
    if not db.fetch_one("SELECT id FROM users WHERE id = ? AND role = 'patient'", (patient_id,)):
        raise BackendError("Patient not found.")
    test = next((t for t in config.LAB_TESTS if t["name"] == test_name), None)
    if not test:
        raise BackendError("Choose a laboratory test from the list.")

    request = {"id": new_id("lab"), "patient_id": patient_id, "doctor_id": doctor["id"], "test_name": test_name,
               "notes": notes, "status": "Requested", "created_at": now()}
    db.insert("lab_requests", request)
    invoice = create_invoice("Laboratory", "LAB", patient_id, request["id"],
                             [{"description": test_name, "quantity": 1, "unit_price": test["price"]}])
    db.update("lab_requests", request["id"], {"invoice_id": invoice["id"]})
    notify(patient_id, f"Your doctor requested a {test_name}. Please pay invoice {invoice['number']}.")
    notify_role("admin", f"New laboratory request {request['id']}.")
    return {"request": request, "invoice": invoice}


def on_invoice_paid(invoice):
    request = db.fetch_one("SELECT * FROM lab_requests WHERE id = ?", (invoice["related_id"],))
    if not request:
        return
    db.update("lab_requests", request["id"], {"status": "Paid - Processing"})
    notify(request["doctor_id"], f"Laboratory request {request['id']} has been paid and is ready to process.")
    notify_role("admin", f"Laboratory request {request['id']} has been paid.")


def save_result(doctor, request_id, status, result):
    doctor = require_role(doctor, "doctor")
    request = db.fetch_one("SELECT * FROM lab_requests WHERE id = ?", (request_id,))
    if not request:
        raise BackendError("Laboratory request not found.")
    if request["status"] == "Requested":
        raise BackendError("The patient has not paid for this test yet.")
    if status not in ("Processing", "Completed"):
        raise BackendError("Choose Processing or Completed.")
    db.update("lab_requests", request_id, {"status": status, "result": result, "result_date": now()})
    notify(request["patient_id"], f"Your laboratory request {request_id} has been updated.")


def list_requests(user):
    """Patients only see their own requests, and a result only once the test is Completed."""
    user = require_role(user, "patient", "doctor", "admin")
    if user["role"] == "patient":
        rows = db.fetch_all("SELECT * FROM lab_requests WHERE patient_id = ? ORDER BY created_at DESC", (user["id"],))
        for row in rows:
            if row["status"] != "Completed":
                row["result"] = None
    else:
        rows = db.fetch_all("SELECT * FROM lab_requests ORDER BY created_at DESC")
    for row in rows:
        row["patient_name"] = name_of(row["patient_id"])
    return rows
