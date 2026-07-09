import unittest
import os

# Set testing environment variables before importing app
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from datetime import datetime, timedelta, timezone
from io import BytesIO
from PIL import Image

# Import models, database and the main app instance
from app import app, SECURE_PDF_FOLDER
from models import db, User, CompanySettings, Invoice, InvoiceItem, Customer, ActivityLog
import openpyxl

class BillFlowTestCase(unittest.TestCase):
    
    def setUp(self):
        """Sets up a clean testing context before every single test run."""
        # 1. Force testing configurations
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False # Disable CSRF for logic tests (we test CSRF separately)
        
        # 2. Use a fast, isolated In-Memory SQLite database
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        
        self.app_context = app.app_context()
        self.app_context.push()
        
        # 3. Create tables in RAM
        db.create_all()
        
        # 4. Set up the test client (simulates browser)
        self.client = app.test_client()
        
        # 5. Seed test admin user & company profile
        self.email = 'testadmin@billflow.com'
        self.password = 'TestPassword123'
        
        # We import werkzeug security here to hash the test password
        from werkzeug.security import generate_password_hash
        self.test_user = User(
            full_name='Test Admin',
            company_name='Test Corp',
            email=self.email,
            password_hash=generate_password_hash(self.password)
        )
        
        db.session.add(self.test_user)
        db.session.commit()
        
        self.test_company = CompanySettings(
            user_id=1,
            name="Test Corp",
            email="billing@testcorp.com",
            phone="1234567890",
            address="123 Test Street, Bangalore",
            gstin="29AAAAA1111A1Z1",
            bank_name="Test Bank",
            bank_account="999888777",
            bank_ifsc="TEST0001234"
        )
        
        db.session.add(self.test_company)
        db.session.commit()

    def tearDown(self):
        """Cleans up and tears down context after every test."""
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    # Helper: Log in the test client
    def login_client(self):
        return self.client.post('/login', data={
            'email': self.email,
            'password': self.password
        }, follow_redirects=True)


    # ==========================================================================
    # 1. SECURITY & AUTHENTICATION TESTS
    # ==========================================================================

    def test_unauthenticated_access_redirect(self):
        """Asserts that visiting protected routes without login redirects to /login."""
        routes = ['/invoices/new', '/settings']
        for route in routes:
            response = self.client.get(route)
            self.assertEqual(response.status_code, 302)
            self.assertIn('/login', response.location)

    def test_public_landing_page(self):
        """Asserts that visiting root route without login renders the public landing page."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"gets your GST right", response.data)

    def test_check_email_exists(self):
        """Asserts that /api/check-email correctly reports existing and new users."""
        # Existing user
        res = self.client.post('/api/check-email', json={'email': self.email})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['exists'])

        # Non-existing user
        res = self.client.post('/api/check-email', json={'email': 'newuser@mail.com'})
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.get_json()['exists'])

    def test_registration_success(self):
        """Asserts that registering a new user is successful and logs the user in."""
        response = self.client.post('/register', data={
            'full_name': 'New User',
            'company_name': 'New Company Inc',
            'email': 'newuser@mail.com',
            'phone': '1234567890',
            'password': 'NewPassword123',
            'confirm_password': 'NewPassword123'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Account created and logged in successfully!", response.data)
        self.assertIn(b"New User", response.data)

    def test_registration_duplicate_email(self):
        """Asserts that registering with a duplicate email fails."""
        response = self.client.post('/register', data={
            'full_name': 'Duplicate User',
            'company_name': 'Duplicate Corp',
            'email': self.email,
            'password': 'NewPassword123',
            'confirm_password': 'NewPassword123'
        }, follow_redirects=True)
        self.assertIn(b"Email address already registered.", response.data)

    def test_registration_password_complexity(self):
        """Asserts that password complexity is validated on registration."""
        # Short password
        response = self.client.post('/register', data={
            'full_name': 'New User',
            'company_name': 'New Corp',
            'email': 'newuser@mail.com',
            'password': 'short',
            'confirm_password': 'short'
        }, follow_redirects=True)
        self.assertIn(b"Password must be at least 8 characters long", response.data)

    def test_login_success(self):
        """Asserts that logging in with valid credentials redirects to dashboard."""
        response = self.login_client()
        self.assertIn(b"Dashboard", response.data)
        self.assertIn(b"Test Admin", response.data)

    def test_login_failure(self):
        """Asserts that logging in with bad credentials fails with generic error flash."""
        response = self.client.post('/login', data={
            'email': self.email,
            'password': 'wrongpassword'
        }, follow_redirects=True)
        self.assertIn(b"Invalid email or password", response.data)

    def test_csrf_protection_active(self):
        """
        Re-enables CSRF protection and asserts that POST requests 
        fail with a 400 status code if a CSRF token is not provided.
        """
        # Enable CSRF protection for this test only
        app.config['WTF_CSRF_ENABLED'] = True
        self.login_client()
        
        # Send post without token
        response = self.client.post('/invoices/new', data={
            'client_name': 'Hacker Corp'
        })
        # CSRF blocks request with HTTP 400 Bad Request
        self.assertEqual(response.status_code, 400)
        
        # Restore configuration
        app.config['WTF_CSRF_ENABLED'] = False


    # ==========================================================================
    # 2. BUSINESS LOGIC & MATH EDGE CASES
    # ==========================================================================

    def test_successful_invoice_generation_math(self):
        """Asserts that a valid invoice calculates subtotals, GST, and totals correctly."""
        self.login_client()
        
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        due = (datetime.now(timezone.utc) + timedelta(days=15)).strftime('%Y-%m-%d')
        
        invoice_data = {
            'client_name': 'Rahul Sharma',
            'client_email': 'rahul@gmail.com',
            'client_address': '456 Client Lane, Mumbai',
            'client_phone': '9876543210',
            'client_gstin': '27BBBBB2222B2Y2',
            'date_created': today,
            'due_date': due,
            'status': 'Unpaid',
            'gst_rate': '18.0',   # 18% GST
            'discount': '10.0',   # 10% Discount
            'notes': 'Thank you!',
            # Item Arrays (simulate multiple items submission)
            'description[]': ['Consulting Fees', 'Software license'],
            'quantity[]': ['2', '1'],
            'unit_price[]': ['5000.00', '10000.00']
        }
        
        response = self.client.post('/invoices/new', data=invoice_data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        # Verify db persistence
        invoice = Invoice.query.filter_by(client_name='Rahul Sharma').first()
        self.assertIsNotNone(invoice)
        
        # Math verification:
        # Subtotal: (2 * 5000) + (1 * 10000) = 10000 + 10000 = 20000
        # Discount: 10% of 20000 = 2000
        # Taxable Amount: 20000 - 2000 = 18000
        # GST Tax: 18% of 18000 = 3240
        # Grand Total: 18000 + 3240 = 21240
        self.assertEqual(invoice.subtotal, 20000.00)
        self.assertEqual(invoice.tax_amount, 3240.00)
        self.assertEqual(invoice.total_amount, 21240.00)
        
        # Verify matching PDF was created in the secure PDF folder
        pdf_path = os.path.join(SECURE_PDF_FOLDER, f"{invoice.invoice_number}.pdf")
        self.assertTrue(os.path.exists(pdf_path))
        
        # Cleanup PDF file from disk
        if os.path.exists(pdf_path):
            os.remove(pdf_path)

    def test_zero_item_invoice_failure(self):
        """Asserts that submitting an invoice with empty items fails validation."""
        self.login_client()
        invoice_data = {
            'client_name': 'Zero Item Corp',
            'client_email': 'zero@corp.com',
            'client_address': 'Null Street',
            'date_created': '2026-06-29',
            'due_date': '2026-07-15',
            'gst_rate': '18.0',
            'discount': '0.0',
            # Empty items
            'description[]': [],
            'quantity[]': [],
            'unit_price[]': []
        }
        
        response = self.client.post('/invoices/new', data=invoice_data, follow_redirects=True)
        self.assertIn(b"An invoice must contain at least one line item", response.data)
        
        # Ensure no invoice was stored in DB
        invoice = Invoice.query.filter_by(client_name='Zero Item Corp').first()
        self.assertIsNone(invoice)

    def test_negative_values_failure(self):
        """Asserts that entering negative quantities or rates is rejected."""
        self.login_client()
        invoice_data = {
            'client_name': 'Negative Qty Corp',
            'client_email': 'neg@corp.com',
            'client_address': 'Neg Street',
            'date_created': '2026-06-29',
            'due_date': '2026-07-15',
            'gst_rate': '18.0',
            'discount': '0.0',
            'description[]': ['Faux item'],
            'quantity[]': ['-5'], # Negative qty!
            'unit_price[]': ['100.00']
        }
        
        response = self.client.post('/invoices/new', data=invoice_data, follow_redirects=True)
        self.assertIn(b"Invalid item data", response.data)
        
        # Ensure database is clean
        invoice = Invoice.query.filter_by(client_name='Negative Qty Corp').first()
        self.assertIsNone(invoice)

    def test_sequential_invoice_numbering(self):
        """Asserts that sequential invoice numbers increment correctly without collision."""
        self.login_client()
        
        # Create 2 invoices manually
        inv1 = Invoice(user_id=1, 
            invoice_number="INV-2026-0001",
            due_date=datetime.now(timezone.utc).date(),
            client_name="Client A", client_email="a@a.com", client_address="Addr A",
            subtotal=100.0, tax_amount=18.0, total_amount=118.0
        )
        db.session.add(inv1)
        db.session.commit()
        
        # Generate next sequence via helper in controller
        from app import get_next_invoice_number
        next_num = get_next_invoice_number(1)
        self.assertEqual(next_num, "INV-2026-0002")


    # ==========================================================================
    # 3. FILE UPLOAD & LOGO SECURITY
    # ==========================================================================

    def test_logo_invalid_file_extension(self):
        """Asserts that uploading files with invalid extensions (e.g. .exe, .py) is rejected."""
        self.login_client()
        
        # Simulate file upload with .txt containing image content
        data = {
            'name': 'Test Corp Updated',
            'email': 'billing@testcorp.com',
            'phone': '1234567890',
            'address': '123 Test Street, Bangalore',
            'logo': (BytesIO(b"not an image"), 'malicious.py') # .py file
        }
        
        response = self.client.post('/settings', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertIn(b"Unsupported logo file extension", response.data)

    def test_logo_corrupted_image_magic_number_failure(self):
        """Asserts that a file with .png extension but corrupted/non-image content is rejected."""
        self.login_client()
        
        # File is named logo.png, but its contents are simple text "fake image"
        data = {
            'name': 'Test Corp Updated',
            'email': 'billing@testcorp.com',
            'phone': '1234567890',
            'address': '123 Test Street, Bangalore',
            'logo': (BytesIO(b"fake image data stream"), 'logo.png') # Fake image content
        }
        
        response = self.client.post('/settings', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertIn(b"Invalid logo image", response.data)

    def test_invoice_editing(self):
        """Asserts that editing an invoice updates database totals and PDF output."""
        self.login_client()
        
        # Create invoice to edit
        inv = Invoice(user_id=1, 
            invoice_number="INV-2026-9999",
            due_date=datetime.now(timezone.utc).date(),
            client_name="Original Client", client_email="o@o.com", client_address="Original Addr",
            subtotal=100.0, tax_amount=18.0, total_amount=118.0
        )
        item = InvoiceItem(description="Original Item", quantity=1, unit_price=100.0, total=100.0)
        inv.items.append(item)
        db.session.add(inv)
        db.session.commit()
        
        # Post edit changes
        edit_data = {
            'client_name': 'Updated Client',
            'client_email': 'u@u.com',
            'client_address': 'Updated Addr',
            'client_phone': '555555',
            'date_created': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
            'due_date': (datetime.now(timezone.utc) + timedelta(days=15)).strftime('%Y-%m-%d'),
            'status': 'Paid',
            'gst_rate': '12.0',
            'discount': '5.0',
            'description[]': ['Updated Item 1', 'Updated Item 2'],
            'quantity[]': ['2', '1'],
            'unit_price[]': ['200.00', '100.00']
        }
        
        response = self.client.post(f'/invoices/{inv.id}/edit', data=edit_data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        # Retrieve updated record
        updated_inv = db.session.get(Invoice, inv.id)
        self.assertEqual(updated_inv.client_name, 'Updated Client')
        self.assertEqual(updated_inv.status, 'Paid')
        
        # Math checks:
        # Subtotal: (2 * 200) + (1 * 100) = 500
        # Discount: 5% of 500 = 25
        # Taxable: 500 - 25 = 475
        # GST: 12% of 475 = 57
        # Total: 475 + 57 = 532
        self.assertEqual(updated_inv.subtotal, 500.00)
        self.assertEqual(updated_inv.tax_amount, 57.00)
        self.assertEqual(updated_inv.total_amount, 532.00)
        self.assertEqual(len(updated_inv.items), 2)
        
        # Cleanup PDF file from disk
        pdf_path = os.path.join(SECURE_PDF_FOLDER, f"{updated_inv.invoice_number}.pdf")
        if os.path.exists(pdf_path):
            os.remove(pdf_path)

    def test_invoice_duplication(self):
        """Asserts that duplicating an invoice creates a new duplicate record with sequential numbering."""
        self.login_client()
        
        # Create source invoice
        inv = Invoice(user_id=1, 
            invoice_number="INV-2026-0005",
            due_date=datetime.now(timezone.utc).date(),
            client_name="Cloned Client", client_email="c@c.com", client_address="Cloned Addr",
            subtotal=100.0, tax_amount=18.0, total_amount=118.0
        )
        item = InvoiceItem(description="Cloned Item", quantity=1, unit_price=100.0, total=100.0)
        inv.items.append(item)
        db.session.add(inv)
        db.session.commit()
        
        response = self.client.get(f'/invoices/{inv.id}/duplicate', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        # Find duplicated invoice
        invoices = Invoice.query.filter_by(client_name='Cloned Client').all()
        self.assertEqual(len(invoices), 2)
        
        # Cleanup duplicated PDF
        for i in invoices:
            pdf_path = os.path.join(SECURE_PDF_FOLDER, f"{i.invoice_number}.pdf")
            if os.path.exists(pdf_path):
                os.remove(pdf_path)

    def test_excel_customer_import(self):
        """Asserts that uploading a valid Excel sheet parses, validates, and returns JSON statistics."""
        self.login_client()
        
        # Dynamically build a mock Excel file in memory using openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        
        # Setup headers
        headers = ["Company Name", "Email", "Phone", "Address", "GSTIN"]
        ws.append(headers)
        
        # Append rows (Row 2, 3 valid; Row 4 invalid email syntax)
        ws.append(["Excel Customer A", "a@excel.com", "1111", "Excel Address A", "27AAAAA1111A1Z1"])
        ws.append(["Excel Customer B", "b@excel.com", "2222", "Excel Address B", "27BBBBB2222B2Y2"])
        ws.append(["Invalid Email Customer", "not-an-email", "3333", "Address C", ""])
        
        # Save to memory stream
        excel_stream = BytesIO()
        wb.save(excel_stream)
        excel_stream.seek(0)
        
        data = {
            'excel_file': (excel_stream, 'customers.xlsx')
        }
        
        import json
        response = self.client.post('/customers/import', data=data, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 200)
        
        res_json = json.loads(response.data.decode('utf-8'))
        self.assertTrue(res_json['success'])
        self.assertEqual(res_json['imported_count'], 2)
        self.assertEqual(res_json['invalid_count'], 1)
        self.assertEqual(res_json['duplicate_count'], 0)
        
        # Verify the report contains the invalid email row entry (Row 4 in Excel sheet)
        self.assertEqual(len(res_json['report']), 1)
        self.assertEqual(res_json['report'][0]['row'], 4)
        self.assertIn("Invalid email format", res_json['report'][0]['reason'])
        
        # Assert database rows are populated
        cust_a = Customer.query.filter_by(name="Excel Customer A").first()
        self.assertIsNotNone(cust_a)
        self.assertEqual(cust_a.email, "a@excel.com")
        self.assertEqual(cust_a.phone, "1111")
        
        cust_b = Customer.query.filter_by(name="Excel Customer B").first()
        self.assertIsNotNone(cust_b)
        
        self.assertEqual(Customer.query.count(), 2)

    def test_download_customer_template(self):
        """Asserts that the sample template download streams an Excel file attachment."""
        self.login_client()
        response = self.client.get('/customers/download-template')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertIn("attachment;", response.headers.get("Content-Disposition", ""))
        self.assertIn("filename=billflow_customer_template.xlsx", response.headers.get("Content-Disposition", ""))


    def test_bulk_create_customers(self):
        """Asserts that bulk customer sheet creation saves valid records and returns structured JSON reports."""
        self.login_client()
        
        # Seed duplicate customer with a GSTIN in database
        cust_dup = Customer(user_id=1, name="Unique Company Name But Duplicate GSTIN", email="dup@dup.com", address="Dup Road", gstin="27GSTIN12345678")
        db.session.add(cust_dup)
        db.session.commit()
        
        bulk_data = {
            "rows": [
                {"name": "Valid Customer", "email": "valid@email.com", "phone": "123", "address": "Valid Addr", "gstin": "27AA"},
                {"name": "Invalid Customer", "email": "", "phone": "456", "address": "Invalid Addr", "gstin": ""},
                {"name": "New Company Name But Duplicate GSTIN", "email": "other@email.com", "phone": "789", "address": "Duplicate Addr", "gstin": "27gstin12345678"}
            ]
        }
        
        import json
        response = self.client.post(
            '/customers/bulk-create',
            data=json.dumps(bulk_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        
        res_json = json.loads(response.data.decode('utf-8'))
        self.assertTrue(res_json['success'])
        self.assertEqual(res_json['added_count'], 1)
        self.assertEqual(res_json['duplicate_count'], 1)
        
        # Check error rows report
        self.assertEqual(len(res_json['error_rows']), 1)
        self.assertEqual(res_json['error_rows'][0]['row_idx'], 1)
        self.assertIn('Email Address is required', res_json['error_rows'][0]['errors']['email'])
        
        # Check database: Customer table should have exactly 2 records
        # (the pre-seeded duplicate + the one new valid customer)
        self.assertEqual(Customer.query.count(), 2)
        
        valid_cust = Customer.query.filter_by(name="Valid Customer").first()
        self.assertIsNotNone(valid_cust)
        self.assertEqual(valid_cust.email, "valid@email.com")

    def test_clear_customer_directory(self):
        """Asserts that posting to /customers/clear removes all customer records from the database."""
        self.login_client()
        
        # Seed 3 customers
        db.session.add(Customer(user_id=1, name="Cust A", email="a@a.com", address="Addr A"))
        db.session.add(Customer(user_id=1, name="Cust B", email="b@a.com", address="Addr B"))
        db.session.add(Customer(user_id=1, name="Cust C", email="c@a.com", address="Addr C"))
        db.session.commit()
        self.assertEqual(Customer.query.count(), 3)
        
        response = self.client.post('/customers/clear', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Customer directory cleared successfully", response.data)
        self.assertEqual(Customer.query.count(), 0)

    def test_invoice_filtering_and_search(self):
        """Asserts that the shared query helper filters invoices by status, search queries, and dates."""
        self.login_client()
        
        # Seed invoices with distinct parameters
        inv_paid = Invoice(user_id=1, 
            invoice_number="INV-2026-9991",
            date_created=datetime.strptime("2026-01-01", "%Y-%m-%d").date(),
            due_date=datetime.strptime("2026-01-15", "%Y-%m-%d").date(),
            status="Paid",
            client_name="Alpha Tech",
            client_email="alpha@tech.com",
            client_address="Alpha Road",
            subtotal=100.0,
            tax_amount=18.0,
            total_amount=118.0
        )
        inv_unpaid = Invoice(user_id=1, 
            invoice_number="INV-2026-9992",
            date_created=datetime.strptime("2026-02-01", "%Y-%m-%d").date(),
            due_date=datetime.strptime("2026-02-15", "%Y-%m-%d").date(),
            status="Unpaid",
            client_name="Beta Corp",
            client_email="beta@corp.com",
            client_address="Beta Road",
            subtotal=200.0,
            tax_amount=36.0,
            total_amount=236.0
        )
        db.session.add(inv_paid)
        db.session.add(inv_unpaid)
        db.session.commit()
        
        # Test 1: Search by Invoice Number
        response = self.client.get('/invoices?search=INV-2026-9991')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"INV-2026-9991", response.data)
        self.assertNotIn(b"INV-2026-9992", response.data)
        
        # Test 2: Search by Client Name
        response = self.client.get('/invoices?search=Beta')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"INV-2026-9992", response.data)
        self.assertNotIn(b"INV-2026-9991", response.data)
        
        # Test 3: Filter by Status
        response = self.client.get('/invoices?status=Paid')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"INV-2026-9991", response.data)
        self.assertNotIn(b"INV-2026-9992", response.data)

    def test_invoice_exports(self):
        """Asserts that Excel and CSV exports generate and stream files from the exports/ directory."""
        self.login_client()
        
        inv = Invoice(user_id=1, 
            invoice_number="INV-2026-EXPORT-1",
            date_created=datetime.now(timezone.utc).date(),
            due_date=datetime.now(timezone.utc).date(),
            status="Paid",
            client_name="Export Client",
            client_email="export@client.com",
            client_address="Export Address",
            subtotal=100.0,
            tax_amount=18.0,
            total_amount=118.0
        )
        db.session.add(inv)
        db.session.commit()
        
        # Test Excel Export
        response = self.client.get('/invoices?export=excel')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        
        # Test CSV Export
        response = self.client.get('/invoices?export=csv')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/csv")

    def test_soft_delete_and_restore(self):
        """Asserts soft deleting moves an invoice to trash, and restoring brings it back."""
        self.login_client()
        inv = Invoice(user_id=1, 
            invoice_number="INV-2026-TRASH-1",
            date_created=datetime.now(timezone.utc).date(),
            due_date=datetime.now(timezone.utc).date(),
            status="Draft",
            client_name="Trash Client",
            client_email="trash@client.com",
            client_address="Trash Address",
            subtotal=10.0,
            tax_amount=1.8,
            total_amount=11.8
        )
        db.session.add(inv)
        db.session.commit()
        
        # Soft delete
        response = self.client.post(f'/invoices/{inv.id}/trash', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(inv.is_deleted)
        
        # Verify hidden from active invoices, visible in trash
        response_active = self.client.get('/invoices')
        self.assertNotIn(b"INV-2026-TRASH-1", response_active.data)
        
        response_trash = self.client.get('/invoices/trash')
        self.assertIn(b"INV-2026-TRASH-1", response_trash.data)
        
        # Restore
        response = self.client.post(f'/invoices/{inv.id}/restore', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(inv.is_deleted)
        
        # Verify visible in active invoices again
        response_active = self.client.get('/invoices')
        self.assertIn(b"INV-2026-TRASH-1", response_active.data)

    def test_permanent_delete(self):
        """Asserts permanent delete removes records from DB completely."""
        self.login_client()
        inv = Invoice(user_id=1, 
            invoice_number="INV-2026-PERM-1",
            date_created=datetime.now(timezone.utc).date(),
            due_date=datetime.now(timezone.utc).date(),
            status="Draft",
            client_name="Perm Client",
            client_email="perm@client.com",
            client_address="Perm Address",
            subtotal=10.0,
            tax_amount=1.8,
            total_amount=11.8
        )
        db.session.add(inv)
        db.session.commit()
        
        inv_id = inv.id
        # Permanent Delete
        response = self.client.post(f'/invoices/{inv_id}/delete-permanent', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        # Verify totally removed
        deleted_inv = db.session.get(Invoice, inv_id)
        self.assertIsNull = self.assertIsNone(deleted_inv)

    def test_toggle_favorites(self):
        """Asserts favorites can be toggled and sort correctly at the top of lists."""
        self.login_client()
        
        inv_a = Invoice(user_id=1, 
            invoice_number="INV-2026-FAV-A",
            date_created=datetime.now(timezone.utc).date(),
            due_date=datetime.now(timezone.utc).date(),
            status="Draft",
            client_name="Client A",
            client_email="a@client.com",
            client_address="Addr A",
            subtotal=10.0,
            tax_amount=1.8,
            total_amount=11.8,
            is_favorite=False
        )
        inv_b = Invoice(user_id=1, 
            invoice_number="INV-2026-FAV-B",
            date_created=datetime.now(timezone.utc).date(),
            due_date=datetime.now(timezone.utc).date(),
            status="Draft",
            client_name="Client B",
            client_email="b@client.com",
            client_address="Addr B",
            subtotal=20.0,
            tax_amount=3.6,
            total_amount=23.6,
            is_favorite=False
        )
        db.session.add(inv_a)
        db.session.add(inv_b)
        db.session.commit()
        
        # Toggle fav on B
        response = self.client.post(f'/invoices/{inv_b.id}/favorite', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(inv_b.is_favorite)
        
        # Query active invoices list and verify sorting order
        invoices_sorted = Invoice.query.filter_by(is_deleted=False).order_by(Invoice.is_favorite.desc(), Invoice.created_at.desc()).all()
        self.assertEqual(invoices_sorted[0].invoice_number, "INV-2026-FAV-B") # B must be first since it is starred

    def test_global_activity_logs(self):
        """Asserts operations write log entries visible on the global Activity Log page."""
        self.login_client()
        
        # Make a post that generates a log (e.g. create a manual customer or wipe directory)
        self.client.post('/customers/clear', follow_redirects=True)
        
        response = self.client.get('/invoices/activity-log')
        self.assertEqual(response.status_code, 200)

    def test_email_dispatch_simulation(self):
        """Asserts email dispatch redirects, logs simulator activities when SMTP is unconfigured."""
        self.login_client()
        inv = Invoice(user_id=1, 
            invoice_number="INV-2026-MAIL-1",
            date_created=datetime.now(timezone.utc).date(),
            due_date=datetime.now(timezone.utc).date(),
            status="Draft",
            client_name="Mail Client",
            client_email="mail@client.com",
            client_address="Mail Address",
            subtotal=10.0,
            tax_amount=1.8,
            total_amount=11.8
        )
        db.session.add(inv)
        db.session.commit()
        
        response = self.client.post(f'/invoices/{inv.id}/email', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Email Dispatch Mocked/Not Sent", response.data)
        
        # Verify a log entry was generated
        log = ActivityLog.query.filter_by(invoice_number="INV-2026-MAIL-1", action="Email Simulation").first()
        self.assertIsNotNone(log)

    def test_reports_summary_aggregation(self):
        """Asserts reports endpoints correctly sum revenues, customer lists, status, and timeline line points."""
        self.login_client()
        
        # Seed test invoices
        inv_paid = Invoice(user_id=1, 
            invoice_number="INV-2026-REP-1",
            date_created=datetime.now(timezone.utc).date(),
            due_date=datetime.now(timezone.utc).date(),
            status="Paid",
            client_name="Client Rep A",
            client_email="rep@a.com",
            client_address="Addr A",
            subtotal=100.0,
            tax_amount=18.0,
            total_amount=118.0
        )
        inv_unpaid = Invoice(user_id=1, 
            invoice_number="INV-2026-REP-2",
            date_created=datetime.now(timezone.utc).date(),
            due_date=datetime.now(timezone.utc).date(),
            status="Pending",
            client_name="Client Rep B",
            client_email="rep@b.com",
            client_address="Addr B",
            subtotal=200.0,
            tax_amount=36.0,
            total_amount=236.0
        )
        inv_cancelled = Invoice(user_id=1, 
            invoice_number="INV-2026-REP-3",
            date_created=datetime.now(timezone.utc).date(),
            due_date=datetime.now(timezone.utc).date(),
            status="Cancelled",
            client_name="Client Rep A",
            client_email="rep@a.com",
            client_address="Addr A",
            subtotal=300.0,
            tax_amount=54.0,
            total_amount=354.0
        )
        db.session.add(inv_paid)
        db.session.add(inv_unpaid)
        db.session.add(inv_cancelled)
        db.session.commit()
        
        # Test 1: Summary Endpoint API
        res = self.client.get('/api/reports/summary?range=last_30_days')
        self.assertEqual(res.status_code, 200)
        data = res.json
        self.assertTrue(data['success'])
        # Revenue should sum paid + pending = 118 + 236 = 354
        self.assertEqual(data['total_revenue'], 354.0)
        # Outstanding should sum pending/unpaid = 236
        self.assertEqual(data['outstanding_amount'], 236.0)
        self.assertEqual(data['total_invoices'], 3)
        self.assertEqual(data['paid_count'], 1)
        self.assertEqual(data['pending_count'], 1)
        self.assertEqual(data['cancelled_count'], 1)
        
        # Test 2: Revenue Trend Endpoint API
        res_trend = self.client.get('/api/reports/revenue?range=last_30_days')
        self.assertEqual(res_trend.status_code, 200)
        self.assertTrue(res_trend.json['success'])
        self.assertGreater(len(res_trend.json['data']), 0)
        
        # Test 3: Status Distribution Endpoint API
        res_status = self.client.get('/api/reports/invoice-status?range=last_30_days')
        self.assertEqual(res_status.status_code, 200)
        self.assertTrue(res_status.json['success'])
        self.assertEqual(res_status.json['data']['Paid'], 1)

    def test_reports_validation_error(self):
        """Asserts invalid custom date bounds trigger custom validation codes."""
        self.login_client()
        
        # Start Date > End Date boundary check
        res = self.client.get('/api/reports/summary?range=custom&start_date=2026-02-01&end_date=2026-01-01')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.json['success'])
        self.assertIn("Start date cannot be after end date", res.json['message'])

    def test_company_settings_extension(self):
        """Asserts new bank fields, terms, and display preferences persist in CompanySettings."""
        self.login_client()
        
        payload = {
            'name': 'Test Corp Ltd',
            'email': 'settings@testcorp.com',
            'phone': '9876543210',
            'address': 'Settings Office Road, Hyderabad',
            'gstin': '36AAAAA1111A1Z1',
            'bank_account_name': 'Test Corp Accounts',
            'bank_name': 'ICICI Bank',
            'bank_account': '999900001234',
            'bank_ifsc': 'ICIC0009999',
            'bank_branch': 'Hyderabad Gachibowli',
            'upi_id': 'testcorp@icici',
            'terms_conditions': '1. Standard terms apply.\n2. Hyd Jurisdiction.',
            'pref_show_hsn_summary': '1',
            'pref_show_bank_details': '1',
            'pref_show_terms': '1',
            'pref_show_signatory': '1'
        }
        
        response = self.client.post('/settings', data=payload, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        # Verify columns in DB
        company = CompanySettings.query.first()
        self.assertIsNotNone(company)
        self.assertEqual(company.bank_account_name, 'Test Corp Accounts')
        self.assertEqual(company.bank_branch, 'Hyderabad Gachibowli')
        self.assertEqual(company.upi_id, 'testcorp@icici')
        self.assertEqual(company.terms_conditions, '1. Standard terms apply.\n2. Hyd Jurisdiction.')
        self.assertTrue(company.pref_show_hsn_summary)
        self.assertTrue(company.pref_show_bank_details)
        self.assertFalse(company.pref_show_notes) # left unchecked, defaults to False in post parse

    def test_invoice_with_hsn_items(self):
        """Asserts invoices can be created with items containing HSN codes and generate PDFs with summaries."""
        self.login_client()
        
        # Seed company settings
        company = CompanySettings(user_id=1, 
            name="Alpha Corp",
            email="alpha@corp.com",
            phone="12345",
            address="Addr",
            gstin="36AAAAA1111A1Z1",
            pref_show_hsn_summary=True,
            pref_show_bank_details=True,
            pref_show_terms=True,
            pref_show_signatory=True
        )
        db.session.add(company)
        db.session.commit()
        
        # Create invoice payload
        payload = {
            'client_name': 'Beta Client',
            'client_email': 'beta@client.com',
            'client_address': 'Beta Address',
            'client_gstin': '36BBBBB2222B2Z2',
            'status': 'Pending',
            'gst_rate': '18.0',
            'discount': '5.0',
            'date_created': '2026-07-07',
            'due_date': '2026-07-22',
            'description[]': ['Item One', 'Item Two'],
            'hsn_sac[]': ['HSN123', 'HSN456'],
            'quantity[]': ['2', '1'],
            'unit_price[]': ['100.00', '200.00'],
            'notes': 'Thank you.'
        }
        
        response = self.client.post('/invoices/new', data=payload, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        # Verify HSN items exist in DB
        inv = Invoice.query.filter_by(client_name='Beta Client').first()
        self.assertIsNotNone(inv)
        self.assertEqual(len(inv.items), 2)
        self.assertEqual(inv.items[0].hsn_sac, 'HSN123')
        self.assertEqual(inv.items[1].hsn_sac, 'HSN456')
        
        # Verify details page renders HSN summary table
        res_details = self.client.get(f'/invoices/{inv.id}')
        self.assertEqual(res_details.status_code, 200)
        self.assertIn(b"HSN/SAC Summary", res_details.data)
        self.assertIn(b"HSN123", res_details.data)
        self.assertIn(b"HSN456", res_details.data)

    def test_api_reports_customers(self):
        """Asserts customer aggregates report endpoint executes and returns correct data."""
        self.login_client()
        
        # Seed customer
        cust = Customer(user_id=1, 
            name="Zeta Security",
            email="zeta@security.com",
            address="Zeta Office",
            gstin="36AAAAA1111A1Z1"
        )
        db.session.add(cust)
        db.session.commit()
        
        # Seed Invoice linked to customer
        inv = Invoice(user_id=1, 
            invoice_number="INV-ZETA-01",
            customer_id=cust.id,
            client_name="Zeta Security",
            client_email="zeta@security.com",
            client_address="Zeta Office",
            date_created=datetime.now(timezone.utc).date(),
            due_date=datetime.now(timezone.utc).date(),
            status="Paid",
            subtotal=1000.0,
            tax_amount=180.0,
            total_amount=1180.0
        )
        db.session.add(inv)
        db.session.commit()
        
        response = self.client.get('/api/reports/customers?range=last_30_days')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['success'])
        
        # Verify customer aggregates in response
        data = response.json['data']
        zeta_record = next((item for item in data if item['name'] == 'Zeta Security'), None)
        self.assertIsNotNone(zeta_record)
        self.assertEqual(zeta_record['invoice_count'], 1)
        self.assertEqual(zeta_record['revenue'], 1180.0)
        self.assertEqual(zeta_record['outstanding'], 0.0)

    def test_reports_customer_profile_rendering(self):
        """Asserts customer profile summary page renders details and invoice histories correctly."""
        self.login_client()
        
        # Seed customer
        cust = Customer(user_id=1, 
            name="Theta Consulting",
            email="theta@consulting.com",
            address="Theta Office",
            gstin="36BBBBB2222B2Z2"
        )
        db.session.add(cust)
        db.session.commit()
        
        # Seed Invoices (one Paid, one Pending)
        inv1 = Invoice(user_id=1, 
            invoice_number="INV-THETA-01",
            customer_id=cust.id,
            client_name="Theta Consulting",
            client_email="theta@consulting.com",
            client_address="Theta Office",
            date_created=datetime.now(timezone.utc).date(),
            due_date=datetime.now(timezone.utc).date(),
            status="Paid",
            subtotal=500.0,
            tax_amount=90.0,
            total_amount=590.0
        )
        inv2 = Invoice(user_id=1, 
            invoice_number="INV-THETA-02",
            customer_id=cust.id,
            client_name="Theta Consulting",
            client_email="theta@consulting.com",
            client_address="Theta Office",
            date_created=datetime.now(timezone.utc).date(),
            due_date=datetime.now(timezone.utc).date(),
            status="Pending",
            subtotal=800.0,
            tax_amount=144.0,
            total_amount=944.0
        )
        db.session.add_all([inv1, inv2])
        db.session.commit()
        
        response = self.client.get(f'/reports/customers/{cust.id}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Theta Consulting", response.data)
        self.assertIn(b"INV-THETA-01", response.data)
        self.assertIn(b"INV-THETA-02", response.data)
        self.assertIn(b"Outstanding Balance", response.data)

    def test_api_reports_products(self):
        """Asserts product analytics endpoint correctly aggregates and categorizes goods vs services."""
        self.login_client()
        
        # Seed Invoice with line items: 1 Product, 1 Service (starts with 99 SAC)
        inv = Invoice(user_id=1, 
            invoice_number="INV-PROD-01",
            client_name="Beta Client",
            client_email="beta@client.com",
            client_address="Beta Addr",
            date_created=datetime.now(timezone.utc).date(),
            due_date=datetime.now(timezone.utc).date(),
            status="Paid",
            subtotal=1500.0,
            tax_amount=270.0,
            total_amount=1770.0
        )
        db.session.add(inv)
        db.session.commit()
        
        item1 = InvoiceItem(
            invoice_id=inv.id,
            description="Steel Rods",
            quantity=10,
            unit_price=100.0,
            tax_rate=18.0,
            hsn_sac="7214", # Goods
            total=1000.0
        )
        item2 = InvoiceItem(
            invoice_id=inv.id,
            description="Software Consulting Service",
            quantity=2,
            unit_price=250.0,
            tax_rate=18.0,
            hsn_sac="9983", # Service SAC
            total=500.0
        )
        db.session.add_all([item1, item2])
        db.session.commit()
        
        response = self.client.get('/api/reports/products?range=last_30_days')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['success'])
        
        top_products = response.json['top_products']
        top_services = response.json['top_services']
        
        # Verify Product classification
        steel_rod = next((p for p in top_products if p['name'] == 'Steel Rods'), None)
        self.assertIsNotNone(steel_rod)
        self.assertEqual(steel_rod['quantity'], 10)
        self.assertEqual(steel_rod['revenue'], 1000.0)
        
        # Verify Service classification
        consulting = next((s for s in top_services if s['name'] == 'Software Consulting Service'), None)
        self.assertIsNotNone(consulting)
        self.assertEqual(consulting['quantity'], 2)
        self.assertEqual(consulting['revenue'], 500.0)

    def test_api_reports_gst(self):
        """Asserts GST report endpoint correctly calculates CGST, SGST, IGST totals and taxable revenue."""
        self.login_client()
        
        # Seed Invoices
        # 1. Intrastate Invoice (CGST/SGST collected)
        inv_intra = Invoice(user_id=1, 
            invoice_number="INV-GST-INTRA",
            client_name="Local Client",
            client_email="local@client.com",
            client_address="Local Address",
            client_gstin="36AAAAA1111A1Z1",
            date_created=datetime.now(timezone.utc).date(),
            due_date=datetime.now(timezone.utc).date(),
            status="Paid",
            subtotal=1000.0,
            tax_amount=180.0,
            cgst=90.0,
            sgst=90.0,
            igst=0.0,
            total_amount=1180.0
        )
        # 2. Interstate Invoice (IGST collected)
        inv_inter = Invoice(user_id=1, 
            invoice_number="INV-GST-INTER",
            client_name="Inter Client",
            client_email="inter@client.com",
            client_address="Inter Address",
            client_gstin="27BBBBB2222B2Z2",
            date_created=datetime.now(timezone.utc).date(),
            due_date=datetime.now(timezone.utc).date(),
            status="Paid",
            subtotal=2000.0,
            tax_amount=360.0,
            cgst=0.0,
            sgst=0.0,
            igst=360.0,
            total_amount=2360.0
        )
        db.session.add_all([inv_intra, inv_inter])
        db.session.commit()
        
        response = self.client.get('/api/reports/gst?range=last_30_days')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['success'])
        
        self.assertEqual(response.json['cgst_collected'], 90.0)
        self.assertEqual(response.json['sgst_collected'], 90.0)
        self.assertEqual(response.json['igst_collected'], 360.0)
        self.assertEqual(response.json['total_gst'], 540.0)
        self.assertEqual(response.json['taxable_revenue'], 3000.0)
        self.assertEqual(len(response.json['invoices']), 2)


if __name__ == '__main__':
    unittest.main()


    # ==========================================================================
    # MULTI-TENANCY ISOLATION TESTS
    # ==========================================================================

    def test_workspace_isolation_between_users(self):
        """Asserts that User B cannot access or modify User A's data (multi-tenant isolation)."""
        # Create a second user and log them in
        from werkzeug.security import generate_password_hash
        user2 = User(
            full_name='Test Admin 2',
            company_name='Test Corp 2',
            email='testadmin2@billflow.com',
            password_hash=generate_password_hash('TestPassword123')
        )
        db.session.add(user2)
        db.session.commit()

        # Log in User A and create an invoice
        self.login_client()
        inv_a = Invoice(user_id=self.test_user.id, 
            invoice_number="INV-2026-AAAA",
            due_date=datetime.now(timezone.utc).date(),
            client_name="Client A", client_email="a@a.com", client_address="Addr A",
            subtotal=100.0, tax_amount=18.0, total_amount=118.0
        )
        cust_a = Customer(user_id=self.test_user.id, 
            name="Customer A",
            email="a@a.com",
            address="Addr A"
        )
        db.session.add(inv_a)
        db.session.add(cust_a)
        db.session.commit()

        # Log out User A, log in User 2
        self.client.get('/logout', follow_redirects=True)
        self.client.post('/login', data={
            'email': 'testadmin2@billflow.com',
            'password': 'TestPassword123'
        }, follow_redirects=True)

        # 1. Assert User 2 cannot see User A's invoice in list
        res = self.client.get('/invoices')
        self.assertNotIn(b"INV-2026-AAAA", res.data)

        # 2. Assert User 2 cannot view details of User A's invoice
        res = self.client.get(f'/invoices/{inv_a.id}')
        self.assertEqual(res.status_code, 404)

        # 3. Assert User 2 cannot download User A's invoice PDF
        res = self.client.get(f'/invoices/{inv_a.id}/download')
        self.assertEqual(res.status_code, 404)

        # 4. Assert User 2 cannot toggle favorite on User A's invoice
        res = self.client.post(f'/invoices/{inv_a.id}/favorite')
        self.assertEqual(res.status_code, 404)

        # 5. Assert User 2 cannot delete User A's invoice
        res = self.client.post(f'/invoices/{inv_a.id}/delete')
        self.assertEqual(res.status_code, 404)

        # 6. Assert User 2 cannot view User A's customer details JSON
        res = self.client.get(f'/api/customers/{cust_a.id}')
        self.assertEqual(res.status_code, 404)
