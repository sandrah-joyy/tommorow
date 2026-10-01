from datetime import date

import database as db
import delivery
from common import BackendError, create_invoice, name_of, new_id, notify, notify_role, now, require_role, today


def _clean_items(items):
    if not items:
        raise BackendError("Add at least one medicine.")
    cleaned = []
    for item in items:
        name = str(item.get("medicine_name", "")).strip()
        try:
            quantity = int(item.get("quantity", 0))
        except (TypeError, ValueError):
            quantity = 0
        if not name or quantity < 1:
            raise BackendError("Each medicine needs a name and a quantity of at least 1.")
        cleaned.append({"medicine_name": name, "quantity": quantity, "dosage": item.get("dosage", ""),
                        "frequency": item.get("frequency", ""), "duration": item.get("duration", "")})
    return cleaned


def create_prescription(doctor, patient_id, items, appointment_id=None):
    doctor = require_role(doctor, "doctor")
    patient = db.fetch_one("SELECT id FROM users WHERE id = ? AND role = 'patient'", (patient_id,))
    if not patient:
        raise BackendError("Patient not found.")
    if appointment_id and not db.fetch_one(
            "SELECT id FROM appointments WHERE id = ? AND doctor_id = ? AND patient_id = ?",
            (appointment_id, doctor["id"], patient_id)):
        raise BackendError("That appointment does not belong to this doctor and patient.")
    items = _clean_items(items)

    prescription = {"id": new_id("prescription"), "patient_id": patient_id, "doctor_id": doctor["id"],
                    "appointment_id": appointment_id, "items": items, "created_at": now()}
    db.insert("prescriptions", prescription)
    order = {"id": new_id("pharmacy"), "prescription_id": prescription["id"], "patient_id": patient_id,
             "type": "Prescription", "items": items, "status": "Pending", "created_at": now()}
    db.insert("pharmacy_orders", order)

    notify(patient_id, "Your prescription has been sent to the pharmacy.")
    notify_role("pharmacist", f"New pharmacy order {order['id']} is waiting for stock processing.")
    return {"prescription": prescription, "order": order}


def request_refill(patient, medicine_id, quantity, note=""):
    """Repeat medicine for ongoing conditions. No consultation fee: only medicine and delivery are charged."""
    patient = require_role(patient, "patient")
    medicine = db.fetch_one("SELECT * FROM inventory WHERE id = ?", (medicine_id,))
    if not medicine or quantity < 1 or medicine["quantity"] < quantity or medicine["expiry"] < today():
        raise BackendError("The selected quantity is not available.")

    order = {"id": new_id("refill"), "patient_id": patient["id"], "type": "NCD Refill",
             "items": [{"medicine_name": medicine["name"], "quantity": quantity, "dosage": "As previously prescribed",
                        "frequency": "As previously prescribed", "duration": "Refill"}],
             "status": "Pending", "note": note, "created_at": now()}
    db.insert("pharmacy_orders", order)
    notify(patient["id"], "Your medicine refill request has been sent to the pharmacy.")
    notify_role("pharmacist", f"New refill request {order['id']} needs stock processing.")
    notify_role("admin", f"REFILL: {patient['name']} submitted refill request {order['id']}.", "booking")
    return order


def _stock_problems(items):
    needed = {}
    for item in items:
        key = item["medicine_name"].lower()
        needed[key] = needed.get(key, 0) + item["quantity"]
    problems = []
    for name, quantity in needed.items():
        medicine = db.fetch_one("SELECT * FROM inventory WHERE lower(name) = ?", (name,))
        if not medicine:
            problems.append(f"{name} is not stocked")
        elif medicine["expiry"] < today():
            problems.append(f"{medicine['name']} has expired")
        elif medicine["quantity"] < quantity:
            problems.append(f"{medicine['name']}: only {medicine['quantity']} left")
    return needed, problems


