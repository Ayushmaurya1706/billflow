import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    """
    A canvas that enables dynamic two-pass page numbering ('Page X of Y').
    Normal canvases write page numbers sequentially, meaning page 1 doesn't 
    know how many total pages exist. This custom canvas overrides showPage 
    and save to capture all draw operations, count the total pages, and then 
    draw the footer text right before saving.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        # Save state of current page to draw numbering later
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B")) # Muted grey slate color
        
        # Draw a thin footer separator line
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(36, 45, letter[0] - 36, 45)
        
        # Page numbering aligned to the right
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(letter[0] - 36, 30, page_text)
        
        # Payment note/Branding aligned to the left
        self.drawString(36, 30, "Generated securely via BillFlow. All rights reserved.")
        self.restoreState()


def generate_invoice_pdf(invoice, company, output_path):
    """
    Generates a professional corporate PDF invoice using ReportLab Platypus.
    
    :param invoice: An instance of the Invoice model.
    :param company: An instance of the CompanySettings model.
    :param output_path: Absolute filepath where the PDF should be written.
    """
    # 1. Page Configuration: Margins at 0.5 inches (36 points) for maximum space utilization.
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=54 # extra space at bottom for the page-number footer
    )

    # 2. Stylesheet Configuration
    styles = getSampleStyleSheet()
    
    # Custom colors
    PRIMARY_COLOR = colors.HexColor("#1E293B")   # Slate 800 (Headers, Branding)
    TEXT_MUTED = colors.HexColor("#64748B")      # Slate 500 (Labels)
    BORDER_COLOR = colors.HexColor("#E2E8F0")    # Slate 200 (Borders)
    
    # Custom paragraph styles to avoid modifying defaults
    style_normal = ParagraphStyle(
        'InvoiceNormal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#334155")
    )
    
    style_bold = ParagraphStyle(
        'InvoiceBold',
        parent=style_normal,
        fontName='Helvetica-Bold'
    )
    
    style_title = ParagraphStyle(
        'InvoiceTitle',
        parent=style_normal,
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=PRIMARY_COLOR,
        alignment=2 # Right aligned
    )

    style_header_label = ParagraphStyle(
        'HeaderLabel',
        parent=style_normal,
        textColor=TEXT_MUTED,
        fontSize=8,
        leading=10
    )

    story = []

    # 3. Header Grid Layout (Logo & Sender details on Left | Document Info on Right)
    logo_flowable = None
    if company.logo_path and os.path.exists(company.logo_path):
        try:
            # Load and scale logo maintaining ratio. Target: height of 50 points.
            logo_flowable = Image(company.logo_path, height=50, width=120, kind='bound')
        except Exception as e:
            # If image parsing fails, we skip it rather than crashing
            print(f"Error loading logo for PDF: {e}")

    sender_info = f"<b>{company.name}</b><br/>" \
                  f"{company.address.replace(chr(10), '<br/>')}<br/>" \
                  f"Email: {company.email} | Phone: {company.phone}"
    if company.gstin:
        sender_info += f"<br/>GSTIN: {company.gstin}"

    sender_p = Paragraph(sender_info, style_normal)
    logo_box = logo_flowable if logo_flowable else sender_p
    
    meta_info = f"<font size=20 color='#1E293B'><b>INVOICE</b></font><br/><br/>" \
                f"<b>Invoice #:</b> {invoice.invoice_number}<br/>" \
                f"<b>Date:</b> {invoice.date_created.strftime('%d-%b-%Y')}<br/>" \
                f"<b>Due Date:</b> {invoice.due_date.strftime('%d-%b-%Y')}<br/>" \
                f"<b>Status:</b> <font color='{'#10B981' if invoice.status == 'Paid' else '#EF4444'}'><b>{invoice.status.upper()}</b></font>"
    meta_p = Paragraph(meta_info, ParagraphStyle('InvoiceMeta', parent=style_normal, alignment=2))

    # Grid columns: Left col takes logo/details, Right col takes metadata
    header_data = [[logo_box, meta_p]]
    if logo_flowable:
        # If logo exists, render company details below it in a stacked layout
        header_data = [
            [logo_flowable, meta_p],
            [sender_p, '']
        ]

    # letter width is 612. Margins are 36*2=72. Printable width = 540.
    header_table = Table(header_data, colWidths=[300, 240])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('SPAN', (0,1), (1,1)) if logo_flowable else ('VALIGN', (0,0), (-1,-1), 'TOP')
    ]))
    
    story.append(header_table)
    story.append(Spacer(1, 20))

    # 4. Bill To & Payment Metadata Row
    client_text = f"<b>BILL TO:</b><br/>" \
                  f"<b>{invoice.client_name}</b><br/>" \
                  f"{invoice.client_address.replace(chr(10), '<br/>')}<br/>" \
                  f"Email: {invoice.client_email}"
    if invoice.client_phone:
        client_text += f" | Phone: {invoice.client_phone}"
    if invoice.client_gstin:
        client_text += f"<br/>Client GSTIN: {invoice.client_gstin}"
    
    client_p = Paragraph(client_text, style_normal)
    
    # We display bank transfer details side by side with billing info for professional layout
    bank_text = "<b>PAYMENT DETAILS:</b><br/>"
    if company.pref_show_bank_details and company.bank_name and company.bank_account:
        ac_name = company.bank_account_name if company.bank_account_name else company.name
        bank_text += f"<b>A/C Name:</b> {ac_name}<br/>" \
                     f"<b>Bank Name:</b> {company.bank_name}<br/>" \
                     f"<b>A/C Number:</b> {company.bank_account}<br/>" \
                     f"<b>IFSC Code:</b> {company.bank_ifsc}"
        if company.bank_branch:
            bank_text += f"<br/><b>Branch:</b> {company.bank_branch}"
        if company.upi_id:
            bank_text += f"<br/><b>UPI ID:</b> {company.upi_id}"
    else:
        bank_text += "Payment is due upon receipt.<br/>Bank details not configured."
        
    bank_p = Paragraph(bank_text, style_normal)
    
    billing_data = [[client_p, bank_p]]
    billing_table = Table(billing_data, colWidths=[270, 270])
    billing_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")), # Light card background
        ('BOX', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('PADDING', (0,0), (-1,-1), 10),
    ]))
    
    story.append(billing_table)
    story.append(Spacer(1, 20))

    # 5. Line Items Table (Widths: SNo 30, Description 280, Price 80, Qty 50, Total 100)
    # If HSN/SAC is present, we adjust column widths to fit HSN/SAC code
    has_hsn = any(item.hsn_sac for item in invoice.items)
    
    if has_hsn:
        item_headers = [
            Paragraph("<b>#</b>", style_bold),
            Paragraph("<b>Item & Description</b>", style_bold),
            Paragraph("<b>HSN/SAC</b>", style_bold),
            Paragraph("<b>Rate</b>", style_bold),
            Paragraph("<b>Qty</b>", style_bold),
            Paragraph("<b>Amount</b>", style_bold)
        ]
        col_widths = [30, 220, 60, 80, 50, 100]
    else:
        item_headers = [
            Paragraph("<b>#</b>", style_bold),
            Paragraph("<b>Item & Description</b>", style_bold),
            Paragraph("<b>Rate</b>", style_bold),
            Paragraph("<b>Qty</b>", style_bold),
            Paragraph("<b>Amount</b>", style_bold)
        ]
        col_widths = [30, 280, 80, 50, 100]
    
    table_data = [item_headers]
    
    # Iterate and construct invoice item rows
    for index, item in enumerate(invoice.items, start=1):
        if has_hsn:
            table_data.append([
                Paragraph(str(index), style_normal),
                Paragraph(item.description, style_normal),
                Paragraph(item.hsn_sac if item.hsn_sac else "-", style_normal),
                Paragraph(f"₹{item.unit_price:,.2f}", style_normal),
                Paragraph(str(item.quantity), style_normal),
                Paragraph(f"₹{item.total:,.2f}", style_normal)
            ])
        else:
            table_data.append([
                Paragraph(str(index), style_normal),
                Paragraph(item.description, style_normal),
                Paragraph(f"₹{item.unit_price:,.2f}", style_normal),
                Paragraph(str(item.quantity), style_normal),
                Paragraph(f"₹{item.total:,.2f}", style_normal)
            ])
        
    items_table = Table(table_data, colWidths=col_widths)
    
    # Style items table: alternate row background colors for clear reading
    t_style = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#F1F5F9")), # Table header background
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('TOPPADDING', (0,0), (-1,0), 6),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('ALIGN', (3,0), (-1,-1), 'RIGHT') if has_hsn else ('ALIGN', (2,0), (-1,-1), 'RIGHT'),
        ('ALIGN', (2,0), (2,-1), 'LEFT') if has_hsn else ('ALIGN', (2,0), (-1,-1), 'RIGHT'),
    ]
    
    for i in range(1, len(table_data)):
        if i % 2 == 0:
            t_style.append(('BACKGROUND', (0,i), (-1,i), colors.HexColor("#F8FAFC")))
        t_style.append(('TOPPADDING', (0,i), (-1,i), 6))
        t_style.append(('BOTTOMPADDING', (0,i), (-1,i), 6))
        
    items_table.setStyle(TableStyle(t_style))
    story.append(items_table)
    story.append(Spacer(1, 15))

    # HSN Summary Table Section
    if company.pref_show_hsn_summary and has_hsn:
        hsn_groups = {}
        for item in invoice.items:
            code = item.hsn_sac.strip() if item.hsn_sac else "-"
            if code not in hsn_groups:
                hsn_groups[code] = {
                    'taxable': 0.0,
                    'cgst': 0.0,
                    'sgst': 0.0,
                    'igst': 0.0,
                    'tax': 0.0
                }
            discount_fraction = invoice.discount / 100.0
            taxable_val = item.total * (1.0 - discount_fraction)
            tax_amount = taxable_val * (item.tax_rate / 100.0)
            
            if invoice.cgst > 0:
                cgst = tax_amount / 2.0
                sgst = tax_amount / 2.0
                igst = 0.0
            else:
                cgst = 0.0
                sgst = 0.0
                igst = tax_amount
                
            hsn_groups[code]['taxable'] += taxable_val
            hsn_groups[code]['cgst'] += cgst
            hsn_groups[code]['sgst'] += sgst
            hsn_groups[code]['igst'] += igst
            hsn_groups[code]['tax'] += tax_amount

        hsn_headers = [
            Paragraph("<b>HSN/SAC</b>", style_bold),
            Paragraph("<b>Taxable Value</b>", style_bold),
            Paragraph("<b>CGST</b>", style_bold),
            Paragraph("<b>SGST</b>", style_bold),
            Paragraph("<b>IGST</b>", style_bold),
            Paragraph("<b>Total Tax</b>", style_bold)
        ]
        hsn_table_data = [hsn_headers]
        for code, data in hsn_groups.items():
            hsn_table_data.append([
                Paragraph(code, style_normal),
                Paragraph(f"₹{data['taxable']:,.2f}", style_normal),
                Paragraph(f"₹{data['cgst']:,.2f}", style_normal),
                Paragraph(f"₹{data['sgst']:,.2f}", style_normal),
                Paragraph(f"₹{data['igst']:,.2f}", style_normal),
                Paragraph(f"₹{data['tax']:,.2f}", style_normal)
            ])
        hsn_table = Table(hsn_table_data, colWidths=[90, 90, 90, 90, 90, 90])
        hsn_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#F1F5F9")),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
            ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
        ]))
        story.append(hsn_table)
        story.append(Spacer(1, 15))

    # 6. Calculations Summary Box (We group this with notes to prevent split pages)
    summary_elements = []
    
    summary_data = [
        [Paragraph("Subtotal:", style_bold), f"₹{invoice.subtotal:,.2f}"],
        [Paragraph(f"Discount ({invoice.discount}%):", style_normal), f"- ₹{(invoice.subtotal * (invoice.discount / 100)):,.2f}"],
        [Paragraph(f"GST ({invoice.gst_rate}%):", style_normal), f"+ ₹{invoice.tax_amount:,.2f}"],
        [Paragraph("<font color='white'><b>Total Amount:</b></font>", ParagraphStyle('TotalText', parent=style_bold, textColor=colors.white)), 
         f"₹{invoice.total_amount:,.2f}"]
    ]
    
    summary_table = Table(summary_data, colWidths=[140, 100])
    summary_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'RIGHT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BACKGROUND', (0,-1), (-1,-1), PRIMARY_COLOR), # Style total amount highlight
        ('TEXTCOLOR', (1,-1), (1,-1), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
    ]))
    
    # Notes & Terms columns formatting
    notes_parts = []
    if company.pref_show_terms and company.terms_conditions:
        terms_html = company.terms_conditions.replace('\n', '<br/>')
        notes_parts.append(f"<b>Terms & Conditions:</b><br/>{terms_html}")
    
    if company.pref_show_notes and invoice.notes:
        notes_html = invoice.notes.replace('\n', '<br/>')
        notes_parts.append(f"<b>Notes:</b><br/>{notes_html}")
        
    if not notes_parts:
        notes_text = ""
    else:
        notes_text = "<br/><br/>".join(notes_parts)
        
    notes_p = Paragraph(f"<font color='#64748B' size=8>{notes_text}</font>", style_normal)
    
    layout_data = [[notes_p, summary_table]]
    layout_table = Table(layout_data, colWidths=[300, 240])
    layout_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
    ]))
    
    summary_elements.append(layout_table)
    
    # 7. Authorized Signatory Block (Floated right below math/notes table)
    if company.pref_show_signatory:
        sig_data = [
            [""],
            [Paragraph("<b>Authorized Signatory</b>", ParagraphStyle('SigStyle', parent=style_normal, alignment=1))]
        ]
        sig_table = Table(sig_data, colWidths=[200], rowHeights=[40, 15])
        sig_table.setStyle(TableStyle([
            ('LINEABOVE', (0,1), (0,1), 0.5, TEXT_MUTED),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))
        
        float_sig_data = [["", sig_table]]
        float_sig_table = Table(float_sig_data, colWidths=[340, 200])
        float_sig_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('ALIGN', (1,0), (1,0), 'RIGHT'),
            ('TOPPADDING', (0,0), (-1,-1), 20),
        ]))
        summary_elements.append(float_sig_table)
        
    # Wrap summary elements into a KeepTogether to guarantee they don't break across pages
    story.append(KeepTogether(summary_elements))

    # 7. Compile the PDF document
    doc.build(story, canvasmaker=NumberedCanvas)
