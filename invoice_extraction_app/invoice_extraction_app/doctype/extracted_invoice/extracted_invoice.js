// invoice_extraction_app/doctype/extracted_invoice/extracted_invoice.js

frappe.ui.form.on('Extracted Invoice', {
    onload: function (frm) {
        window.extractedInvoiceButtons = window.extractedInvoiceButtons || [];
    },

    refresh: function (frm) {
        if (window.extractedInvoiceButtons && window.extractedInvoiceButtons.length > 0) {
            window.extractedInvoiceButtons.forEach(function (btn) {
                if (btn && btn.$wrapper) {
                    btn.$wrapper.remove();
                }
            });
            window.extractedInvoiceButtons = [];
        }

        if (frm.doc.original_file && frm.doc.status !== 'Converted') {
            console.log("✅ Adding Gemini Extract button");

            const geminiExtractBtn = frm.add_custom_button(__('🔍 Extract via Gemini'), function () {
                extract_invoice_data_gemini(frm);
            }, __('Extraction'));

            window.extractedInvoiceButtons.push(geminiExtractBtn);
        }

        if (frm.doc.original_file && frm.doc.status !== 'Converted') {
            console.log("✅ Adding Mistral Extract button");

            const mistralExtractBtn = frm.add_custom_button(__('🌐 Extract via Mistral'), function () {
                extract_invoice_data_mistral(frm);
            }, __('Extraction'));

            window.extractedInvoiceButtons.push(mistralExtractBtn);

            frm.page.set_primary_action(__('Extract via Mistral'), function () {
                extract_invoice_data_mistral(frm);
            }, 'fa fa-magic');
        }

        // زر إنشاء فاتورة شراء
        const hasItems = frm.doc.items && frm.doc.items.length > 0;
        const hasSupplier = frm.doc.supplier_link;
        const canCreate = frm.doc.status === 'Ready' || (hasItems && hasSupplier);

        if (canCreate && frm.doc.status !== 'Converted') {
            console.log("✅ Adding Create Purchase Invoice button");

            const createBtn = frm.add_custom_button(__('🧾 Create Purchase Invoice'), function () {
                open_purchase_invoice_form(frm);
            }, __('Actions'));

            window.extractedInvoiceButtons.push(createBtn);
        }

        if (frm.doc.purchase_invoice_link) {
            console.log("✅ Adding View Purchase Invoice button");

            const viewBtn = frm.add_custom_button(__('📄 View Purchase Invoice'), function () {
                frappe.set_route('Form', 'Purchase Invoice', frm.doc.purchase_invoice_link);
            }, __('Actions'));

            window.extractedInvoiceButtons.push(viewBtn);
        }

        if (hasItems) {
            console.log("✅ Adding Validate Tax button");

            const validateBtn = frm.add_custom_button(__('🧮 Validate Tax'), function () {
                validate_tax_calculations(frm);
            }, __('Tools'));

            window.extractedInvoiceButtons.push(validateBtn);
        }

        if (hasItems) {
            console.log("✅ Adding Fix Tax button");

            const fixBtn = frm.add_custom_button(__('🔧 Fix Tax Calculation'), function () {
                fix_tax_calculation(frm);
            }, __('Tools'));

            window.extractedInvoiceButtons.push(fixBtn);
        }

        // تنسيق حالة الاستخراج
        if (frm.doc.status && frm.fields_dict.status) {
            const status_class = {
                'Draft': 'label-default',
                'Ready': 'label-primary',
                'Converted': 'label-success'
            }[frm.doc.status] || 'label-default';

            frm.fields_dict.status.$wrapper.find('.control-value').html(
                `<span class="label ${status_class}">${frm.doc.status}</span>`
            );
        }

        console.log("✅ Form refresh completed");
    },

    original_file: function (frm) {
        setTimeout(function () {
            frm.refresh();
        }, 300);
    },

    items_on_form_rendered: function (frm) {
        update_item_totals(frm);
    },

    quantity: function (frm, cdt, cdn) {
        update_item_row_total(frm, cdt, cdn);
        update_totals(frm);
    },

    rate: function (frm, cdt, cdn) {
        update_item_row_total(frm, cdt, cdn);
        update_totals(frm);
    }
});

