// invoice_extraction_app/mistral_settings/mistral_settings.js
frappe.ui.form.on('Mistral Settings', {
    refresh: function (frm) {
        // Add test connection button
        
        // Add documentation link
        frm.add_custom_button(__('API Documentation'), function () {
            window.open('https://docs.mistral.ai/', '_blank');
        });
    },

    selected_model: function (frm) {
        // Show model description
        var model_descriptions = {
            'mistral-large-latest': 'Most capable model for complex tasks',
            'mistral-medium-latest': 'Balanced model for general tasks',
            'mistral-small-latest': 'Fast and cost-effective for simple tasks',
            'open-mistral-7b': 'Open source 7B parameter model',
            'open-mixtral-8x7b': 'Open source mixture of experts model',
            'open-mixtral-8x22b': 'Largest open source mixture of experts model',
            'codestral-latest': 'Specialized for code generation'
        };

        var desc = model_descriptions[frm.doc.selected_model] || 'No description available';
        frm.set_df_property('selected_model', 'description', desc);
    }
});