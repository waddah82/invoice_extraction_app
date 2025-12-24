frappe.ui.form.on('Extracted Invoice', {
    onload: function(frm) {
        console.log("📄 Form loaded");
        console.log("Document:", frm.doc.name);
        console.log("File exists:", !!frm.doc.original_file);
        
        // تهيئة متغير للأزرار
        window.extractedInvoiceButtons = window.extractedInvoiceButtons || [];
    },
    
    refresh: function(frm) {
        console.log("🔄 Form refresh started");
        
        // ============ إزالة الأزرار القديمة ============
        // إزالة الأزرار السابقة
        if (window.extractedInvoiceButtons && window.extractedInvoiceButtons.length > 0) {
            window.extractedInvoiceButtons.forEach(function(btn) {
                if (btn && btn.$wrapper) {
                    btn.$wrapper.remove();
                }
            });
            window.extractedInvoiceButtons = [];
        }
        
        // إزالة زر الاستخراج الرئيسي إن وجد
        //frm.page.remove_primary_action();
        
        // ============ زر استخراج البيانات ============
        if (frm.doc.original_file && frm.doc.status !== 'Converted') {
            console.log("✅ Adding Extract button");
            
            const extractBtn = frm.add_custom_button(__('🔍 Extract Data'), function() {
                extract_invoice_data(frm);
            }, __('Actions'));
            
            window.extractedInvoiceButtons.push(extractBtn);
            
            // إضافة زر استخراج كزر رئيسي أيضاً
            frm.page.set_primary_action(__('Extract Data'), function() {
                extract_invoice_data(frm);
            }, 'octicon octicon-file-text');
        }
        
        // ============ زر إنشاء فاتورة شراء ============
        const hasItems = frm.doc.items && frm.doc.items.length > 0;
        const hasSupplier = frm.doc.supplier_link;
        const canCreate = frm.doc.status === 'Ready' || (hasItems && hasSupplier);
        
        if (canCreate && frm.doc.status !== 'Converted') {
            console.log("✅ Adding Create Purchase Invoice button");
            
            const createBtn = frm.add_custom_button(__('🧾 Create Purchase Invoice'), function() {
                open_purchase_invoice_form(frm);
            }, __('Actions'));
            
            window.extractedInvoiceButtons.push(createBtn);
        }
        
        // ============ زر عرض فاتورة الشراء ============
        if (frm.doc.purchase_invoice_link) {
            console.log("✅ Adding View Purchase Invoice button");
            
            const viewBtn = frm.add_custom_button(__('📄 View Purchase Invoice'), function() {
                frappe.set_route('Form', 'Purchase Invoice', frm.doc.purchase_invoice_link);
            }, __('Actions'));
            
            window.extractedInvoiceButtons.push(viewBtn);
        }
        
        // ============ زر التحقق من الضريبة ============
        if (hasItems) {
            console.log("✅ Adding Validate Tax button");
            
            const validateBtn = frm.add_custom_button(__('🧮 Validate Tax'), function() {
                validate_tax_calculations(frm);
            }, __('Tools'));
            
            window.extractedInvoiceButtons.push(validateBtn);
        }
        
        // ============ تنسيق حالة الاستخراج ============
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
        
        // ============ عرض تفاصيل الضريبة ============
        
        
        console.log("✅ Form refresh completed. Buttons added:", window.extractedInvoiceButtons.length);
    },
    
    original_file: function(frm) {
        console.log("📁 File changed, refreshing...");
        // إعادة تحميل النموذج بعد تغيير الملف
        setTimeout(function() {
            frm.refresh();
        }, 300);
    },
    
    // تحديث عند تغيير الأصناف
    items_on_form_rendered: function(frm) {
        update_item_totals(frm);
    },
    
    // تحديث الحسابات عند تغيير القيم
    quantity: function(frm, cdt, cdn) {
        update_item_row_total(frm, cdt, cdn);
        update_totals(frm);
    },
    
    rate: function(frm, cdt, cdn) {
        update_item_row_total(frm, cdt, cdn);
        update_totals(frm);
    }
});




