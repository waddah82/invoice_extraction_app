frappe.ui.form.on('Gemini Settings', {
    refresh: function(frm) {
        // Add test API button
        frm.add_custom_button(__('Test API Connection'), function() {
            if (!frm.doc.gemini_api_key) {
                frappe.msgprint(__('Please enter Gemini API Key first'));
                return;
            }
            
            frappe.call({
                method: 'frappe.client.save',
                args: {
                    doc: frm.doc
                },
                freeze: true,
                freeze_message: __('Testing API connection...'),
                callback: function(r) {
                    if (!r.exc) {
                        frappe.msgprint({
                            title: __('Success'),
                            message: __('API connection successful'),
                            indicator: 'green'
                        });
                    }
                }
            });
        }).addClass('btn-primary');
        
        // Add get API key button
        frm.add_custom_button(__('Get API Key'), function() {
            window.open('https://makersuite.google.com/app/apikey', '_blank');
        }).addClass('btn-default');
    }
});