function extract_invoice_data_gemini(frm) {
    if (!frm.doc.original_file) {
        frappe.msgprint(__('Please upload an invoice file first'));
        return;
    }

    frappe.call({
        method: 'invoice_extraction_app.api.extract_invoice_data_only',
        args: { file_url: frm.doc.original_file },
        freeze: true,
        freeze_message: __('Extracting invoice data with Gemini...'),
        callback: function (r) {
            if (r.message.success) {
                populate_form_with_data(frm, r.message.data);
                frm.set_value('extraction_model', 'Gemini');
                frm.save();

                frappe.show_alert({
                    message: __('✅ Invoice data extracted successfully using Gemini!'),
                    indicator: 'green'
                }, 5);
            } else {
                frappe.msgprint({
                    title: __('Extraction Failed'),
                    message: __('Gemini extraction failed: ') + r.message.error,
                    indicator: 'red'
                });
            }
        }
    });
}

function extract_invoice_data_mistral(frm) {
    if (!frm.doc.original_file) {
        frappe.msgprint(__('Please upload an invoice file first'));
        return;
    }

    frappe.call({
        method: 'invoice_extraction_app.mistral.get_mistral_settings',
        callback: function (settings_r) {
            if (!settings_r.message || !settings_r.message.success) {
                frappe.msgprint({
                    title: __('Mistral Settings Error'),
                    message: __('Failed to get Mistral settings: ') + (settings_r.message.error || 'Unknown error'),
                    indicator: 'red'
                });
                return;
            }

            if (!settings_r.message.mistral_available) {
                frappe.msgprint({
                    title: __('Mistral Not Installed'),
                    message: __('Mistral library is not installed. Please install: pip install mistralai'),
                    indicator: 'red'
                });
                return;
            }

            if (!settings_r.message.has_api_key) {
                frappe.msgprint({
                    title: __('API Key Required'),
                    message: __('Please set your Mistral API key in Mistral Settings first.'),
                    indicator: 'orange',
                    primary_action: {
                        label: __('Open Settings'),
                        action: function () {
                            frappe.set_route('Form', 'Mistral Settings', 'Mistral Settings');
                        }
                    }
                });
                return;
            }

            show_mistral_extraction(frm, settings_r.message);
        }
    });
}

function show_mistral_extraction_options(frm, settings) {
    frappe.prompt([
        {
            fieldname: 'model',
            fieldtype: 'Select',
            label: __('Select Model'),
            options: `mistral-ocr-latest\nmistral-ocr-2512\npixtral-12b-2409\npixtral-large-latest\nmistral-large-latest\nmistral-medium-latest\nmistral-small-latest\nopen-mistral-7b\nopen-mixtral-8x7b\nopen-mixtral-8x22b`,
            default: settings.model || 'mistral-ocr-latest',
            reqd: 1
        },
        {
            fieldname: 'temperature',
            fieldtype: 'Float',
            label: __('Temperature'),
            default: settings.temperature || 0.1,
            min_value: 0,
            max_value: 1
        }
    ], function (values) {
        frappe.call({
            method: 'invoice_extraction_app.mistral.extract_invoice_data_only',
            args: {
                file_url: frm.doc.original_file,
                model_name: values.model,
                temperature: parseFloat(values.temperature)
            },
            freeze: true,
            freeze_message: __('Extracting invoice data with Mistral...'),
            callback: function (r) {
                if (r.message.success) {
                    populate_form_with_data(frm, r.message.data);
                    frm.set_value('extraction_model', `Mistral: ${values.model}`);
                    frm.save();

                    frappe.show_alert({
                        message: __('✅ Invoice data extracted successfully using Mistral!'),
                        indicator: 'green'
                    }, 5);
                } else {
                    frappe.msgprint({
                        title: __('Extraction Failed'),
                        message: __('Mistral extraction failed: ') + r.message.error,
                        indicator: 'red'
                    });
                }
            }
        });
    }, __('Mistral Extraction Options'), __('Start Extraction'));
}
function show_mistral_extraction(frm, settings) {
    frappe.call({
        method: 'invoice_extraction_app.mistral.extract_invoice_data_only',
        args: {
            file_url: frm.doc.original_file
        },
        freeze: true,
        freeze_message: __('Extracting invoice data with Mistral...'),
        callback: function (r) {
            if (r.message.success) {
                populate_form_with_data(frm, r.message.data);
                frm.set_value('extraction_model', `Mistral: ${values.model}`);
                frm.save();

                frappe.show_alert({
                    message: __('✅ Invoice data extracted successfully using Mistral!'),
                    indicator: 'green'
                }, 5);
            } else {
                frappe.msgprint({
                    title: __('Extraction Failed'),
                    message: __('Mistral extraction failed: ') + r.message.error,
                    indicator: 'red'
                });
            }
        }
    });
}