// دالة استخراج البيانات
function extract_invoice_data(frm) {
    if (!frm.doc.original_file) {
        frappe.msgprint(__('Please upload an invoice file first'));
        return;
    }
    
    frappe.call({
        method: 'invoice_extraction_app.api.extract_invoice_data_only',
        args: { file_url: frm.doc.original_file },
        freeze: true,
        freeze_message: __('Extracting invoice data...'),
        callback: function(r) {
            if (r.message.success) {
                populate_form_with_data(frm, r.message.data);
                frappe.show_alert(__('✅ Invoice data extracted successfully!'));
            } else {
                frappe.msgprint(__('Extraction failed: ') + r.message.error);
            }
        }
    });
}

// دالة ملء البيانات مع المطابقة التلقائية
function populate_form_with_data(frm, data) {
    console.log("📝 Populating form with data", data);
    
    // مسح الجدول القديم
    if (frm.doc.items && frm.doc.items.length > 0) {
        frm.clear_table('items');
    }
    
    // مطابقة المورد
    let matched_supplier_id = '';
    let matched_supplier_name = '';
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
            callback: function(r) {
                if (r.message && r.message.length > 0) {
                    matched_supplier_id = r.message[0].name;
                    matched_supplier_name = r.message[0].supplier_name;
                }
            }
        });
    }
    
    // ملء الحقول الرئيسية
    frm.set_value('supplier_name', data.supplier_ar || data.supplier || '');
    frm.set_value('supplier_link', matched_supplier_id);
    frm.set_value('invoice_number', data.invoice_number || '');
    frm.set_value('invoice_date', data.date || '');
    frm.set_value('due_date', data.due_date || '');
    frm.set_value('subtotal', data.subtotal || 0);
    frm.set_value('tax_amount', data.tax_amount || 0);
    frm.set_value('total_amount', data.total_amount || 0);
    frm.set_value('currency', data.currency || 'SAR');
    
    // إضافة الأصناف مع المطابقة
    const items = data.items || [];
    
    items.forEach(function(item, index) {
        const row = frm.add_child('items');
        const description = item.description_ar || item.description || __('Item') + ' ' + (index + 1);
        
        // مطابقة الصنف
        let matched_item_id = '';
        let matched_item_code = '';
        let matched_item_name = '';
        
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
                callback: function(r) {
                    if (r.message && r.message.length > 0) {
                        matched_item_id = r.message[0].name;
                        matched_item_code = r.message[0].item_code || '';
                        matched_item_name = r.message[0].item_name;
                    }
                }
            });
        }
        
        // تعيين قيم الصف
        row.item_name = description;
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

