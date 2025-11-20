"""Generate mock ERP data for construction business."""

from datetime import datetime, timedelta
import random
from .notifications_db import (
    create_worker, create_client, create_vendor, create_payment,
    list_workers, list_clients, list_vendors
)

# Mock data templates
WORKERS_DATA = [
    {"name": "John Martinez", "email": "john.martinez@email.com", "phone": "+1-555-0101", "address": "123 Main St, City, State", "role": "Site Supervisor", "hourly_rate": 45.00, "status": "active", "hire_date": "2023-01-15"},
    {"name": "Michael Chen", "email": "michael.chen@email.com", "phone": "+1-555-0102", "address": "456 Oak Ave, City, State", "role": "Carpenter", "hourly_rate": 35.00, "status": "active", "hire_date": "2023-03-20"},
    {"name": "David Rodriguez", "email": "david.rodriguez@email.com", "phone": "+1-555-0103", "address": "789 Pine Rd, City, State", "role": "Electrician", "hourly_rate": 42.00, "status": "active", "hire_date": "2023-02-10"},
    {"name": "James Wilson", "email": "james.wilson@email.com", "phone": "+1-555-0104", "address": "321 Elm St, City, State", "role": "Plumber", "hourly_rate": 40.00, "status": "active", "hire_date": "2023-04-05"},
    {"name": "Robert Taylor", "email": "robert.taylor@email.com", "phone": "+1-555-0105", "address": "654 Maple Dr, City, State", "role": "Mason", "hourly_rate": 38.00, "status": "active", "hire_date": "2023-05-12"},
    {"name": "William Anderson", "email": "william.anderson@email.com", "phone": "+1-555-0106", "address": "987 Cedar Ln, City, State", "role": "Roofer", "hourly_rate": 36.00, "status": "active", "hire_date": "2023-06-18"},
    {"name": "Richard Thomas", "email": "richard.thomas@email.com", "phone": "+1-555-0107", "address": "147 Birch Way, City, State", "role": "HVAC Technician", "hourly_rate": 44.00, "status": "active", "hire_date": "2023-07-22"},
    {"name": "Joseph Jackson", "email": "joseph.jackson@email.com", "phone": "+1-555-0108", "address": "258 Spruce Ct, City, State", "role": "Concrete Worker", "hourly_rate": 32.00, "status": "active", "hire_date": "2023-08-30"},
]

CLIENTS_DATA = [
    {"name": "Sarah Johnson", "company_name": "Johnson Real Estate Development", "email": "sarah.johnson@jred.com", "phone": "+1-555-0201", "address": "1000 Business Blvd, Suite 200, City, State", "contact_person": "Sarah Johnson", "status": "active", "notes": "Major commercial developer"},
    {"name": "Emily Davis", "company_name": "Davis Construction Group", "email": "emily.davis@dcg.com", "phone": "+1-555-0202", "address": "2000 Corporate Ave, City, State", "contact_person": "Emily Davis", "status": "active", "notes": "Residential construction projects"},
    {"name": "Jessica Brown", "company_name": "Brown Properties LLC", "email": "jessica.brown@brownprop.com", "phone": "+1-555-0203", "address": "3000 Enterprise Dr, City, State", "contact_person": "Jessica Brown", "status": "active", "notes": "Multi-family housing projects"},
    {"name": "Amanda Miller", "company_name": "Miller & Associates", "email": "amanda.miller@millerassoc.com", "phone": "+1-555-0204", "address": "4000 Commerce St, City, State", "contact_person": "Amanda Miller", "status": "active", "notes": "Office building construction"},
    {"name": "Ashley Garcia", "company_name": "Garcia Development Corp", "email": "ashley.garcia@garcdev.com", "phone": "+1-555-0205", "address": "5000 Industrial Way, City, State", "contact_person": "Ashley Garcia", "status": "active", "notes": "Industrial facilities"},
]

VENDORS_DATA = [
    {"name": "Robert Smith", "company_name": "Smith Building Materials", "email": "robert.smith@smithmaterials.com", "phone": "+1-555-0301", "address": "6000 Supply Rd, City, State", "contact_person": "Robert Smith", "vendor_type": "Materials Supplier", "payment_terms": "Net 30", "status": "active", "notes": "Concrete, steel, lumber"},
    {"name": "Christopher Lee", "company_name": "Lee Hardware & Tools", "email": "chris.lee@leehw.com", "phone": "+1-555-0302", "address": "7000 Tool Ave, City, State", "contact_person": "Christopher Lee", "vendor_type": "Equipment Rental", "payment_terms": "Net 15", "status": "active", "notes": "Heavy machinery and tools"},
    {"name": "Daniel White", "company_name": "White Electrical Supply", "email": "daniel.white@whiteelec.com", "phone": "+1-555-0303", "address": "8000 Power St, City, State", "contact_person": "Daniel White", "vendor_type": "Electrical Supplies", "payment_terms": "Net 30", "status": "active", "notes": "Wiring, fixtures, panels"},
    {"name": "Matthew Harris", "company_name": "Harris Plumbing Supplies", "email": "matthew.harris@harrisplumb.com", "phone": "+1-555-0304", "address": "9000 Water Way, City, State", "contact_person": "Matthew Harris", "vendor_type": "Plumbing Supplies", "payment_terms": "Net 30", "status": "active", "notes": "Pipes, fixtures, fittings"},
    {"name": "Anthony Clark", "company_name": "Clark Roofing Materials", "email": "anthony.clark@clarkroof.com", "phone": "+1-555-0305", "address": "10000 Shingle Dr, City, State", "contact_person": "Anthony Clark", "vendor_type": "Roofing Materials", "payment_terms": "Net 30", "status": "active", "notes": "Shingles, membranes, insulation"},
    {"name": "Mark Lewis", "company_name": "Lewis Concrete & Aggregate", "email": "mark.lewis@lewisconcrete.com", "phone": "+1-555-0306", "address": "11000 Aggregate Blvd, City, State", "contact_person": "Mark Lewis", "vendor_type": "Concrete Supplier", "payment_terms": "Net 20", "status": "active", "notes": "Ready-mix concrete, aggregates"},
    {"name": "Donald Walker", "company_name": "Walker Safety Equipment", "email": "donald.walker@walkersafety.com", "phone": "+1-555-0307", "address": "12000 Safety Ln, City, State", "contact_person": "Donald Walker", "vendor_type": "Safety Equipment", "payment_terms": "Net 30", "status": "active", "notes": "PPE, safety gear, signage"},
]

