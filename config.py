import os

DB_PATH = os.environ.get("BEACON_DB", "beacon_hospital.db")

HOSPITAL = {
    "name": "Beacon of Hope Hospital",
    "phone": "0720876123",
    "email": "hospital@beaconafrica.org",
    "location": "Ongata Rongai, Beacon of Hope Centre, Off Magadi Rd, Along Gataka Rd",
}

ROLES = ["patient", "doctor", "nurse", "pharmacist", "rider", "admin"]

OPEN_MINUTES = 8 * 60
CLOSE_MINUTES = 17 * 60
SUNDAY = 6
APPOINTMENT_MINUTES = 45
DEFAULT_MAX_BOOKINGS = 10

APPOINTMENT_TYPES = ["Video Consultation", "Audio Consultation", "Physical Hospital Visit"]
PHYSICAL_VISIT = "Physical Hospital Visit"
SPECIALTIES = ["Clinical Provider", "General Consultation", "Telemedicine Follow-up"]

CONSULT_CATEGORY = "Telemedicine / Consultation"
HOME_CATEGORY = "Home Service"
HOME_ASSESSMENT_FEE = 1500

HOME_TRANSPORT = {
    "0": ("0-5 km (included)", 0),
    "300": ("6-10 km", 300),
    "500": ("11-15 km", 500),
    "quotation": ("Beyond 15 km (quotation)", 0),
}

LAB_TESTS = [
    {"name": "Complete Blood Count (CBC)", "price": 500},
    {"name": "Blood Sugar", "price": 300},
    {"name": "Malaria Test", "price": 300},
    {"name": "Urinalysis", "price": 300},
    {"name": "Liver Function Test", "price": 1200},
    {"name": "Kidney Function Test", "price": 1200},
    {"name": "Lipid Profile", "price": 1000},
    {"name": "Pregnancy Test", "price": 300},
]

DEFAULT_SERVICES = [
    {"id": "svc_consult_followup", "category": CONSULT_CATEGORY, "name": "Consultation fee/follow-up fee (15-30 minutes)",
     "description": "Telemedicine consultation or follow-up with a clinical provider.", "price": 500, "price_label": "KES 500"},
    {"id": "svc_bp_glucose", "category": CONSULT_CATEGORY, "name": "Telemedicine + review of home BP/glucose readings",
     "description": "Virtual consultation including review of home blood pressure or glucose readings.", "price": 500, "price_label": "KES 500-750"},
    {"id": "svc_physio_virtual", "category": CONSULT_CATEGORY, "name": "Physiotherapy virtual follow-up",
     "description": "Virtual physiotherapy follow-up consultation.", "price": 750, "price_label": "KES 750"},
    {"id": "svc_nursing_virtual", "category": CONSULT_CATEGORY, "name": "Nursing/caregiver virtual consultation",
     "description": "Virtual nursing or caregiver consultation.", "price": 500, "price_label": "KES 500"},
    {"id": "home_ncd_monitoring", "category": HOME_CATEGORY, "name": "NCD Home Monitoring & Follow-up",
     "description": "Nurse/clinician visit; BP; blood sugar where indicated; medication review; lifestyle counselling.", "price": 1500, "price_label": "KES 1,500"},
    {"id": "home_nursing_chronic", "category": HOME_CATEGORY, "name": "Home Nursing & Chronic Care",
     "description": "Nursing assessment; vital signs; medication support; basic nursing care; caregiver education.", "price": 2000, "price_label": "KES 2,000"},
    {"id": "home_mobility_rehab", "category": HOME_CATEGORY, "name": "Mobility & Rehabilitation Support",
     "description": "Physiotherapy/mobility assessment; exercises; falls-risk assessment; caregiver guidance.", "price": 2000, "price_label": "KES 2,000"},
    {"id": "home_post_hospital", "category": HOME_CATEGORY, "name": "Post-Hospital/Post-Procedure Home Care",
     "description": "Clinical review; wound/recovery assessment; vital signs; medication review; referral where needed.", "price": 2000, "price_label": "KES 2,000"},
    {"id": "home_elderly_dependent", "category": HOME_CATEGORY, "name": "Elderly & Dependent Patient Care",
     "description": "Nursing assessment; mobility support; vital signs; caregiver education; care-plan follow-up.", "price": 2500, "price_label": "KES 2,500"},
]

