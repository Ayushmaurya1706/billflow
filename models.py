from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

# Initialize the SQLAlchemy database instance. 
# This will bind to our Flask app in app.py.
db = SQLAlchemy()

class User(db.Model, UserMixin):
    """
    User model for handling dashboard authentication.
    Inherits from UserMixin to provide standard authentication helpers 
    (is_authenticated, is_active, is_anonymous, get_id) for Flask-Login.
    """
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    company_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(120), unique=True, index=True, nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<User {self.email}>"


class CompanySettings(db.Model):
    """
    Stores company-specific profile details.
    These are used to auto-populate the sender details on generated invoices.
    There should typically only be one row in this table.
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    logo_path = db.Column(db.String(255), nullable=True) # Rel path to logo in static/uploads
    gstin = db.Column(db.String(15), nullable=True)      # GST Registration Number
    address = db.Column(db.Text, nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    
    # Billing details (Bank Transfer Details)
    bank_name = db.Column(db.String(100), nullable=True)
    bank_account = db.Column(db.String(50), nullable=True)
    bank_ifsc = db.Column(db.String(20), nullable=True) # Sort code or IFSC code
    bank_account_name = db.Column(db.String(150), nullable=True)
    bank_branch = db.Column(db.String(100), nullable=True)
    upi_id = db.Column(db.String(100), nullable=True)
    terms_conditions = db.Column(db.Text, nullable=True)
    
    # Display Preferences (checkbox options)
    pref_show_hsn_summary = db.Column(db.Boolean, default=True, nullable=False)
    pref_show_bank_details = db.Column(db.Boolean, default=True, nullable=False)
    pref_show_terms = db.Column(db.Boolean, default=True, nullable=False)
    pref_show_notes = db.Column(db.Boolean, default=True, nullable=False)
    pref_show_signatory = db.Column(db.Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<CompanySettings {self.name}>"


class Invoice(db.Model):
    """
    Invoice model representing the main invoice document metadata, 
    totals, status, and client details.
    """
    id = db.Column(db.Integer, primary_key=True)
    # Unique invoice tracking number with index for fast database searches
    invoice_number = db.Column(db.String(50), unique=True, index=True, nullable=False)
    
    # Customer Foreign Key Link (B2B preserved historical records via SET NULL)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id', ondelete='SET NULL'), nullable=True, index=True)
    
    date_created = db.Column(db.Date, default=datetime.utcnow, nullable=False, index=True)
    due_date = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(20), default='Unpaid', nullable=False, index=True) # Draft, Unpaid, Paid, Pending, Overdue, Cancelled
    
    # Client/Customer Details Snapshot (Historical Audit Integrity)
    client_name = db.Column(db.String(150), nullable=False)
    client_email = db.Column(db.String(120), nullable=False)
    client_phone = db.Column(db.String(20), nullable=True)
    client_address = db.Column(db.Text, nullable=False)
    client_gstin = db.Column(db.String(15), nullable=True)
    
    # Calculation Fields
    gst_rate = db.Column(db.Float, default=18.0, nullable=False) # e.g. 18% GST
    discount = db.Column(db.Float, default=0.0, nullable=False)  # Discount percentage (e.g. 5%)
    subtotal = db.Column(db.Float, nullable=False)               # Sum of items (Qty * Price)
    tax_amount = db.Column(db.Float, nullable=False)             # GST Tax amount calculated
    cgst = db.Column(db.Float, default=0.0, nullable=False)
    sgst = db.Column(db.Float, default=0.0, nullable=False)
    igst = db.Column(db.Float, default=0.0, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)           # Net payable (Subtotal - Discount + Tax)
    
    # Optional payment instructions/footer notes
    notes = db.Column(db.Text, nullable=True)
    
    # Version 3 Additions: Favorites & Soft Delete States
    is_favorite = db.Column(db.Boolean, default=False, nullable=False, index=True)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False, index=True)
    deleted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationship to invoice line items.
    # cascade='all, delete-orphan' ensures deleting an invoice cleans up all its items.
    items = db.relationship('InvoiceItem', backref='invoice', cascade='all, delete-orphan', lazy=True)

    def __repr__(self):
        return f"<Invoice {self.invoice_number} - {self.client_name}>"


class ActivityLog(db.Model):
    """
    ActivityLog model tracking transaction and edit actions performed on invoices.
    Preserves log history even if the source Invoice record is permanently deleted.
    """
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id', ondelete='SET NULL'), nullable=True, index=True)
    invoice_number = db.Column(db.String(50), nullable=False) # Preserved for history audit
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        return f"<ActivityLog {self.action} on {self.invoice_number}>"


class InvoiceItem(db.Model):
    """
    InvoiceItem model representing single rows/items inside a parent invoice.
    """
    id = db.Column(db.Integer, primary_key=True)
    # Foreign key link pointing back to the parent Invoice
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id', ondelete='CASCADE'), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Float, nullable=False)
    tax_rate = db.Column(db.Float, default=18.0, nullable=False)
    hsn_sac = db.Column(db.String(50), nullable=True)
    total = db.Column(db.Float, nullable=False) # quantity * unit_price (stored for snapshot integrity)

    def __repr__(self):
        return f"<InvoiceItem {self.description} x{self.quantity}>"


class Customer(db.Model):
    """
    Customer model for catalog management.
    Name is unique and indexed to allow selection and auto-completion.
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, index=True, nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.Text, nullable=False)
    gstin = db.Column(db.String(15), nullable=True)

    def __repr__(self):
        return f"<Customer {self.name}>"
