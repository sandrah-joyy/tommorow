import config
import database as db
from common import (BackendError, check_booking_window, create_invoice, get_user, name_of, new_id,
                    notify, notify_role, now, require_role, to_minutes, to_time)


def overlaps(start1, end1, start2, end2):
    return start1 < end2 and end1 > start2


def doctor_appointments(doctor_id, date, skip_id=None):
    rows = db.fetch_all(
        "SELECT * FROM appointments WHERE doctor_id = ? AND date = ? AND status != 'Cancelled'", (doctor_id, date))
    return [row for row in rows if row["id"] != skip_id]


def doctor_max_bookings(doctor_id, date):
    special_day = db.fetch_one("SELECT max_bookings FROM doctor_schedules WHERE doctor_id = ? AND date = ?",
                               (doctor_id, date))
    if special_day:
        return special_day["max_bookings"]
    doctor = get_user(doctor_id)
    return (doctor and doctor["max_bookings_per_day"]) or config.DEFAULT_MAX_BOOKINGS


def slot_is_taken(appointments, start):
    end = start + config.APPOINTMENT_MINUTES
    return any(overlaps(start, end, to_minutes(a["time"]), to_minutes(a["end_time"])) for a in appointments)


def next_free_slot(doctor_id, date, time):
    start = to_minutes(time)
    for appointment in sorted(doctor_appointments(doctor_id, date), key=lambda a: a["time"]):
        if overlaps(start, start + config.APPOINTMENT_MINUTES,
                    to_minutes(appointment["time"]), to_minutes(appointment["end_time"])):
            start = to_minutes(appointment["end_time"])
    return to_time(start) if start <= config.CLOSE_MINUTES else None


def list_doctors(date=None, time=None, specialty=None):
    """Doctors with an 'available' flag for the chosen date and time."""
    doctors = db.fetch_all("SELECT id, name, specialty FROM users WHERE role = 'doctor' AND enabled = 1")
    if specialty:
        doctors = [d for d in doctors if d["specialty"] == specialty]
    for doctor in doctors:
        busy = bool(date and time) and slot_is_taken(doctor_appointments(doctor["id"], date), to_minutes(time))
        doctor["available"] = not busy
    return doctors


def book_appointment(patient, doctor_id, date, time, appointment_type, service_id, reason=""):
    patient = require_role(patient, "patient")
    if appointment_type not in config.APPOINTMENT_TYPES:
        raise BackendError("Choose a valid appointment type.")
    service = db.fetch_one("SELECT * FROM services WHERE id = ? AND category = ? AND active = 1",
                           (service_id, config.CONSULT_CATEGORY))
    if not service:
        raise BackendError("Please choose a consultation or follow-up service.")
    doctor = get_user(doctor_id)
    if not doctor or doctor["role"] != "doctor" or not doctor["enabled"]:
        raise BackendError("Doctor not found.")
    check_booking_window(date, time)

    start = to_minutes(time)
    doctor_day = doctor_appointments(doctor_id, date)
    if slot_is_taken(doctor_day, start):
        free = next_free_slot(doctor_id, date, time)
        hint = f"Next available start: {free}." if free else "No later slot is available that day."
        raise BackendError(f"This doctor is busy at that time. {hint}")
    limit = doctor_max_bookings(doctor_id, date)
    if len(doctor_day) >= limit:
        raise BackendError(f"This doctor has reached the maximum of {limit} bookings for {date}.")
    patient_day = db.fetch_all(
        "SELECT * FROM appointments WHERE patient_id = ? AND date = ? AND status != 'Cancelled'", (patient["id"], date))
    if slot_is_taken(patient_day, start):
        raise BackendError("You already have another appointment at this time.")

    appointment = {
        "id": new_id("appointment"), "patient_id": patient["id"], "doctor_id": doctor_id,
        "specialty": doctor["specialty"], "date": date, "time": time,
        "end_time": to_time(start + config.APPOINTMENT_MINUTES), "type": appointment_type,
        "service": service["name"], "fee": service["price"], "reason": reason,
        "status": "Pending Payment", "payment_status": "Unpaid", "created_at": now(),
    }
    db.insert("appointments", appointment)

    prefix = "PHYS" if appointment_type == config.PHYSICAL_VISIT else "CONS"
    invoice = create_invoice("Consultation", prefix, patient["id"], appointment["id"], [
        {"description": f"{service['name']} - {doctor['specialty']}", "quantity": 1, "unit_price": service["price"]}])

    notify(patient["id"], f"{appointment_type} booked for {date} at {time}. Please pay invoice {invoice['number']}.")
    notify(doctor_id, f"New {appointment_type.lower()} booking request for {date} at {time}.")
    notify_role("admin", f"NEW BOOKING: {patient['name']} booked {appointment_type} for {date} at {time} with {doctor['name']}.", "booking")
    return {"appointment": appointment, "invoice": invoice}