function populate_form_with_data(frm, data) {
    console.log("📝 Populating form with data", data);

    if (frm.doc.items && frm.doc.items.length > 0) {
        frm.clear_table('items');
    }

    let matched_supplier_id = '';
    if (data.supplier || data.supplier_ar) {
        const supplier_name = data.supplier_ar || data.supplier;

        frappe.call({
            method: 'frappe.client.get_list',
            args: {
                doctype: 'Supplier',
                filters: [['supplier_name', 'like', `%${supplier_name}%`]],
                fields: ['name', 'supplier_name'],
                limit: 1
            },
            async: false,
            callback: function (r) {
                if (r.message && r.message.length > 0) {
                    matched_supplier_id = r.message[0].name;
                }
            }
        });
    }

    frm.set_value('supplier_name', data.supplier_ar || data.supplier || '');
    frm.set_value('supplier_link', matched_supplier_id);
    frm.set_value('invoice_number', data.invoice_number || '');
    frm.set_value('invoice_date', data.date || '');
    frm.set_value('due_date', data.due_date || '');
    frm.set_value('subtotal', data.subtotal || 0);
    frm.set_value('tax_amount', data.tax_amount || 0);
    frm.set_value('total_amount', data.total_amount || 0);
    frm.set_value('currency', data.currency || 'SAR');

    const items = data.items || [];

    items.forEach(function (item, index) {
        const row = frm.add_child('items');
        const description = item.description_ar || item.description || __('Item') + ' ' + (index + 1);

        let matched_item_id = '';

        if (description) {
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Item',
                    filters: [['item_name', 'like', `%${description}%`]],
                    fields: ['name', 'item_name', 'item_code'],
                    limit: 1
                },
                async: false,
                callback: function (r) {
                    if (r.message && r.message.length > 0) {
                        matched_item_id = r.message[0].name;
                    }
                }
            });
        }

        row.extracted_text = description;
        row.description = description;
        row.item_link = matched_item_id;
        row.quantity = parseFloat(item.quantity || 1);
        row.rate = parseFloat(item.unit_price || 0);
        row.amount = row.quantity * row.rate;

        if (item.tax_amount !== undefined && item.tax_amount !== null) {
            row.tax_amount = parseFloat(item.tax_amount);
        }
        if (item.total_with_tax !== undefined && item.total_with_tax !== null) {
            row.total_with_tax = parseFloat(item.total_with_tax);
        }
    });

    frm.refresh_field('items');
    update_totals(frm);
    frm.set_value('status', 'Ready');
    frm.save();

    console.log("✅ Form populated successfully");
}

