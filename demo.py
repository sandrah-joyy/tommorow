"""Runs the whole hospital journey from start to finish. Use it for the presentation: python demo.py"""
import os
from datetime import date, timedelta

import admin
import appointments
import assistant
import auth
import billing
import config
import delivery
import home_services
import laboratory
import pharmacy
from common import BackendError, list_notifications, patient_status
from seed import setup_database

PAY_PHONE = "0712345678"


def step(title):
    print(f"\n=== {title}")


def show(label, value):
    print(f"  {label}: {value}")


def should_fail(label, function, *args, **kwargs):
    try:
        function(*args, **kwargs)
    except BackendError as error:
        show(f"{label} -> blocked", error)
    else:
        raise SystemExit(f"Expected '{label}' to be blocked, but it worked.")


def next_weekday(weekday):
    day = date.today() + timedelta(days=1)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day.isoformat()


def sign_in(email, password=config.DEMO_PASSWORD):
    return auth.login(email, password)["user"]


def main():
    config.DB_PATH = "demo_run.db"
    if os.path.exists(config.DB_PATH):
        os.remove(config.DB_PATH)
    setup_database()

    patient = sign_in("patient@beaconhope.demo")
    doctor = sign_in("eunice.ngugi@beaconhope.demo")
    nurse = sign_in("beatrice.gitamo@beaconhope.demo")
    pharmacist = sign_in("peter.miano@beaconhope.demo")
    rider = sign_in("dancan.bande@beaconhope.demo")
    boss = sign_in("boniface@beaconafrica.org")

    monday, tuesday, sunday = next_weekday(0), next_weekday(1), next_weekday(6)

    step("1. Accounts and sign-in")
    should_fail("wrong password", auth.login, "patient@beaconhope.demo", "not-the-password")
    amina = auth.register_patient("Amina Otieno", "amina@example.com", "0722000111", "Rongai", "secret1", "secret1")
    show("new patient registered", amina["name"])
    show("Demo Patient status", patient_status(patient["id"]))

    step("2. Booking rules (Monday to Saturday, 08:00-17:00, 45-minute slots)")
    should_fail("Sunday booking", appointments.book_appointment, patient, "doctor_eunice", sunday, "09:00", "Video Consultation", "svc_consult_followup")
    should_fail("6 PM booking", appointments.book_appointment, patient, "doctor_eunice", monday, "18:00", "Video Consultation", "svc_consult_followup")
    booking = appointments.book_appointment(patient, "doctor_eunice", monday, "09:00", "Video Consultation", "svc_consult_followup")
    show("appointment", f"{booking['appointment']['date']} {booking['appointment']['time']}-{booking['appointment']['end_time']}")
    show("invoice", f"{booking['invoice']['number']} total KES {booking['invoice']['total']:,.0f}")
    amina_user = sign_in("amina@example.com", "secret1")
    should_fail("overlapping slot", appointments.book_appointment, amina_user, "doctor_eunice", monday, "09:30", "Video Consultation", "svc_consult_followup")
    show("doctors free at 09:30", [d["name"] for d in appointments.list_doctors(monday, "09:30") if d["available"]])

    step("3. Payment (mock M-Pesa) and consultation")
    should_fail("bad phone number", billing.pay_invoice, patient, booking["invoice"]["id"], "12345")
    billing.pay_invoice(patient, booking["invoice"]["id"], PAY_PHONE)
    appointment_id = booking["appointment"]["id"]
    show("status after payment", appointments.list_appointments(patient)[0]["status"])
    appointments.join_consultation(patient, appointment_id)
    appointments.save_clinical_notes(doctor, appointment_id, "BP 150/95. Review medication adherence.")
    appointments.end_consultation(doctor, appointment_id)
    show("Demo Patient status now", patient_status(patient["id"]))

    step("4. Prescription -> pharmacy -> medicine invoice")
    should_fail("patient writing a prescription", pharmacy.create_prescription, patient, patient["id"], [{"medicine_name": "Amoxicillin 500mg", "quantity": 1}])
    created = pharmacy.create_prescription(doctor, patient["id"], [
        {"medicine_name": "Amoxicillin 500mg", "quantity": 10, "dosage": "500mg", "frequency": "3x daily", "duration": "5 days"},
        {"medicine_name": "Paracetamol 500mg", "quantity": 20, "dosage": "500mg", "frequency": "as needed", "duration": "5 days"}],
        appointment_id)
    order_id = created["order"]["id"]
    checked = pharmacy.process_order(pharmacist, order_id)
    show("stock available", checked["available"])
    show("medicine invoice", f"KES {checked['invoice']['total']:,.0f}")
    show("Amoxicillin stock left", [m["quantity"] for m in pharmacy.list_inventory(pharmacist) if m["name"].startswith("Amox")][0])
    billing.pay_invoice(patient, checked["invoice"]["id"], PAY_PHONE)

    step("5. Delivery: details -> delivery fee -> rider -> OTP")
    delivery_id = delivery.list_deliveries(pharmacist)[0]["id"]
    show("status after medicine paid", delivery.list_deliveries(pharmacist)[0]["status"])
    suggestion = delivery.suggest_fee(4.2)
    show("tariff for 4.2 km", suggestion)
    updated = delivery.confirm_details(pharmacist, delivery_id, "Rongai, Gataka Rd", "Blue gate after the chemist", "0712345678", suggestion["band_id"])
    show("delivery fee", f"KES {updated['fee']:,.0f}")
    delivery_invoice = [i for i in billing.list_invoices(patient) if i["type"] == "Delivery"][0]
    should_fail("dispatch before paying the delivery fee", delivery.assign_rider, pharmacist, delivery_id, "rider_dancan")
    billing.pay_invoice(patient, delivery_invoice["id"], PAY_PHONE)
    delivery.assign_rider(pharmacist, delivery_id, "rider_dancan")

    rider_view = delivery.list_deliveries(rider)[0]
    show("what the rider can see", sorted(rider_view))
    should_fail("rider reading prescriptions", pharmacy.list_prescriptions, rider)
    otp = delivery.list_deliveries(patient)[0]["otp"]
    delivery.rider_pick_up(rider, delivery_id)
    should_fail("starting without calling the receiver", delivery.rider_confirm_location, rider, delivery_id, False)
    delivery.rider_confirm_location(rider, delivery_id, True)
    should_fail("wrong delivery code", delivery.rider_mark_delivered, rider, delivery_id, "0000")
    delivery.rider_mark_delivered(rider, delivery_id, otp)
    show("final order status", pharmacy.list_orders(patient)[0]["status"])
    should_fail("refill above stock", pharmacy.request_refill, patient, "med3", 500)
    refill = pharmacy.request_refill(patient, "med3", 5, "Monthly allergy refill")
    show("refill invoice", f"KES {pharmacy.process_order(pharmacist, refill['id'])['invoice']['total']:,.0f}")

    step("6. Laboratory")
    lab = laboratory.request_test(doctor, patient["id"], "Blood Sugar", "Fasting")
    billing.pay_invoice(patient, lab["invoice"]["id"], PAY_PHONE)
    laboratory.save_result(doctor, lab["request"]["id"], "Completed", "Fasting glucose 6.2 mmol/L")
    show("patient sees", laboratory.list_requests(patient)[0]["result"])

    step("7. Home care: assessment first for new clients")
    should_fail("home service before assessment", home_services.request_service, amina_user, "home_ncd_monitoring", "nurse_beatrice", tuesday, "10:00", "Rongai", "0")
    assessment = home_services.request_assessment(amina_user, "nurse_beatrice", tuesday, "10:00", "Rongai, Nairobi", "Hypertension follow-up at home")
    should_fail("same nurse, same time", home_services.request_service, patient, "home_ncd_monitoring", "nurse_beatrice", tuesday, "10:00", "Rongai", "0")
    billing.pay_invoice(amina_user, assessment["invoice"]["id"], PAY_PHONE)
    home_services.save_assessment_outcome(nurse, assessment["request"]["id"], "approved", "Stable. Suitable for home monitoring.")
    service = home_services.request_service(amina_user, "home_ncd_monitoring", "nurse_beatrice", next_weekday(2), "11:00", "Rongai, Nairobi", "300")
    show("home service total", f"KES {service['request']['total']:,.0f}")
    billing.pay_invoice(amina_user, service["invoice"]["id"], PAY_PHONE)
    home_services.update_status(nurse, service["request"]["id"], "Completed")

    step("8. Administrator")
    created = admin.add_user(boss, "Lucy Wambui", "lucy.wambui@beaconhope.demo", "0700000205", "nurse")
    show("login code for new nurse", created["login_code"])
    first = auth.login("lucy.wambui@beaconhope.demo", created["login_code"])
    show("first sign-in", first["status"])
    auth.set_first_password(created["user"]["id"], "MyOwnPass1", "MyOwnPass1")
    show("second sign-in", auth.login("lucy.wambui@beaconhope.demo", "MyOwnPass1")["status"])
    should_fail("patient opening admin reports", admin.generate_report, patient, "financial")
    report = admin.generate_report(boss, "financial")
    show("report", f"{report['title']}: {len(report['rows'])} invoices, paid KES {report['summary']['paid_total']:,.0f}")
    show("dashboard", admin.dashboard_summary(boss))
    show("CSV starts with", admin.report_to_csv(report).splitlines()[0])

    step("9. Notifications and service assistant")
    show("patient notifications", len(list_notifications(patient)))
    show("assistant", assistant.reply("How does medicine delivery work?"))

    print("\nDemo finished: every step worked and every rule blocked what it should.")


if __name__ == "__main__":
    main()
