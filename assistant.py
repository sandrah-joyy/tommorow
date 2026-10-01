import re

import config

ANSWERS = [
    (("physical", "visit"),
     "Book a physical hospital visit from Appointments: choose Physical Hospital Visit, then a doctor, date and time, and pay the invoice."),
    (("telemedicine", "video", "audio"),
     "Telemedicine appointments are video or audio consultations. Once paid, a confirmed appointment appears under Consultation."),
    (("refill", "ncd", "diabetes", "hypertension"),
     "Patients on ongoing treatment can request a medicine refill without a consultation. You pay only for the medicine and the delivery."),
    (("lab", "test"),
     "Doctors request laboratory tests. You pay the invoice, and you can view the result here once it is completed."),
    (("home", "nurse", "nursing"),
     "New clients start with a Home Assessment. Returning clients and approved clients can request home services directly."),
    (("medicine", "pharmacy", "delivery", "rider"),
     "The pharmacy checks stock and you pay for the medicine. The pharmacist then calls you to confirm the delivery location and fee. "
     "After you pay the delivery fee, a rider is assigned and brings your medicine."),
    (("pay", "mpesa", "m-pesa", "invoice"),
     "Payments are made by M-Pesa from the Payments page. Each invoice is paid separately."),
    (("hour", "open", "sunday", "closed"),
     "Services are available from 8:00 AM to 5:00 PM, Monday to Saturday. We are closed on Sundays."),
]

FALLBACK = (f"For anything else, please contact {config.HOSPITAL['name']} on {config.HOSPITAL['phone']} "
            f"or {config.HOSPITAL['email']}.")


def reply(question):
    words = re.findall(r"[a-z-]+", question.lower())
    for keywords, answer in ANSWERS:
        if any(word.startswith(keyword) for word in words for keyword in keywords):
            return answer
    return FALLBACK


def contact_details():
    return config.HOSPITAL