function open_purchase_invoice_form(frm) {
    if (!frm.doc.supplier_link) {
        frappe.msgprint(__('Please select a supplier first'));
        return;
    }
    if (!frm.doc.items || frm.doc.items.length === 0) {
        frappe.msgprint(__('No items found in the extracted invoice'));
        return;
    }

    let unlinkedItems = [];
    frm.doc.items.forEach(function (item, index) {
        if (!item.item_link || item.item_link == " ") {
            unlinkedItems.push(__('Row') + ' ' + (index + 1) + ': ' + item.extracted_text);
        }
    });

    if (unlinkedItems.length > 0) {
        frappe.msgprint({
            title: __('Unlinked Items'),
            message: __('Please link the following items before creating invoice:') +
                     '<br><br>' + unlinkedItems.join('<br>'),
            indicator: 'orange'
        });
        return;
    }

    const items_data = (frm.doc.items || []).map(it => ({
        extracted_text: it.item_code || it.item_link || it.extracted_text || '',
        qty: parseFloat(it.quantity || 0),
        rate: parseFloat(it.rate || 0),
        amount: parseFloat(it.amount || 0)
    }));

    window.__extracted_items_data = items_data;
    window.__extracted_header = {
        supplier: frm.doc.supplier_link,
        bill_no: frm.doc.invoice_number,
        bill_date: frm.doc.invoice_date || frappe.datetime.get_today(),
        due_date: frm.doc.due_date || frappe.datetime.add_days(frappe.datetime.get_today(), 30),
        currency: frm.doc.currency || 'SAR',
        company: frappe.defaults.get_user_default("company") || '',
        subtotal: frm.doc.subtotal || 0,
        tax_amount: frm.doc.tax_amount || 0,
        total_amount: frm.doc.total_amount || 0
    };

    frappe.new_doc('Purchase Invoice').then(() => {
        const wait = setInterval(() => {
            if (cur_frm && cur_frm.doctype === 'Purchase Invoice') {
                clearInterval(wait);

                const hdr = window.__extracted_header || {};
                const data = window.__extracted_items_data || [];

                cur_frm.set_value('supplier', hdr.supplier);
                cur_frm.set_value('bill_no', hdr.bill_no);
                cur_frm.set_value('bill_date', hdr.bill_date);
                cur_frm.set_value('due_date', hdr.due_date);
                cur_frm.set_value('currency', hdr.currency);
                cur_frm.set_value('company', hdr.company);

                cur_frm.clear_table('items');

                data.forEach(d => {
                    const row = cur_frm.add_child('items');
                    row.item_code = d.extracted_text;
                    row.qty = d.qty;
                    row.rate = d.rate;
                    row.amount = d.amount;
                });

                cur_frm.refresh_field('items');

                if (hdr.tax_amount && hdr.tax_amount > 0) {
                    add_tax_actual_amount(cur_frm, hdr.tax_amount);
                }

                setTimeout(() => {
                    cur_frm.refresh();
                    cur_frm.cscript.calculate_taxes_and_totals();
                }, 500);

                delete window.__extracted_items_data;
                delete window.__extracted_header;
            }
        }, 100);
    });
}

function validate_tax_calculations(frm) {
    if (!frm.doc.name) {
        frappe.msgprint({
            title: __('Error'),
            message: __('Please save the document first'),
            indicator: 'red'
        });
        return;
    }

    frappe.call({
        method: 'invoice_extraction_app.api.validate_tax_calculations',
        args: {
            invoice_name: frm.doc.name
        },
        freeze: true,
        freeze_message: __('Validating tax calculations...'),
        callback: function (r) {
            if (r.message.success) {
                show_tax_validation_results(r.message);
            } else {
                frappe.msgprint({
                    title: __('Error'),
                    message: __('Validation failed: ') + r.message.error,
                    indicator: 'red'
                });
            }
        }
    });
}

