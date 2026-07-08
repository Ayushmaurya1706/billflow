/**
 * BillFlow Invoice Builder Interactivity
 * Handles dynamic row addition, real-time calculations, and live preview rendering.
 */

document.addEventListener('DOMContentLoaded', function() {
    // 1. DOM Element Cache
    const itemsTableBody = document.querySelector('#items-table-body');
    const addItemBtn = document.querySelector('#add-item-btn');
    const invoiceForm = document.querySelector('#invoice-form');
    
    // Form Inputs
    const discountInput = document.querySelector('#discount');
    const gstRateSelect = document.querySelector('#gst_rate');
    const clientNameInput = document.querySelector('#client_name');
    const clientEmailInput = document.querySelector('#client_email');
    const clientPhoneInput = document.querySelector('#client_phone');
    const clientAddressInput = document.querySelector('#client_address');
    const clientGstinInput = document.querySelector('#client_gstin');
    const invoiceNumberInput = document.querySelector('#invoice_number');
    const dateCreatedInput = document.querySelector('#date_created');
    const dueDateInput = document.querySelector('#due_date');
    const notesInput = document.querySelector('#notes');

    // Summary Displays (Form)
    const subtotalDisplay = document.querySelector('#subtotal-val');
    const discountDisplay = document.querySelector('#discount-val');
    const taxDisplay = document.querySelector('#tax-val');
    const totalDisplay = document.querySelector('#total-val');

    // Preview Elements (Paper Mockup)
    const prevClientName = document.querySelector('#prev-client-name');
    const prevClientEmail = document.querySelector('#prev-client-email');
    const prevClientPhone = document.querySelector('#prev-client-phone');
    const prevClientAddress = document.querySelector('#prev-client-address');
    const prevClientGstin = document.querySelector('#prev-client-gstin');
    const prevInvoiceNum = document.querySelector('#prev-invoice-num');
    const prevDate = document.querySelector('#prev-date');
    const prevDueDate = document.querySelector('#prev-due-date');
    const prevNotes = document.querySelector('#prev-notes');
    const prevItemsBody = document.querySelector('#prev-items-body');
    const prevSubtotal = document.querySelector('#prev-subtotal');
    const prevDiscount = document.querySelector('#prev-discount');
    const prevTax = document.querySelector('#prev-tax');
    const prevTotal = document.querySelector('#prev-total');

    // Helper: Format number as Currency
    function formatCurrency(value) {
        return '₹' + parseFloat(value).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,');
    }

    // Helper: Safe Parse Float (avoids NaN if input is blank or invalid)
    function safeParseFloat(val) {
        const parsed = parseFloat(val);
        return isNaN(parsed) ? 0 : parsed;
    }

    // Helper: Safe Parse Int
    function safeParseInt(val) {
        const parsed = parseInt(val, 10);
        return isNaN(parsed) ? 0 : parsed;
    }

    // 2. Dynamic Line Items Management
    function createRowHtml() {
        const tr = document.createElement('tr');
        tr.className = 'item-row';
        tr.innerHTML = `
            <td class="col-desc">
                <input type="text" name="description[]" class="form-control item-desc" placeholder="Item description..." required>
            </td>
            <td class="col-hsn">
                <input type="text" name="hsn_sac[]" class="form-control item-hsn" placeholder="HSN/SAC (Optional)">
            </td>
            <td class="col-qty">
                <input type="number" name="quantity[]" class="form-control item-qty" value="1" min="1" required>
            </td>
            <td class="col-rate">
                <input type="number" name="unit_price[]" class="form-control item-rate" value="0.00" min="0" step="0.01" required>
            </td>
            <td class="col-amount">₹0.00</td>
            <td class="col-action">
                <button type="button" class="remove-item-btn" title="Remove line item">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                    </svg>
                </button>
            </td>
        `;
        return tr;
    }

    // Add row
    if (addItemBtn) {
        addItemBtn.addEventListener('click', function() {
            itemsTableBody.appendChild(createRowHtml());
            calculateInvoice();
        });
    }

    // Remove row (Event delegation on table body)
    if (itemsTableBody) {
        itemsTableBody.addEventListener('click', function(e) {
            // Find closest element matching .remove-item-btn
            const removeBtn = e.target.closest('.remove-item-btn');
            if (removeBtn) {
                const row = removeBtn.closest('.item-row');
                
                // Keep at least one row in the table
                if (itemsTableBody.querySelectorAll('.item-row').length > 1) {
                    row.remove();
                    calculateInvoice();
                } else {
                    alert('An invoice must contain at least one line item.');
                }
            }
        });
    }

    // 3. Real-Time Math Engine
    function calculateInvoice() {
        let subtotal = 0;
        const rows = itemsTableBody.querySelectorAll('.item-row');
        
        // Loop through rows to calculate line amounts
        rows.forEach(row => {
            const qtyInput = row.querySelector('.item-qty');
            const rateInput = row.querySelector('.item-rate');
            const amountCell = row.querySelector('.col-amount');

            // Force values to respect minimum constraints to prevent negatives
            let qty = safeParseInt(qtyInput.value);
            if (qty < 1) {
                qty = 1;
                qtyInput.value = 1;
            }
            
            let rate = safeParseFloat(rateInput.value);
            if (rate < 0) {
                rate = 0;
                rateInput.value = "0.00";
            }

            const rowAmount = qty * rate;
            subtotal += rowAmount;
            
            // Update line total text cell
            amountCell.textContent = formatCurrency(rowAmount);
        });

        // Fetch adjustments
        let discountRate = safeParseFloat(discountInput.value);
        if (discountRate < 0) {
            discountRate = 0;
            discountInput.value = 0;
        } else if (discountRate > 100) {
            discountRate = 100;
            discountInput.value = 100;
        }
        
        let gstRate = safeParseFloat(gstRateSelect.value);

        // Calculations
        const discountAmount = subtotal * (discountRate / 100);
        const taxableAmount = subtotal - discountAmount;
        const taxAmount = taxableAmount * (gstRate / 100);
        const grandTotal = taxableAmount + taxAmount;

        // Update Form Display
        subtotalDisplay.textContent = formatCurrency(subtotal);
        discountDisplay.textContent = '- ' + formatCurrency(discountAmount);
        taxDisplay.textContent = '+ ' + formatCurrency(taxAmount);
        totalDisplay.textContent = formatCurrency(grandTotal);

        // Sync Preview Displays
        prevSubtotal.textContent = formatCurrency(subtotal);
        prevDiscount.textContent = '- ' + formatCurrency(discountAmount);
        prevTax.textContent = '+ ' + formatCurrency(taxAmount);
        prevTotal.textContent = formatCurrency(grandTotal);

        // Rebuild preview item list
        updatePreviewItemsTable(rows);
    }

    // 4. Update the visual table in the preview panel
    function updatePreviewItemsTable(rows) {
        prevItemsBody.innerHTML = '';
        
        rows.forEach((row, index) => {
            const desc = row.querySelector('.item-desc').value || '(Empty Description)';
            const hsnInput = row.querySelector('.item-hsn');
            const hsn = hsnInput ? hsnInput.value.trim() : '';
            const qty = safeParseInt(row.querySelector('.item-qty').value);
            const rate = safeParseFloat(row.querySelector('.item-rate').value);
            const amount = qty * rate;

            let hsnSpan = '';
            if (hsn) {
                hsnSpan = ` <span style="font-size: 7px; color: var(--text-muted); font-weight: normal; margin-left: 6px;">(HSN: ${escapeHtml(hsn)})</span>`;
            }

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td style="width: 30px;">${index + 1}</td>
                <td><strong>${escapeHtml(desc)}</strong>${hsnSpan}</td>
                <td style="text-align: right; width: 80px;">${formatCurrency(rate)}</td>
                <td style="text-align: center; width: 40px;">${qty}</td>
                <td style="text-align: right; width: 90px;">${formatCurrency(amount)}</td>
            `;
            prevItemsBody.appendChild(tr);
        });
    }

    // Escapes special HTML tags to prevent XSS issues inside preview sync
    function escapeHtml(text) {
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return text.replace(/[&<>"']/g, function(m) { return map[m]; });
    }

    // 5. Live Inputs Sync (Input Event listeners on fields)
    function setupSync(inputEl, previewEl, defaultText = '', formatFn = null) {
        if (!inputEl || !previewEl) return;
        
        const updateFn = () => {
            let val = inputEl.value;
            if (formatFn) {
                val = formatFn(val);
            }
            previewEl.innerHTML = val ? val.replace(/\n/g, '<br/>') : defaultText;
        };
        
        inputEl.addEventListener('input', updateFn);
        updateFn(); // Run once initially
    }

    // Bind sync listeners
    setupSync(clientNameInput, prevClientName, '<strong>Client Name</strong>');
    setupSync(clientEmailInput, prevClientEmail, 'client@email.com');
    setupSync(clientPhoneInput, prevClientPhone, 'Phone number');
    setupSync(clientAddressInput, prevClientAddress, 'Billing address details...');
    setupSync(clientGstinInput, prevClientGstin, 'GSTIN: (Not provided)');
    setupSync(invoiceNumberInput, prevInvoiceNum, 'INV-XXXX-XXXX');
    setupSync(notesInput, prevNotes, 'Payment terms & notes here...');

    // Simple date formatter helper
    function formatDateString(val) {
        if (!val) return '';
        const d = new Date(val);
        if (isNaN(d.getTime())) return '';
        
        const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        return `${d.getDate().toString().padStart(2, '0')}-${months[d.getMonth()]}-${d.getFullYear()}`;
    }

    setupSync(dateCreatedInput, prevDate, '00-AAA-0000', formatDateString);
    setupSync(dueDateInput, prevDueDate, '00-AAA-0000', formatDateString);

    // 6. Customer Selection Dropdown Auto-fill
    const customerSelect = document.querySelector('#customer_select');
    if (customerSelect) {
        customerSelect.addEventListener('change', function() {
            const customerId = this.value;
            if (!customerId) return;
            
            // Query the JSON endpoint for customer metadata
            fetch(`/api/customers/${customerId}`)
                .then(response => {
                    if (!response.ok) {
                        throw new Error('Failed to retrieve customer data');
                    }
                    return response.json();
                })
                .then(data => {
                    // Populate form fields
                    if (clientNameInput) clientNameInput.value = data.name;
                    if (clientEmailInput) clientEmailInput.value = data.email;
                    if (clientPhoneInput) clientPhoneInput.value = data.phone;
                    if (clientAddressInput) clientAddressInput.value = data.address;
                    if (clientGstinInput) clientGstinInput.value = data.gstin;
                    
                    // Dispatch input events programmatically so the live preview updates
                    const inputEvent = new Event('input', { bubbles: true });
                    if (clientNameInput) clientNameInput.dispatchEvent(inputEvent);
                    if (clientEmailInput) clientEmailInput.dispatchEvent(inputEvent);
                    if (clientPhoneInput) clientPhoneInput.dispatchEvent(inputEvent);
                    if (clientAddressInput) clientAddressInput.dispatchEvent(inputEvent);
                    if (clientGstinInput) clientGstinInput.dispatchEvent(inputEvent);
                    
                    // Recalculate totals
                    calculateInvoice();
                })
                .catch(error => {
                    console.error('Customer fetch error:', error);
                });
        });
    }

    // Event listeners to trigger recalculations
    if (invoiceForm) {
        invoiceForm.addEventListener('input', function(e) {
            if (e.target.classList.contains('item-qty') || 
                e.target.classList.contains('item-rate') || 
                e.target.id === 'discount' || 
                e.target.id === 'gst_rate' ||
                e.target.classList.contains('item-desc')) {
                calculateInvoice();
            }
        });
    }

    // Run initial calculations
    calculateInvoice();
});
