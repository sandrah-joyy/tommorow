import secrets

import database as db
from common import BackendError, create_invoice, get_user, name_of, new_id, notify, notify_role, now, require_role

RIDER_FIELDS = ("id", "status", "patient_name", "receiver_phone", "location", "directions",
                "assigned_at", "picked_up_at", "started_at", "delivered_at")


def delivery_bands():
    return db.get_setting("delivery_bands")


def suggest_fee(distance_km):
    """Finds the tariff band for a distance. Above 30 km the fee is a quotation (per km)."""
    for band in delivery_bands():
        if band["max_km"] is not None and distance_km <= band["max_km"]:
            return {"band_id": band["id"], "fee": band["fee"], "is_quotation": False}
    band = next(b for b in delivery_bands() if b.get("quotation"))
    return {"band_id": band["id"], "fee": round(distance_km * band["per_km"]), "is_quotation": True}


def create_for_order(order):
    """Called when the medicine invoice is paid."""
    if db.fetch_one("SELECT id FROM deliveries WHERE order_id = ?", (order["id"],)):
        return
    patient = get_user(order["patient_id"])
    db.insert("deliveries", {
        "id": new_id("delivery"), "order_id": order["id"], "patient_id": order["patient_id"],
        "status": "Awaiting Delivery Details", "receiver_phone": patient["phone"], "fee": 0,
        "payment_status": "Pending", "created_at": now()})
    db.update("pharmacy_orders", order["id"], {"status": "Awaiting Delivery Details"})
    notify(order["patient_id"], "Medicine payment received. The pharmacy will call you to confirm your delivery location and delivery fee.")
    notify_role("pharmacist", f"MEDICINE PAID: Order {order['id']}. Call {patient['name']} to confirm the delivery "
                              "location, directions, receiver phone and delivery fee.")


def confirm_details(pharmacist, delivery_id, location, directions, receiver_phone, band_id, fee=None):
    """Pharmacist records what the patient said on the phone. This creates the delivery invoice."""
    pharmacist = require_role(pharmacist, "pharmacist")
    delivery = db.fetch_one("SELECT * FROM deliveries WHERE id = ?", (delivery_id,))
    if not delivery:
        raise BackendError("Delivery not found.")
    if delivery["status"] not in ("Awaiting Delivery Details", "Awaiting Delivery Payment"):
        raise BackendError("The delivery details can no longer be changed.")
    location, directions, receiver_phone = location.strip(), directions.strip(), receiver_phone.strip()
    if not (location and directions and receiver_phone):
        raise BackendError("Enter the confirmed location, directions and receiver phone.")

    band = next((b for b in delivery_bands() if b["id"] == band_id), None)
    if not band:
        raise BackendError("Choose a delivery charge band.")
    if fee is None:
        if band.get("quotation"):
            raise BackendError("Above 30 km the delivery fee is a quotation. Enter the agreed amount.")
        fee = band["fee"]
    if fee <= 0:
        raise BackendError("Enter a valid delivery fee.")

    items = [{"description": "Medicine delivery", "quantity": 1, "unit_price": fee}]
    invoice = db.fetch_one("SELECT * FROM invoices WHERE id = ?", (delivery["invoice_id"],)) if delivery["invoice_id"] else None
    if invoice:
        db.update("invoices", invoice["id"], {"items": items, "total": fee})
    else:
        invoice = create_invoice("Delivery", "DEL", delivery["patient_id"], delivery_id, items)

    db.update("deliveries", delivery_id, {
        "location": location, "directions": directions, "receiver_phone": receiver_phone, "fee": fee,
        "charge_band": band_id, "is_quotation": int(bool(band.get("quotation"))),
        "status": "Awaiting Delivery Payment", "invoice_id": invoice["id"], "confirmed_by": pharmacist["id"]})
    db.update("pharmacy_orders", delivery["order_id"], {"status": "Awaiting Delivery Payment"})
    notify(delivery["patient_id"], f"Delivery invoice {invoice['number']} is ready. Delivery fee: KES {fee:,.0f}. "
                                   "Please pay it before dispatch.")
    return db.fetch_one("SELECT * FROM deliveries WHERE id = ?", (delivery_id,))


def on_invoice_paid(invoice):
    """Called when the delivery invoice is paid. The order is now ready for the pharmacist to dispatch."""
    delivery = db.fetch_one("SELECT * FROM deliveries WHERE id = ?", (invoice["related_id"],))
    if not delivery:
        return
    db.update("deliveries", delivery["id"], {"payment_status": "Paid", "status": "Paid - Awaiting Dispatch"})
    db.update("pharmacy_orders", delivery["order_id"], {"status": "Paid - Awaiting Pharmacist Dispatch"})
    notify_role("pharmacist", f"DELIVERY PAID: Order {delivery['order_id']} is ready for rider assignment.")
    notify_role("admin", f"DELIVERY PAID: Order {delivery['order_id']} is ready for dispatch.")