// دالة فتح نموذج فاتورة شراء جديد كامل
function open_purchase_invoice_form1(frm) {
    // التحقق من البيانات الأساسية
    if (!frm.doc.supplier_link) {
        frappe.msgprint(__('Please select a supplier first'));
        return;
    }
    
    if (!frm.doc.items || frm.doc.items.length === 0) {
        frappe.msgprint(__('No items found in the extracted invoice'));
        return;
    }
    
    // جمع بيانات الأصناف
    const items_data = [];
    frm.doc.items.forEach(function(item) {
        items_data.push({
            
            item_name: item.item_name,
           
            qty: item.quantity,
            rate: item.rate,
            amount: item.amount
           
        });
    });
    
    // حساب نسبة الضريبة
    let tax_rate = 15;
    if (frm.doc.subtotal && frm.doc.subtotal > 0 && frm.doc.tax_amount && frm.doc.tax_amount > 0) {
        tax_rate = (frm.doc.tax_amount / frm.doc.subtotal) * 100;
        tax_rate = Math.round(tax_rate * 100) / 100;
    }
    
    // الحصول على حساب الضريبة الافتراضي
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Account',
            filters: [
                ['account_type', '=', 'Tax'],
                ['company', '=', frappe.defaults.get_user_default("company")],
                ['is_group', '=', 0]
            ],
            fields: ['name'],
            limit: 1
        },
        callback: function(r) {
            let tax_account = '';
            if (r.message && r.message.length > 0) {
                tax_account = r.message[0].name;
            }
            
            // فتح نموذج فاتورة شراء جديد
            frappe.new_doc('Purchase Invoice', {
                // البيانات الأساسية
                supplier: frm.doc.supplier_link,
                supplier_name: frm.doc.supplier_name,
                bill_no: frm.doc.invoice_number,
                posting_date: frm.doc.invoice_date || frappe.datetime.get_today(),
                due_date: frm.doc.due_date || frappe.datetime.add_days(frappe.datetime.get_today(), 30),
                currency: frm.doc.currency || 'SAR',
                company: frappe.defaults.get_user_default("company") || '',
                
                // الأصناف
                items: items_data,
                
                // الضريبة
                taxes: frm.doc.tax_amount && frm.doc.tax_amount > 0 ? [{
                    charge_type: 'On Net Total',
                    account_head: tax_account || '',
                    description: `Tax ${tax_rate}%`,
                    rate: tax_rate
                }] : [],
                
                // إعدادات إضافية
                set_posting_time: 1,
                is_return: 0,
                apply_tds: 0,
                disable_rounded_total: 0,
                update_stock: 0 // افتراضي 0، المستخدم يحدد
            }).then(function(doc) {
                console.log("✅ Purchase Invoice form opened with extracted data");
                
                // إضافة حدث لحفظ الفاتورة لربطها
                doc.frm.cscript.save = function() {
                    const original_save = this._super;
                    return function() {
                        original_save.apply(this, arguments).then(function() {
                            // بعد الحفظ الناجح، ربط الفاتورة المستخرجة
                            if (doc.frm.doc.name) {
                                link_extracted_to_purchase_invoice(frm, doc.frm.doc.name);
                            }
                        });
                    };
                }(doc.frm.cscript.save);
            });
        }
    });
}
function open_purchase_invoice_form2(frm) {
    if (!frm.doc.supplier_link) {
        frappe.msgprint(__('Please select a supplier first'));
        return;
    }

    if (!frm.doc.items || frm.doc.items.length === 0) {
        frappe.msgprint(__('No items found in the extracted invoice'));
        return;
    }

    // جهّز بيانات الأصناف من Extracted Invoice
    const items_data = (frm.doc.items || []).map(it => ({
        // لازم يكون Item Code الحقيقي (أو اسم الصنف إذا نظامك يستخدمه ككود)
        item_code: it.item_code || it.item_link || '',
        qty: parseFloat(it.quantity || 0),
        rate: parseFloat(it.rate || 0)
    }));

    console.log("items_data to push:", items_data);

    // مرّر بيانات للفاتورة عبر route_options
    frappe.route_options = {
        supplier: frm.doc.supplier_link,
        bill_no: frm.doc.invoice_number,
        posting_date: frm.doc.invoice_date || frappe.datetime.get_today(),
        due_date: frm.doc.due_date || frappe.datetime.add_days(frappe.datetime.get_today(), 30),
        currency: frm.doc.currency || 'SAR',
        company: frappe.defaults.get_user_default("company") || '',
        __extracted_items_data: items_data,   // مفتاح خاص بنا
        __extracted_invoice_name: frm.doc.name
    };

    // افتح نموذج جديد
    frappe.new_doc('Purchase Invoice');

    // بعد ما يفتح النموذج فعليًا، أضف الصفوف
    const interval = setInterval(() => {
        if (cur_frm && cur_frm.doctype === 'Purchase Invoice' && cur_frm.is_new()) {
            clearInterval(interval);

            const data = frappe.route_options?.__extracted_items_data || [];
            if (!data.length) {
                console.log("No extracted items found in route_options");
                return;
            }

            // امسح أي صفوف افتراضية
            cur_frm.clear_table('items');

            data.forEach(d => {
                const row = cur_frm.add_child('items');
                row.item_name = d.item_name;
                row.qty = d.qty;
                row.rate = d.rate;
            });

            cur_frm.refresh_field('items');
            console.log("✅ Rows added to Purchase Invoice items table");
        }
    }, 200);
}