def reschedule_appointment(patient, appointment_id, new_date, new_time):
    patient = require_role(patient, "patient")
    appointment = db.fetch_one("SELECT * FROM appointments WHERE id = ? AND patient_id = ?",
                               (appointment_id, patient["id"]))
    if not appointment:
        raise BackendError("Appointment not found.")
    if appointment["status"] in ("Completed", "Cancelled"):
        raise BackendError("This appointment can no longer be rescheduled.")
    check_booking_window(new_date, new_time)
    if (new_date, new_time) <= (appointment["date"], appointment["time"]):
        raise BackendError("Please choose a later date and time than the current appointment.")

    start = to_minutes(new_time)
    if slot_is_taken(doctor_appointments(appointment["doctor_id"], new_date, skip_id=appointment_id), start):
        raise BackendError("The doctor is already booked for that time.")

    db.update("appointments", appointment_id, {
        "date": new_date, "time": new_time, "end_time": to_time(start + config.APPOINTMENT_MINUTES),
        "rescheduled_at": now()})
    notify(appointment["doctor_id"], f"Appointment rescheduled to {new_date} at {new_time}.")
    notify_role("admin", f"APPOINTMENT RESCHEDULED: {patient['name']}'s appointment is now {new_date} at {new_time}.", "booking")
    return db.fetch_one("SELECT * FROM appointments WHERE id = ?", (appointment_id,))


def list_appointments(user):
    user = require_role(user, "patient", "doctor", "admin")
    if user["role"] == "patient":
        rows = db.fetch_all("SELECT * FROM appointments WHERE patient_id = ? ORDER BY date, time", (user["id"],))
    elif user["role"] == "doctor":
        rows = db.fetch_all("SELECT * FROM appointments WHERE doctor_id = ? ORDER BY date, time", (user["id"],))
    else:
        rows = db.fetch_all("SELECT * FROM appointments ORDER BY date, time")
    for row in rows:
        row["patient_name"] = name_of(row["patient_id"])
        row["doctor_name"] = name_of(row["doctor_id"])
    return rows


def on_invoice_paid(invoice):
    appointment = db.fetch_one("SELECT * FROM appointments WHERE id = ?", (invoice["related_id"],))
    if not appointment:
        return
    db.update("appointments", appointment["id"],
              {"status": "Confirmed", "payment_status": "Paid", "paid_at": invoice["paid_at"]})
    notify(appointment["patient_id"], "Payment received. Your appointment is confirmed.")
    notify(appointment["doctor_id"], f"Appointment confirmed for {appointment['date']} at {appointment['time']}.")


def set_default_capacity(doctor, max_bookings, specialty=None):
    doctor = require_role(doctor, "doctor")
    if max_bookings < 1:
        raise BackendError("Capacity must be at least 1.")
    changes = {"max_bookings_per_day": max_bookings}
    if specialty:
        if specialty not in config.SPECIALTIES:
            raise BackendError("Choose a valid specialty.")
        changes["specialty"] = specialty
    db.update("users", doctor["id"], changes)


def set_date_capacity(doctor, date, max_bookings):
    doctor = require_role(doctor, "doctor")
    if max_bookings < 1:
        raise BackendError("Capacity must be at least 1.")
    existing = db.fetch_one("SELECT id FROM doctor_schedules WHERE doctor_id = ? AND date = ?", (doctor["id"], date))
    if existing:
        db.update("doctor_schedules", existing["id"], {"max_bookings": max_bookings})
    else:
        db.insert("doctor_schedules", {"id": new_id("schedule"), "doctor_id": doctor["id"],
                                       "date": date, "max_bookings": max_bookings})


def _my_appointment(user, appointment_id):
    appointment = db.fetch_one("SELECT * FROM appointments WHERE id = ?", (appointment_id,))
    if not appointment or user["id"] not in (appointment["patient_id"], appointment["doctor_id"]):
        raise BackendError("Appointment not found.")
    return appointment


def join_consultation(user, appointment_id):
    user = require_role(user, "patient", "doctor")
    appointment = _my_appointment(user, appointment_id)
    if appointment["status"] != "Confirmed" or appointment["type"] == config.PHYSICAL_VISIT:
        raise BackendError("This telemedicine consultation has not been confirmed.")
    record = db.fetch_one("SELECT * FROM consultations WHERE appointment_id = ?", (appointment_id,))
    return {"appointment": appointment, "minutes_allowed": config.APPOINTMENT_MINUTES,
            "clinical_notes": record["clinical_notes"] if record else ""}


def _consultation_record(appointment):
    record = db.fetch_one("SELECT * FROM consultations WHERE appointment_id = ?", (appointment["id"],))
    if record:
        return record
    record = {"id": new_id("consultation"), "appointment_id": appointment["id"],
              "patient_id": appointment["patient_id"], "doctor_id": appointment["doctor_id"],
              "clinical_notes": "", "created_at": now()}
    db.insert("consultations", record)
    return record


def save_clinical_notes(doctor, appointment_id, notes):
    doctor = require_role(doctor, "doctor")
    appointment = _my_appointment(doctor, appointment_id)
    if appointment["status"] != "Confirmed":
        raise BackendError("Notes can only be saved for a confirmed consultation.")
    record = _consultation_record(appointment)
    db.update("consultations", record["id"], {"clinical_notes": notes})
    notify(appointment["patient_id"], "Your doctor has updated the clinical notes for your consultation.")


def end_consultation(user, appointment_id):
    user = require_role(user, "patient", "doctor")
    appointment = _my_appointment(user, appointment_id)
    if appointment["status"] != "Confirmed":
        raise BackendError("Only a confirmed consultation can be ended.")
    record = _consultation_record(appointment)
    db.update("consultations", record["id"], {"ended_at": now()})
    db.update("appointments", appointment_id, {"status": "Completed"})
    notify(appointment["patient_id"], "Your consultation has ended. A prescription may now be processed by the pharmacy.")
    return db.fetch_one("SELECT * FROM appointments WHERE id = ?", (appointment_id,))