function show_tax_validation_results(data) {
    const calculations = data.calculations;
    const validation = data.validation;
    const differences = data.differences;

    let message = `
    <div style="max-height: 400px; overflow-y: auto;">
        <h4>${__('Tax Validation Results')}</h4>

        <div class="row" style="margin-top: 15px;">
            <div class="col-md-6">
                <div class="panel panel-default">
                    <div class="panel-heading">
                        <h5>${__('From Items')}</h5>
                    </div>
                    <div class="panel-body">
                        <table class="table table-bordered">
                            <tr>
                                <td><strong>${__('Subtotal')}:</strong></td>
                                <td>${format_currency(calculations.from_items.subtotal)}</td>
                            </tr>
                            <tr>
                                <td><strong>${__('Tax Amount')}:</strong></td>
                                <td>${format_currency(calculations.from_items.tax_amount)}</td>
                            </tr>
                            <tr>
                                <td><strong>${__('Total Amount')}:</strong></td>
                                <td>${format_currency(calculations.from_items.total_amount)}</td>
                            </tr>
                        </table>
                    </div>
                </div>
            </div>

            <div class="col-md-6">
                <div class="panel panel-default">
                    <div class="panel-heading">
                        <h5>${__('From Extracted Data')}</h5>
                    </div>
                    <div class="panel-body">
                        <table class="table table-bordered">
                            <tr>
                                <td><strong>${__('Subtotal')}:</strong></td>
                                <td>${format_currency(calculations.from_extracted.subtotal)}</td>
                            </tr>
                            <tr>
                                <td><strong>${__('Tax Amount')}:</strong></td>
                                <td>${format_currency(calculations.from_extracted.tax_amount)}</td>
                            </tr>
                            <tr>
                                <td><strong>${__('Total Amount')}:</strong></td>
                                <td>${format_currency(calculations.from_extracted.total_amount)}</td>
                            </tr>
                            <tr>
                                <td><strong>${__('Tax Rate')}:</strong></td>
                                <td>${calculations.tax_rate_percentage}%</td>
                            </tr>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        <div class="panel ${validation.all_match ? 'panel-success' : 'panel-warning'}">
            <div class="panel-heading">
                <h5>${__('Validation Status')}</h5>
            </div>
            <div class="panel-body">
                <table class="table">
                    <tr>
                        <td><strong>${__('Subtotal Match')}:</strong></td>
                        <td>
                            ${validation.subtotal_match ?
                                '<span class="indicator green">✓ ' + __('Correct') + '</span>' :
                                '<span class="indicator red">✗ ' + __('Different') + '</span>'}
                            ${!validation.subtotal_match ?
                                '<span class="text-muted"> (' + __('Difference') + ': ' + format_currency(differences.subtotal_diff) + ')</span>' : ''}
                        </td>
                    </tr>
                    <tr>
                        <td><strong>${__('Tax Match')}:</strong></td>
                        <td>
                            ${validation.tax_match ?
                                '<span class="indicator green">✓ ' + __('Correct') + '</span>' :
                                '<span class="indicator red">✗ ' + __('Different') + '</span>'}
                            ${!validation.tax_match ?
                                '<span class="text-muted"> (' + __('Difference') + ': ' + format_currency(differences.tax_diff) + ')</span>' : ''}
                        </td>
                    </tr>
                    <tr>
                        <td><strong>${__('Total Match')}:</strong></td>
                        <td>
                            ${validation.total_match ?
                                '<span class="indicator green">✓ ' + __('Correct') + '</span>' :
                                '<span class="indicator red">✗ ' + __('Different') + '</span>'}
                            ${!validation.total_match ?
                                '<span class="text-muted"> (' + __('Difference') + ': ' + format_currency(differences.total_diff) + ')</span>' : ''}
                        </td>
                    </tr>
                </table>
            </div>
        </div>
    </div>

    <div class="text-center" style="margin-top: 15px;">
        <button class="btn btn-primary" onclick="fix_tax_calculation_global('${cur_frm.doc.name}')">
            ${__('Fix Tax Calculation')}
        </button>
    </div>
    `;

    frappe.msgprint({
        title: __('Tax Validation'),
        message: message,
        indicator: validation.all_match ? 'green' : 'orange',
        width: 800
    });
}