def assign_rider(pharmacist, delivery_id, rider_id):
    require_role(pharmacist, "pharmacist")
    delivery = db.fetch_one("SELECT * FROM deliveries WHERE id = ?", (delivery_id,))
    if not delivery:
        raise BackendError("Delivery not found.")
    if delivery["payment_status"] != "Paid" or delivery["status"] != "Paid - Awaiting Dispatch":
        raise BackendError("The delivery fee must be paid before the pharmacy can dispatch this order.")
    rider = db.fetch_one("SELECT * FROM users WHERE id = ? AND role = 'rider' AND enabled = 1", (rider_id,))
    if not rider:
        raise BackendError("Choose an available rider.")

    otp = f"{secrets.randbelow(10000):04d}"
    db.update("deliveries", delivery_id, {"rider_id": rider_id, "status": "Assigned", "otp": otp, "assigned_at": now()})
    db.update("pharmacy_orders", delivery["order_id"], {"status": "Dispatched - Rider Assigned"})

    notify(rider_id, f"DELIVERY ASSIGNED: Pick up the parcel from the pharmacy, then call the receiver on "
                     f"{delivery['receiver_phone']} to confirm the exact location.")
    notify(delivery["patient_id"], f"Your medicine order has been dispatched to rider {rider['name']}. "
                                   f"Your delivery code is {otp}. Give it to the rider only when you receive the parcel.")
    notify_role("admin", f"Pharmacy dispatched order {delivery['order_id']} to rider {rider['name']}.")


def _rider_delivery(rider, delivery_id, expected_status, wrong_status_message):
    rider = require_role(rider, "rider")
    delivery = db.fetch_one("SELECT * FROM deliveries WHERE id = ? AND rider_id = ?", (delivery_id, rider["id"]))
    if not delivery:
        raise BackendError("You are not authorised to update this delivery.")
    if delivery["status"] != expected_status:
        raise BackendError(wrong_status_message)
    return delivery


def rider_pick_up(rider, delivery_id):
    delivery = _rider_delivery(rider, delivery_id, "Assigned", "This delivery is not waiting for pickup.")
    db.update("deliveries", delivery_id, {"status": "Picked Up - Call Receiver", "picked_up_at": now()})
    db.update("pharmacy_orders", delivery["order_id"], {"status": "Picked Up - Call Receiver"})
    notify(delivery["patient_id"], "The rider has picked up your medicine and will call you to confirm the exact location.")


def rider_confirm_location(rider, delivery_id, spoke_to_receiver):
    delivery = _rider_delivery(rider, delivery_id, "Picked Up - Call Receiver",
                               "Pick up the medicine before confirming the location.")
    if not spoke_to_receiver:
        raise BackendError("Call the receiver and confirm the location before starting the delivery.")
    db.update("deliveries", delivery_id, {"status": "In Transit", "started_at": now()})
    db.update("pharmacy_orders", delivery["order_id"], {"status": "In Transit"})
    notify(delivery["patient_id"], "The rider has confirmed your location by phone and is on the way.")


def rider_mark_delivered(rider, delivery_id, otp):
    delivery = _rider_delivery(rider, delivery_id, "In Transit", "The delivery must be in transit first.")
    if str(otp).strip() != delivery["otp"]:
        raise BackendError("Incorrect delivery code.")
    db.update("deliveries", delivery_id, {"status": "Delivered", "delivered_at": now()})
    db.update("pharmacy_orders", delivery["order_id"], {"status": "Completed - Delivered"})
    notify(delivery["patient_id"], "Your medicine has been delivered successfully.")


def list_deliveries(user):
    """Each role sees only what it needs. Riders never see medicines, fees or the delivery code."""
    user = require_role(user, "patient", "pharmacist", "rider", "admin")
    if user["role"] == "patient":
        rows = db.fetch_all("SELECT * FROM deliveries WHERE patient_id = ? ORDER BY created_at DESC", (user["id"],))
    elif user["role"] == "rider":
        rows = db.fetch_all("SELECT * FROM deliveries WHERE rider_id = ? ORDER BY created_at DESC", (user["id"],))
    else:
        rows = db.fetch_all("SELECT * FROM deliveries ORDER BY created_at DESC")

    result = []
    for row in rows:
        row["patient_name"] = name_of(row["patient_id"])
        row["rider_name"] = name_of(row["rider_id"])
        if user["role"] == "rider":
            row = {key: row[key] for key in RIDER_FIELDS}
        elif user["role"] != "patient":
            row.pop("otp")
        result.append(row)
    return result
