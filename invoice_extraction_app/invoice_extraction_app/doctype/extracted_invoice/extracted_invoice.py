import frappe
from frappe.model.document import Document

class ExtractedInvoice(Document):
    def validate(self):
        self.validate_completion()
        self.calculate_item_amounts()
    
    def validate_completion(self):
        """Validate that all required data is complete"""
        if self.status == "Converted":
            return
            
        missing_fields = []
        
        if not self.supplier_name:
            missing_fields.append("Supplier Name")
        
        if not self.invoice_number:
            missing_fields.append("Invoice Number")
        
        if not self.invoice_date:
            missing_fields.append("Invoice Date")
        
        if not self.currency:
            missing_fields.append("Currency")
        
        # Check items
        if not self.items:
            missing_fields.append("Items")
        else:
            for item in self.items:
                if not item.item_name:
                    missing_fields.append(f"Item name in row {item.idx}")
                if item.quantity <= 0:
                    missing_fields.append(f"Quantity in row {item.idx}")
                if item.rate <= 0:
                    missing_fields.append(f"Rate in row {item.idx}")
        
        if missing_fields and self.status == "Ready":
            frappe.throw(f"Please complete the following fields: {', '.join(set(missing_fields))}")
    
    def calculate_item_amounts(self):
        """Calculate amount for each item"""
        for item in self.items:
            item.amount = item.quantity * item.rate
    
    def before_save(self):
        """Update status based on mapping"""
        if self.status != "Converted":
            if self.supplier_link:
                all_items_mapped = all(item.item_link for item in self.items)
                self.status = "Mapped" if all_items_mapped else "Ready"
            else:
                self.status = "Ready"