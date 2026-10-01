import re
import time

import appointments
import database as db
import delivery
import home_services
import laboratory
import pharmacy
from common import BackendError, name_of, new_id, now, require_role

KENYAN_PHONE = re.compile(r"^(?:\+254|254|0)7\d{8}$")


class MockMpesa:
    """Pretend M-Pesa. Replace this class with the real STK push later; nothing else has to change."""

    def stk_push(self, phone, amount):
        return {"success": True, "reference": f"MPESA-{int(time.time() * 1000)}"}


gateway = MockMpesa()


def list_invoices(user):
    user = require_role(user, "patient", "admin")
    if user["role"] == "patient":
        rows = db.fetch_all("SELECT * FROM invoices WHERE patient_id = ? ORDER BY created_at DESC", (user["id"],))
    else:
        rows = db.fetch_all("SELECT * FROM invoices ORDER BY created_at DESC")
    for row in rows:
        row["patient_name"] = name_of(row["patient_id"])
    return rows


def pay_invoice(patient, invoice_id, phone):
    patient = require_role(patient, "patient")
    invoice = db.fetch_one("SELECT * FROM invoices WHERE id = ? AND patient_id = ?", (invoice_id, patient["id"]))
    if not invoice:
        raise BackendError("Invoice not found.")
    if invoice["status"] == "Paid":
        raise BackendError("This invoice is already paid.")
    if invoice["status"] != "Pending":
        raise BackendError("This invoice can no longer be paid.")
    clean_phone = re.sub(r"[\s-]", "", phone)
    if not KENYAN_PHONE.match(clean_phone):
        raise BackendError("Enter a valid Kenyan M-Pesa number, for example 0712345678.")

    result = gateway.stk_push(clean_phone, invoice["total"])
    if not result["success"]:
        raise BackendError("The payment was not completed. Please try again.")

    paid_at = now()
    db.update("invoices", invoice_id, {"status": "Paid", "payment_method": "M-Pesa Paybill",
                                       "reference": result["reference"], "paid_at": paid_at})
    db.insert("payments", {"id": new_id("payment"), "invoice_id": invoice_id, "patient_id": patient["id"],
                           "method": "M-Pesa Paybill", "phone": clean_phone, "reference": result["reference"],
                           "amount": invoice["total"], "status": "Completed", "created_at": paid_at})
    paid_invoice = db.fetch_one("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    handle_paid_invoice(paid_invoice)
    return paid_invoice


def handle_paid_invoice(invoice):
    """Each invoice type triggers the next step of its own workflow."""
    handlers = {
        "Consultation": appointments.on_invoice_paid,
        "Pharmacy": pharmacy.on_invoice_paid,
        "Delivery": delivery.on_invoice_paid,
        "Home Assessment": home_services.on_invoice_paid,
        "Home Service": home_services.on_invoice_paid,
        "Laboratory": laboratory.on_invoice_paid,
    }
    handlers[invoice["type"]](invoice)
