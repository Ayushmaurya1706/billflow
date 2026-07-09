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

    # Relationships for isolated multi-tenant workspaces
    invoices = db.relationship('Invoice', backref='user', cascade='all, delete-orphan', lazy=True)
    customers = db.relationship('Customer', backref='user', cascade='all, delete-orphan', lazy=True)
    company_settings = db.relationship('CompanySettings', backref='user', cascade='all, delete-orphan', lazy=True)
    activity_logs = db.relationship('ActivityLog', backref='user', cascade='all, delete-orphan', lazy=True)

    def __init__(self, full_name=None, company_name=None, email=None, phone=None, password_hash=None, created_at=None, updated_at=None, **kwargs):
        super().__init__(
            full_name=full_name,
            company_name=company_name,
            email=email,
            phone=phone,
            password_hash=password_hash,
            created_at=created_at,
            updated_at=updated_at,
            **kwargs
        )

    def __repr__(self):
        return f"<User {self.email}>"


class CompanySettings(db.Model):
    """
    Stores company-specific profile details.
    These are used to auto-populate the sender details on generated invoices.
    There should typically only be one row per user in this table.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
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

    def __init__(self, user_id=None, name=None, logo_path=None, gstin=None, address=None, email=None, phone=None,
                 bank_name=None, bank_account=None, bank_ifsc=None, bank_account_name=None, bank_branch=None,
                 upi_id=None, terms_conditions=None, pref_show_hsn_summary=True, pref_show_bank_details=True,
                 pref_show_terms=True, pref_show_notes=True, pref_show_signatory=True, **kwargs):
        super().__init__(
            user_id=user_id,
            name=name, logo_path=logo_path, gstin=gstin, address=address, email=email, phone=phone,
            bank_name=bank_name, bank_account=bank_account, bank_ifsc=bank_ifsc, bank_account_name=bank_account_name,
            bank_branch=bank_branch, upi_id=upi_id, terms_conditions=terms_conditions,
            pref_show_hsn_summary=pref_show_hsn_summary, pref_show_bank_details=pref_show_bank_details,
            pref_show_terms=pref_show_terms, pref_show_notes=pref_show_notes, pref_show_signatory=pref_show_signatory,
            **kwargs
        )

    def __repr__(self):
        return f"<CompanySettings {self.name}>"


class Invoice(db.Model):
    """
    Invoice model representing the main invoice document metadata, 
    totals, status, and client details.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Invoice tracking number with index for fast database searches (Scoped unique per user)
    invoice_number = db.Column(db.String(50), index=True, nullable=False)
    
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

    __table_args__ = (
        db.UniqueConstraint('user_id', 'invoice_number', name='uq_invoice_user_number'),
    )

    def __init__(self, user_id=None, invoice_number=None, customer_id=None, date_created=None, due_date=None, status='Unpaid',
                 client_name=None, client_email=None, client_phone=None, client_address=None, client_gstin=None,
                 gst_rate=18.0, discount=0.0, subtotal=None, tax_amount=None, cgst=0.0, sgst=0.0, igst=0.0,
                 total_amount=None, notes=None, is_favorite=False, is_deleted=False, deleted_at=None,
                 created_at=None, updated_at=None, **kwargs):
        super().__init__(
            user_id=user_id,
            invoice_number=invoice_number, customer_id=customer_id, date_created=date_created, due_date=due_date,
            status=status, client_name=client_name, client_email=client_email, client_phone=client_phone,
            client_address=client_address, client_gstin=client_gstin, gst_rate=gst_rate, discount=discount,
            subtotal=subtotal, tax_amount=tax_amount, cgst=cgst, sgst=sgst, igst=igst, total_amount=total_amount,
            notes=notes, is_favorite=is_favorite, is_deleted=is_deleted, deleted_at=deleted_at,
            created_at=created_at, updated_at=updated_at,
            **kwargs
        )

    def __repr__(self):
        return f"<Invoice {self.invoice_number} - {self.client_name}>"


class ActivityLog(db.Model):
    """
    ActivityLog model tracking transaction and edit actions performed on invoices.
    Preserves log history even if the source Invoice record is permanently deleted.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id', ondelete='SET NULL'), nullable=True, index=True)
    invoice_number = db.Column(db.String(50), nullable=False) # Preserved for history audit
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __init__(self, user_id=None, invoice_id=None, invoice_number=None, action=None, details=None, created_at=None, **kwargs):
        super().__init__(
            user_id=user_id,
            invoice_id=invoice_id,
            invoice_number=invoice_number,
            action=action,
            details=details,
            created_at=created_at,
            **kwargs
        )

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

    def __init__(self, invoice_id=None, description=None, quantity=1, unit_price=None, tax_rate=18.0, hsn_sac=None, total=None, **kwargs):
        super().__init__(
            invoice_id=invoice_id,
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            tax_rate=tax_rate,
            hsn_sac=hsn_sac,
            total=total,
            **kwargs
        )

    def __repr__(self):
        return f"<InvoiceItem {self.description} x{self.quantity}>"


class Customer(db.Model):
    """
    Customer model for catalog management.
    Name is unique per user and indexed to allow selection and auto-completion.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(150), index=True, nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.Text, nullable=False)
    gstin = db.Column(db.String(15), nullable=True)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'name', name='uq_customer_user_name'),
    )

    def __init__(self, user_id=None, name=None, email=None, phone=None, address=None, gstin=None, **kwargs):
        super().__init__(
            user_id=user_id,
            name=name,
            email=email,
            phone=phone,
            address=address,
            gstin=gstin,
            **kwargs
        )

    def __repr__(self):
        return f"<Customer {self.name}>"
