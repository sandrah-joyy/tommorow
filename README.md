# Beacon of Hope Hospital - Backend (Python + SQLite)

Plain Python, no extra libraries. Run the full demo:

    python demo.py

All demo accounts use the password in `config.py` (`DEMO_PASSWORD`). Demo emails are listed in `DEMO_USERS`.

## Files

| File | What it does |
|---|---|
| `config.py` | Fees, opening hours, service list, delivery tariff, demo users |
| `database.py` | SQLite tables and four small helpers: `fetch_all`, `fetch_one`, `insert`, `update` |
| `common.py` | Shared tools: errors, passwords, role check, booking hours, invoices, notifications |
| `seed.py` | Creates the tables and demo data on the first run |
| `auth.py` | Register, login, first-time password, reset, profile |
| `appointments.py` | Booking rules, rescheduling, doctor capacity, consultation and clinical notes |
| `billing.py` | Invoices and the mock M-Pesa payment. Paying an invoice starts the next step of its workflow |
| `pharmacy.py` | Prescriptions, refills, stock check, medicine invoice, inventory |
| `delivery.py` | Delivery details, delivery fee, rider assignment, pickup, delivery code |
| `home_services.py` | Home assessment for new clients, home service requests, nurse updates |
| `laboratory.py` | Doctor requests a test, patient pays, doctor saves the result |
| `admin.py` | Users, login codes, service prices, delivery tariff, reports, CSV export |
| `assistant.py` | Answers to common questions about the services |
| `demo.py` | Walks through the whole hospital journey and shows the rules blocking bad actions |

## The main workflow: medicine

1. Doctor writes a prescription (or the patient asks for a refill) -> pharmacy order
2. Pharmacist checks stock -> medicine invoice
3. Patient pays -> pharmacist calls the patient and records location, directions and fee
4. Patient pays the delivery invoice -> pharmacist assigns a rider
5. Rider picks up, calls the receiver, starts the trip, enters the patient's delivery code -> delivered

## Rules enforced in the code

- Every function checks the user's role first (`require_role`), not just the screen.
- Services run Monday to Saturday, 08:00 to 17:00. Appointments last 45 minutes with no overlaps.
- A doctor has a daily booking limit, and a patient cannot double-book.
- New clients need an approved home assessment before booking home services.
- Delivery cannot be dispatched until the delivery fee is paid.
- Riders only see delivery details. Never medicines, fees or the delivery code.
- Passwords are stored hashed. Mock M-Pesa sits in one class, ready to be swapped for the real one.

## Using it from Streamlit

    from seed import setup_database
    import auth, appointments

    setup_database()
    result = auth.login(email, password)
    user = result["user"]
    appointments.list_appointments(user)

Every function raises `BackendError` with a readable message. Show it with `st.error(str(error))`.