DEFAULT_DELIVERY_BANDS = [
    {"id": "delivery_0_3", "label": "0-3 km", "max_km": 3, "fee": 100},
    {"id": "delivery_3_5", "label": "3.1-5 km", "max_km": 5, "fee": 150},
    {"id": "delivery_5_10", "label": "5.1-10 km", "max_km": 10, "fee": 250},
    {"id": "delivery_10_15", "label": "10.1-15 km", "max_km": 15, "fee": 350},
    {"id": "delivery_15_20", "label": "15.1-20 km", "max_km": 20, "fee": 450},
    {"id": "delivery_20_25", "label": "20.1-25 km", "max_km": 25, "fee": 550},
    {"id": "delivery_25_30", "label": "25.1-30 km", "max_km": 30, "fee": 650},
    {"id": "delivery_above_30", "label": "Above 30 km (KES 20 per km, quoted before dispatch)",
     "max_km": None, "fee": 0, "per_km": 20, "quotation": True},
]

DEMO_PASSWORD = "Demo@2026"

DEMO_USERS = [
    {"id": "admin_boniface", "name": "Boniface Machogu", "email": "boniface@beaconafrica.org", "role": "admin", "phone": "0724741827"},
    {"id": "doctor_eunice", "name": "Eunice Wanjiku Ngugi", "email": "eunice.ngugi@beaconhope.demo", "role": "doctor", "phone": "0700000101", "specialty": "Clinical Provider"},
    {"id": "doctor_george", "name": "George Keitany", "email": "george.keitany@beaconhope.demo", "role": "doctor", "phone": "0700000102", "specialty": "Clinical Provider"},
    {"id": "doctor_benard", "name": "Benard Onyinsi", "email": "benard.onyinsi@beaconhope.demo", "role": "doctor", "phone": "0700000103", "specialty": "Clinical Provider"},
    {"id": "doctor_angela", "name": "Angela Mwangi", "email": "angela.mwangi@beaconhope.demo", "role": "doctor", "phone": "0700000104", "specialty": "Clinical Provider"},
    {"id": "nurse_beatrice", "name": "Beatrice Gitamo", "email": "beatrice.gitamo@beaconhope.demo", "role": "nurse", "phone": "0700000201"},
    {"id": "nurse_gerald", "name": "Gerald Ragira", "email": "gerald.ragira@beaconhope.demo", "role": "nurse", "phone": "0700000202"},
    {"id": "nurse_dennis", "name": "Dennis Onami", "email": "dennis.onami@beaconhope.demo", "role": "nurse", "phone": "0700000203"},
    {"id": "nurse_caroline", "name": "Caroline Wanjiku", "email": "caroline.wanjiku@beaconhope.demo", "role": "nurse", "phone": "0700000204"},
    {"id": "pharmacist_peter", "name": "Peter Miano", "email": "peter.miano@beaconhope.demo", "role": "pharmacist", "phone": "0700000301"},
    {"id": "pharmacist_rajab", "name": "Rajab Ziada", "email": "rajab.ziada@beaconhope.demo", "role": "pharmacist", "phone": "0700000302"},
    {"id": "rider_dancan", "name": "Dancan Bande", "email": "dancan.bande@beaconhope.demo", "role": "rider", "phone": "0700000401", "vehicle": "Motorbike"},
    {"id": "patient1", "name": "Demo Patient", "email": "patient@beaconhope.demo", "role": "patient", "phone": "0700000005", "address": "Rongai, Nairobi"},
]

DEMO_MEDICINES = [
    {"id": "med1", "name": "Amoxicillin 500mg", "price": 25, "quantity": 100, "expiry": "2027-12-31"},
    {"id": "med2", "name": "Paracetamol 500mg", "price": 10, "quantity": 200, "expiry": "2027-12-31"},
    {"id": "med3", "name": "Cetirizine 10mg", "price": 20, "quantity": 80, "expiry": "2027-12-31"},
]

ASSISTANT_MAX_QUESTIONS = 3