function fix_tax_calculation(frm) {
    if (!frm.doc.name) {
        frappe.msgprint(__('Please save the document first'));
        return;
    }

    frappe.call({
        method: 'invoice_extraction_app.api.fix_tax_calculation',
        args: { invoice_name: frm.doc.name },
        freeze: true,
        freeze_message: __('Fixing tax calculations...'),
        callback: function (r) {
            if (r.message.success) {
                frappe.show_alert({
                    message: __('✅ Tax calculations fixed successfully'),
                    indicator: 'green'
                });
                frm.reload_doc();
            } else {
                frappe.msgprint({
                    title: __('Error'),
                    message: __('Failed to fix tax calculations: ') + r.message.error,
                    indicator: 'red'
                });
            }
        }
    });
}

function fix_tax_calculation_global(invoice_name) {
    frappe.call({
        method: 'invoice_extraction_app.api.fix_tax_calculation',
        args: { invoice_name: invoice_name },
        callback: function (r) {
            if (r.message.success) {
                frappe.show_alert(__('✅ Tax calculations fixed'));
                cur_frm.reload_doc();
            }
        }
    });
}

// ============ دوال مساعدة ============
function update_item_row_total(frm, cdt, cdn) {
    const row = frappe.get_doc(cdt, cdn);
    if (row.quantity && row.rate) {
        row.amount = row.quantity * row.rate;
        frm.refresh_field('items');
    }
}

function update_item_totals(frm) {
    if (!frm.doc.items) return;

    frm.doc.items.forEach(function (item) {
        if (item.quantity && item.rate && !item.amount) {
            item.amount = item.quantity * item.rate;
        }
    });
    frm.refresh_field('items');
}

function update_totals(frm) {
    if (!frm.doc.items || frm.doc.items.length === 0) return;

    let subtotal = 0;
    let total_tax = 0;

    frm.doc.items.forEach(function (item) {
        const item_total = item.amount || (item.quantity * item.rate) || 0;
        subtotal += item_total;

        if (item.tax_amount) {
            total_tax += parseFloat(item.tax_amount);
        }
    });

    subtotal = parseFloat(subtotal.toFixed(2));
    total_tax = parseFloat(total_tax.toFixed(2));
    const total_amount = parseFloat((subtotal + total_tax).toFixed(2));

    frm.set_value('subtotal', subtotal);
    frm.set_value('tax_amount', total_tax);
    frm.set_value('total_amount', total_amount);
}

function add_tax_actual_amount(frm, tax_amount) {
    if (frm.doc.taxes && frm.doc.taxes.length > 0) {
        frm.clear_table('taxes');
    }

    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Account',
            filters: [
                ['account_type', '=', 'Tax'],
                ['company', '=', frm.doc.company],
                ['is_group', '=', 0]
            ],
            fields: ['name', 'account_name'],
            limit: 5
        },
        callback: function (r) {
            if (r.message && r.message.length > 0) {
                const tax_account = r.message[0].name;
                const tax_row = frm.add_child('taxes');

                tax_row.charge_type = "Actual";
                tax_row.account_head = tax_account;
                tax_row.description = `Tax Amount: ${format_currency(tax_amount)}`;
                tax_row.tax_amount = parseFloat(tax_amount);
                tax_row.total = parseFloat(tax_amount);
                tax_row.cost_center = frm.doc.cost_center || '';
                tax_row.add_deduct_tax = 'Add';
                tax_row.included_in_print_rate = 0;
                tax_row.dont_recompute_tax = 0;

                frm.refresh_field('taxes');

                frappe.show_alert({
                    message: __('✅ Tax amount added: ') + format_currency(tax_amount),
                    indicator: 'green'
                });
            } else {
                const tax_row = frm.add_child('taxes');
                tax_row.charge_type = "Actual";
                tax_row.description = `Tax Amount: ${format_currency(tax_amount)}`;
                tax_row.tax_amount = parseFloat(tax_amount);
                tax_row.total = parseFloat(tax_amount);
                tax_row.add_deduct_tax = 'Add';

                frm.refresh_field('taxes');
            }
        }
    });
}

function format_currency(amount) {
    if (amount === undefined || amount === null) return '0.00';
    const num = parseFloat(amount);
    return num.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}