function open_purchase_invoice_form11111(frm) {
    if (!frm.doc.supplier_link) {
        frappe.msgprint(__('Please select a supplier first'));
        return;
    }
    if (!frm.doc.items || frm.doc.items.length === 0) {
        frappe.msgprint(__('No items found in the extracted invoice'));
        return;
    }

    const items_data = (frm.doc.items || []).map(it => ({
        // لاحظ: هذه "أسماء" وليست item_code حقيقي — سنعالجها تحت
        item_name: it.item_code || it.item_link || it.item_name || '',
        qty: parseFloat(it.quantity || 0),
        rate: parseFloat(it.rate || 0),
        amount: parseFloat(it.amount || 0)
    }));

    console.log("items_data to push:", items_data);

    // ✅ خزّن البيانات عالميًا بدل route_options
    window.__extracted_items_data = items_data;
    window.__extracted_header = {
        supplier: frm.doc.supplier_link,
        bill_no: frm.doc.invoice_number,
        bill_date: frm.doc.invoice_date || frappe.datetime.get_today(),
        due_date: frm.doc.due_date || frappe.datetime.add_days(frappe.datetime.get_today(), 30),
        currency: frm.doc.currency || 'SAR',
        company: frappe.defaults.get_user_default("company") || ''
    };

    frappe.new_doc('Purchase Invoice').then(() => {
        // انتظر لحد ما cur_frm يصير جاهز
        const wait = setInterval(() => {
            if (cur_frm && cur_frm.doctype === 'Purchase Invoice') {
                clearInterval(wait);

                const hdr = window.__extracted_header || {};
                const data = window.__extracted_items_data || [];

                console.log("Using cached extracted items:", data);

                // عبّي الرأس
                cur_frm.set_value('supplier', hdr.supplier);
                cur_frm.set_value('bill_no', hdr.bill_no);
                cur_frm.set_value('bill_date', hdr.bill_date);
                cur_frm.set_value('due_date', hdr.due_date);
                cur_frm.set_value('currency', hdr.currency);
                cur_frm.set_value('company', hdr.company);

                // امسح وأضف الأصناف
                cur_frm.clear_table('items');

                data.forEach(d => {
                    const row = cur_frm.add_child('items');
                    row.item_code = d.item_name;
                    row.qty = d.qty;
                    row.rate = d.rate;
                    row.amount = d.amount;
                });

                cur_frm.refresh_field('items');
                console.log("✅ Rows added to Purchase Invoice items table");

                // نظّف الكاش
                delete window.__extracted_items_data;
                delete window.__extracted_header;
            }
        }, 100);
    });
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
    frm.doc.items.forEach(function(item, index) {
        if (!item.item_link) {
            unlinkedItems.push(__('Row') + ' ' + (index + 1) + ': ' + item.item_name);
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
        item_name: it.item_code || it.item_link || it.item_name || '',
        qty: parseFloat(it.quantity || 0),
        rate: parseFloat(it.rate || 0),
        amount: parseFloat(it.amount || 0)
    }));

    console.log("items_data to push:", items_data);

    // ✅ خزّن البيانات عالميًا بدل route_options
    window.__extracted_items_data = items_data;
    window.__extracted_header = {
        supplier: frm.doc.supplier_link,
        bill_no: frm.doc.invoice_number,
        bill_date: frm.doc.invoice_date || frappe.datetime.get_today(),
        due_date: frm.doc.due_date || frappe.datetime.add_days(frappe.datetime.get_today(), 30),
        currency: frm.doc.currency || 'SAR',
        company: frappe.defaults.get_user_default("company") || '',
        // إضافة بيانات الضريبة
        subtotal: frm.doc.subtotal || 0,
        tax_amount: frm.doc.tax_amount || 0,
        total_amount: frm.doc.total_amount || 0
    };

    frappe.new_doc('Purchase Invoice').then(() => {
        // انتظر لحد ما cur_frm يصير جاهز
        const wait = setInterval(() => {
            if (cur_frm && cur_frm.doctype === 'Purchase Invoice') {
                clearInterval(wait);

                const hdr = window.__extracted_header || {};
                const data = window.__extracted_items_data || [];

                console.log("Using cached extracted items:", data);
                console.log("Tax data:", {
                    subtotal: hdr.subtotal,
                    tax_amount: hdr.tax_amount,
                    total_amount: hdr.total_amount
                });

                // عبّي الرأس
                cur_frm.set_value('supplier', hdr.supplier);
                cur_frm.set_value('bill_no', hdr.bill_no);
                cur_frm.set_value('bill_date', hdr.bill_date);
                cur_frm.set_value('due_date', hdr.due_date);
                cur_frm.set_value('currency', hdr.currency);
                cur_frm.set_value('company', hdr.company);

                // امسح وأضف الأصناف
                cur_frm.clear_table('items');

                data.forEach(d => {
                    const row = cur_frm.add_child('items');
                    row.item_code = d.item_name;
                    row.qty = d.qty;
                    row.rate = d.rate;
                    row.amount = d.amount;
                });

                cur_frm.refresh_field('items');
                console.log("✅ Rows added to Purchase Invoice items table");

                // 1. إضافة الضريبة الإجمالية إذا كانت موجودة
                if (hdr.tax_amount && hdr.tax_amount > 0) {
                    add_tax_actual_amount(cur_frm, hdr.tax_amount);
                }

                // 2. تحديث الحسابات
                setTimeout(() => {
                    cur_frm.refresh();
                    cur_frm.cscript.calculate_taxes_and_totals();
                    console.log("✅ Tax calculations updated");
                }, 500);

                // نظّف الكاش
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
        callback: function(r) {
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
        <button class="btn btn-primary" onclick="fix_tax_calculation('${cur_frm.doc.name}')">
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


// دالة لإضافة الضريبة باستخدام charge_type: "Actual"
function add_tax_actual_amount(frm, tax_amount) {
    console.log("Adding tax with actual amount:", tax_amount);
    
    // مسح أي ضريبة موجودة مسبقاً
    if (frm.doc.taxes && frm.doc.taxes.length > 0) {
        frm.clear_table('taxes');
    }
    
    // الحصول على حساب الضريبة الافتراضي
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
        callback: function(r) {
            if (r.message && r.message.length > 0) {
                const tax_account = r.message[0].name;
                const tax_account_name = r.message[0].account_name;
                
                // إضافة سطر الضريبة باستخدام charge_type: "Actual"
                const tax_row = frm.add_child('taxes');
                
                // تعيين الحقول المطلوبة
                tax_row.charge_type = "Actual";
                tax_row.account_head = tax_account;
                tax_row.description = `Tax Amount: ${format_currency(tax_amount)}`;
                tax_row.tax_amount = parseFloat(tax_amount);
                tax_row.total = parseFloat(tax_amount);
                
                // الحقول الاختيارية
                tax_row.cost_center = frm.doc.cost_center || '';
                tax_row.add_deduct_tax = 'Add';
                tax_row.included_in_print_rate = 0;
                tax_row.dont_recompute_tax = 0;
                
                console.log("✅ Tax row added with actual amount:", tax_row);
                
                frm.refresh_field('taxes');
                
                // عرض تأكيد
                frappe.show_alert({
                    message: __('✅ Tax amount added: ') + format_currency(tax_amount),
                    indicator: 'green'
                });
                
                // عرض ملخص الضريبة
                show_tax_summary(frm, tax_amount, tax_account_name);
                
            } else {
                console.warn("⚠️ No tax account found");
                frappe.show_alert({
                    message: __('No tax account found. Tax amount will be added without account.'),
                    indicator: 'orange'
                });
                
                // إضافة الضريبة بدون حساب (لتجنب الخطأ)
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
function update_item_row_total(frm, cdt, cdn) {
    const row = frappe.get_doc(cdt, cdn);
    if (row.quantity && row.rate) {
        row.amount = row.quantity * row.rate;
        frm.refresh_field('items');
    }
}

function update_item_totals(frm) {
    if (!frm.doc.items) return;
    
    frm.doc.items.forEach(function(item) {
        if (item.quantity && item.rate && !item.amount) {
            item.amount = item.quantity * item.rate;
        }
    });
    frm.refresh_field('items');
}

function update_totals(frm) {
    if (!frm.doc.items || frm.doc.items.length === 0) return;
    
    // حساب الإجماليات
    let subtotal = 0;
    let total_tax = 0;
    
    frm.doc.items.forEach(function(item) {
        const item_total = item.amount || (item.quantity * item.rate) || 0;
        subtotal += item_total;
        
        if (item.tax_amount) {
            total_tax += parseFloat(item.tax_amount);
        }
    });
    
    subtotal = parseFloat(subtotal.toFixed(2));
    total_tax = parseFloat(total_tax.toFixed(2));
    const total_amount = parseFloat((subtotal + total_tax).toFixed(2));
    
    // تحديث القيم
    frm.set_value('subtotal', subtotal);
    frm.set_value('tax_amount', total_tax);
    frm.set_value('total_amount', total_amount);
}

// دالة لعرض ملخص الضريبة
function show_tax_summary(frm, tax_amount, tax_account_name) {
    // حساب subtotal من الأصناف
    let subtotal = 0;
    if (frm.doc.items && frm.doc.items.length > 0) {
        frm.doc.items.forEach(item => {
            subtotal += (item.qty * item.rate);
        });
    }
    
    const tax_percentage = subtotal > 0 ? (tax_amount / subtotal * 100).toFixed(2) : '0.00';
    
    const dialog = new frappe.ui.Dialog({
        title: __('Tax Summary'),
        fields: [
            {
                fieldname: 'summary',
                fieldtype: 'HTML',
                options: `
                    <div style="padding: 15px;">
                        <div class="alert alert-success">
                            <i class="fa fa-check-circle"></i>
                            <strong>${__('Tax Added Successfully')}</strong>
                        </div>
                        
                        <table class="table table-bordered" style="margin-top: 15px;">
                            <tr>
                                <td width="40%"><strong>${__('Tax Type')}</strong></td>
                                <td>Actual Amount</td>
                            </tr>
                            <tr>
                                <td><strong>${__('Tax Amount')}</strong></td>
                                <td><strong class="text-primary">${format_currency(tax_amount)}</strong></td>
                            </tr>
                            <tr>
                                <td><strong>${__('Tax Percentage')}</strong></td>
                                <td>${tax_percentage}%</td>
                            </tr>
                            <tr>
                                <td><strong>${__('Subtotal (from items)')}</strong></td>
                                <td>${format_currency(subtotal)}</td>
                            </tr>
                            <tr>
                                <td><strong>${__('Total with Tax')}</strong></td>
                                <td><strong class="text-success">${format_currency(subtotal + parseFloat(tax_amount))}</strong></td>
                            </tr>
                            <tr>
                                <td><strong>${__('Tax Account')}</strong></td>
                                <td>${tax_account_name || 'Not specified'}</td>
                            </tr>
                        </table>
                        
                        <div class="alert alert-info" style="margin-top: 15px;">
                            <i class="fa fa-info-circle"></i>
                            ${__('You can modify the tax details in the Taxes table below.')}
                        </div>
                    </div>
                `
            }
        ],
        size: 'medium',
        primary_action_label: __('Close'),
        primary_action: function() {
            dialog.hide();
        }
    });
    
    dialog.show();
}

// دالة مساعدة لتنسيق العملة
function format_currency(amount) {
    if (amount === undefined || amount === null) return '0.00';
    const num = parseFloat(amount);
    return num.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

// إضافة زر يدوي لإضافة الضريبة
frappe.ui.form.on('Purchase Invoice', {
    onload: function(frm) {
        // التحقق إذا كانت الفاتورة من فاتورة مستخرجة
        if (window.__extracted_items_data && frm.is_new()) {
            console.log("Loading extracted invoice data...");
            
            // إضافة زر لإضافة الضريبة يدوياً
            frm.add_custom_button(__('💰 Add Tax Amount'), function() {
                add_tax_manually(frm);
            }, __('Tools'));
        }
    },
    
    refresh: function(frm) {
        // إضافة زر لإضافة/تعديل الضريبة
        if (frm.is_new()) {
            frm.add_custom_button(__('🧾 Add/Edit Tax'), function() {
                add_tax_manually(frm);
            }, __('Tools'));
        }
    }
});

// دالة لإضافة الضريبة يدوياً
function add_tax_manually(frm) {
    // الحصول على الضريبة الحالية إن وجدت
    let current_tax = 0;
    if (frm.doc.taxes && frm.doc.taxes.length > 0) {
        current_tax = frm.doc.taxes[0].tax_amount || 0;
    }
    
    frappe.prompt([
        {
            fieldname: 'tax_amount',
            fieldtype: 'Currency',
            label: __('Tax Amount'),
            default: current_tax || '',
            reqd: 1
        },
        {
            fieldname: 'description',
            fieldtype: 'Data',
            label: __('Description'),
            default: 'VAT',
            reqd: 0
        }
    ], function(values) {
        if (!values.tax_amount || parseFloat(values.tax_amount) <= 0) {
            frappe.msgprint(__('Please enter a valid tax amount'));
            return;
        }
        
        // مسح الضرائب القديمة
        if (frm.doc.taxes && frm.doc.taxes.length > 0) {
            frm.clear_table('taxes');
        }
        
        // إضافة الضريبة الجديدة
        const tax_row = frm.add_child('taxes');
        tax_row.charge_type = "Actual";
        tax_row.description = values.description || `Tax: ${format_currency(values.tax_amount)}`;
        tax_row.tax_amount = parseFloat(values.tax_amount);
        tax_row.total = parseFloat(values.tax_amount);
        tax_row.add_deduct_tax = 'Add';
        
        // الحصول على حساب الضريبة
        frappe.call({
            method: 'frappe.client.get_list',
            args: {
                doctype: 'Account',
                filters: [
                    ['account_type', '=', 'Tax'],
                    ['company', '=', frm.doc.company],
                    ['is_group', '=', 0]
                ],
                fields: ['name'],
                limit: 1
            },
            callback: function(r) {
                if (r.message && r.message.length > 0) {
                    tax_row.account_head = r.message[0].name;
                }
                
                frm.refresh_field('taxes');
                frm.cscript.calculate_taxes_and_totals();
                
                frappe.show_alert({
                    message: __('Tax amount added successfully'),
                    indicator: 'green'
                });
            }
        });
        
    }, __('Add Tax Amount'), __('Add'));
}



// دالة ربط الفاتورة المستخرجة بفاتورة الشراء
function link_extracted_to_purchase_invoice(frm, purchase_invoice_name) {
    frappe.call({
        method: 'invoice_extraction_app.api.link_to_purchase_invoice',
        args: {
            extracted_invoice_name: frm.doc.name,
            purchase_invoice_name: purchase_invoice_name
        },
        callback: function(r) {
            if (r.message.success) {
                frappe.show_alert({
                    message: __('✅ Purchase invoice linked successfully'),
                    indicator: 'green'
                });
                frm.reload_doc();
            }
        }
    });
}

// ============ كود إضافي للتحسين ============

// عند النقر على حقل الصنف في الجدول، فتح بحث
$(document).on('click', '[data-fieldname="item_name"] input', function() {
    const $row = $(this).closest('[data-idx]');
    const idx = $row.attr('data-idx');
    const frm = cur_frm;
    
    if (frm && idx && frm.doctype === 'Extracted Invoice') {
        const grid = frm.fields_dict.items.grid;
        const row = grid.grid_rows_by_docname[idx];
        
        if (row && row.doc.item_name) {
            frappe.prompt({
                fieldtype: 'Data',
                label: __('Search Item'),
                fieldname: 'item_search',
                default: row.doc.item_name,
                reqd: 1
            }, function(values) {
                search_and_select_item(values.item_search, idx);
            }, __('Search Item'), __('Search'));
        }
    }
});

function search_and_select_item(item_name, row_idx) {
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Item',
            filters: [['item_name', 'like', `%${item_name}%`]],
            fields: ['name', 'item_name', 'item_code', 'stock_uom'],
            limit: 20
        },
        callback: function(r) {
            if (r.message && r.message.length > 0) {
                const dialog = new frappe.ui.Dialog({
                    title: __('Select Item'),
                    fields: [
                        {
                            fieldname: 'items_list',
                            fieldtype: 'HTML',
                            options: get_items_html(r.message)
                        }
                    ]
                });
                
                dialog.show();
                
                dialog.$wrapper.on('click', '.item-option', function() {
                    const item_id = $(this).data('item-id');
                    const item_name = $(this).data('item-name');
                    const item_code = $(this).data('item-code');
                    
                    if (cur_frm) {
                        const grid = cur_frm.fields_dict.items.grid;
                        const row = grid.grid_rows_by_docname[row_idx];
                        
                        if (row) {
                            row.doc.item_link = item_id;
                            row.doc.item_name = item_name;
                            row.doc.item_code = item_code;
                            grid.refresh();
                            
                            frappe.show_alert(__('✅ Item selected'));
                        }
                    }
                    
                    dialog.hide();
                });
            }
        }
    });
}

function get_items_html(items) {
    let html = `
        <div style="max-height: 300px; overflow-y: auto;">
            <div class="list-group">
    `;
    
    items.forEach(function(item) {
        html += `
            <div class="list-group-item item-option" 
                 data-item-id="${item.name}"
                 data-item-name="${item.item_name.replace(/'/g, "\\'")}"
                 data-item-code="${item.item_code || ''}"
                 style="cursor: pointer; padding: 10px; margin-bottom: 5px;">
                <strong>${item.item_name}</strong>
                ${item.item_code ? `<div class="small text-muted">Code: ${item.item_code}</div>` : ''}
                ${item.stock_uom ? `<div class="small text-muted">UOM: ${item.stock_uom}</div>` : ''}
            </div>
        `;
    });
    
    html += `
            </div>
        </div>
    `;
    
    return html;
}