def process_order(pharmacist, order_id):
    """Checks stock. If everything is available, reserves it and sends the medicine invoice to the patient."""
    require_role(pharmacist, "pharmacist")
    order = db.fetch_one("SELECT * FROM pharmacy_orders WHERE id = ?", (order_id,))
    if not order:
        raise BackendError("Order not found.")
    if order["status"] not in ("Pending", "Unavailable"):
        raise BackendError("This order has already been processed.")

    needed, problems = _stock_problems(order["items"])
    if problems:
        db.update("pharmacy_orders", order_id, {"status": "Unavailable"})
        notify(order["patient_id"], "One or more medicines in your order are currently unavailable.")
        return {"available": False, "problems": problems}

    invoice_items = []
    for item in order["items"]:
        medicine = db.fetch_one("SELECT * FROM inventory WHERE lower(name) = ?", (item["medicine_name"].lower(),))
        invoice_items.append({"description": medicine["name"], "quantity": item["quantity"],
                              "unit_price": medicine["price"]})
    for name, quantity in needed.items():
        db.execute("UPDATE inventory SET quantity = quantity - ? WHERE lower(name) = ?", (quantity, name))

    invoice = create_invoice("Pharmacy", "PHARM", order["patient_id"], order_id, invoice_items)
    db.update("pharmacy_orders", order_id, {"status": "Awaiting Pharmacy Payment"})
    notify(order["patient_id"], f"Pharmacy invoice {invoice['number']} is ready for payment.")
    return {"available": True, "invoice": invoice}


def on_invoice_paid(invoice):
    order = db.fetch_one("SELECT * FROM pharmacy_orders WHERE id = ?", (invoice["related_id"],))
    if order:
        delivery.create_for_order(order)


def list_orders(user):
    user = require_role(user, "patient", "pharmacist", "admin")
    if user["role"] == "patient":
        rows = db.fetch_all("SELECT * FROM pharmacy_orders WHERE patient_id = ? ORDER BY created_at DESC", (user["id"],))
    else:
        rows = db.fetch_all("SELECT * FROM pharmacy_orders ORDER BY created_at DESC")
    for row in rows:
        row["patient_name"] = name_of(row["patient_id"])
        found = db.fetch_one("SELECT id, status FROM deliveries WHERE order_id = ?", (row["id"],))
        row["delivery_id"] = found["id"] if found else None
        row["delivery_status"] = found["status"] if found else None
    return rows


def list_prescriptions(user):
    user = require_role(user, "doctor", "pharmacist", "admin")
    if user["role"] == "doctor":
        rows = db.fetch_all("SELECT * FROM prescriptions WHERE doctor_id = ? ORDER BY created_at DESC", (user["id"],))
    else:
        rows = db.fetch_all("SELECT * FROM prescriptions ORDER BY created_at DESC")
    for row in rows:
        row["patient_name"] = name_of(row["patient_id"])
        row["doctor_name"] = name_of(row["doctor_id"])
        order = db.fetch_one("SELECT status FROM pharmacy_orders WHERE prescription_id = ?", (row["id"],))
        row["pharmacy_status"] = order["status"] if order else "-"
    return rows


def list_inventory(user):
    require_role(user, "pharmacist", "admin")
    return db.fetch_all("SELECT * FROM inventory ORDER BY name")


def add_medicine(user, name, price, quantity, expiry):
    """Adds a new medicine. If the name already exists, the quantity is added to the stock."""
    require_role(user, "pharmacist", "admin")
    name = name.strip()
    if not name or price < 0 or quantity < 0:
        raise BackendError("Enter a medicine name, a valid price and a valid quantity.")
    try:
        date.fromisoformat(expiry)
    except ValueError:
        raise BackendError("Enter the expiry date as YYYY-MM-DD.")
    existing = db.fetch_one("SELECT * FROM inventory WHERE lower(name) = ?", (name.lower(),))
    if existing:
        db.update("inventory", existing["id"],
                  {"quantity": existing["quantity"] + quantity, "price": price, "expiry": expiry})
        return db.fetch_one("SELECT * FROM inventory WHERE id = ?", (existing["id"],))
    medicine = {"id": new_id("medicine"), "name": name, "price": price, "quantity": quantity, "expiry": expiry}
    db.insert("inventory", medicine)
    return medicine