PROJECTS = [
    "Downtown Office Complex",
    "Riverside Residential Tower",
    "Industrial Warehouse Facility",
    "Shopping Mall Expansion",
    "Hospital Wing Addition",
    "School Renovation Project",
    "Apartment Complex Phase 2",
    "Commercial Plaza Development",
]

CATEGORIES = [
    "Labor",
    "Materials",
    "Equipment Rental",
    "Subcontractor",
    "Permits & Fees",
    "Utilities",
    "Insurance",
    "Other",
]

def generate_mock_payments():
    """Generate mock payment records."""
    workers = list_workers()
    clients = list_clients()
    vendors = list_vendors()
    
    payments = []
    today = datetime.now().date()
    
    # Payments to receive from clients (invoices)
    for i, client in enumerate(clients[:4]):
        for j in range(2):  # 2 payments per client
            due_date = today + timedelta(days=random.randint(5, 45))
            amount = random.randint(5000, 50000)
            payments.append({
                "payment_type": "receive",
                "entity_type": "client",
                "entity_id": client['id'],
                "amount": amount,
                "currency": "USD",
                "description": f"Payment for {PROJECTS[i % len(PROJECTS)]} - Phase {j+1}",
                "invoice_number": f"INV-{client['id']:03d}-{j+1:03d}",
                "due_date": due_date.isoformat(),
                "status": "pending" if due_date > today else random.choice(["pending", "overdue"]),
                "project_name": PROJECTS[i % len(PROJECTS)],
                "category": random.choice(CATEGORIES),
                "notes": f"Milestone payment for {PROJECTS[i % len(PROJECTS)]}"
            })
    
    # Payments to send to vendors (bills)
    for i, vendor in enumerate(vendors[:5]):
        for j in range(2):  # 2 payments per vendor
            due_date = today + timedelta(days=random.randint(7, 35))
            amount = random.randint(2000, 25000)
            payments.append({
                "payment_type": "send",
                "entity_type": "vendor",
                "entity_id": vendor['id'],
                "amount": amount,
                "currency": "USD",
                "description": f"Payment for {vendor.get('vendor_type', 'Materials')} - Invoice {j+1}",
                "invoice_number": f"VEND-{vendor['id']:03d}-{j+1:03d}",
                "due_date": due_date.isoformat(),
                "status": "pending" if due_date > today else random.choice(["pending", "overdue"]),
                "project_name": PROJECTS[i % len(PROJECTS)],
                "category": random.choice(CATEGORIES),
                "notes": f"Materials/equipment for {PROJECTS[i % len(PROJECTS)]}"
            })
    
    # Payments to send to workers (payroll)
    for i, worker in enumerate(workers[:6]):
        due_date = today + timedelta(days=random.randint(1, 14))
        hours = random.randint(80, 160)
        amount = worker.get('hourly_rate', 35) * hours
        payments.append({
            "payment_type": "send",
            "entity_type": "worker",
            "entity_id": worker['id'],
            "amount": round(amount, 2),
            "currency": "USD",
            "description": f"Bi-weekly payroll - {hours} hours @ ${worker.get('hourly_rate', 35)}/hr",
            "invoice_number": f"PAY-{worker['id']:03d}-{datetime.now().strftime('%Y%m%d')}",
            "due_date": due_date.isoformat(),
            "status": "pending" if due_date > today else "pending",
            "project_name": PROJECTS[i % len(PROJECTS)],
            "category": "Labor",
            "notes": f"Payroll for {worker.get('role', 'Worker')}"
        })
    
    return payments


def populate_mock_data():
    """Populate database with mock data."""
    print("Generating mock ERP data...")
    
    # Check if data already exists
    existing_workers = list_workers()
    existing_clients = list_clients()
    existing_vendors = list_vendors()
    
    if existing_workers or existing_clients or existing_vendors:
        print("Mock data already exists. Skipping generation.")
        return
    
    # Create workers
    print("Creating workers...")
    for worker_data in WORKERS_DATA:
        create_worker(worker_data)
    
    # Create clients
    print("Creating clients...")
    for client_data in CLIENTS_DATA:
        create_client(client_data)
    
    # Create vendors
    print("Creating vendors...")
    for vendor_data in VENDORS_DATA:
        create_vendor(vendor_data)
    
    # Create payments
    print("Creating payments...")
    payments = generate_mock_payments()
    for payment_data in payments:
        create_payment(payment_data)
    
    print(f"✅ Mock data generated successfully!")
    print(f"   - {len(WORKERS_DATA)} workers")
    print(f"   - {len(CLIENTS_DATA)} clients")
    print(f"   - {len(VENDORS_DATA)} vendors")
    print(f"   - {len(payments)} payments")

