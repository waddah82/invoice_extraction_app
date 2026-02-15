import frappe
from frappe.model.document import Document

class MistralSettings(Document):
    def validate(self):
        """Validate Mistral Settings"""
        # Ensure temperature is within valid range
        if self.temperature < 0 or self.temperature > 1:
            frappe.throw("Temperature must be between 0 and 1")
        
        # Validate JSON format
        if self.json_format:
            try:
                import json
                # Test if it's valid JSON by trying to parse a sample
                test_json = self.json_format.replace("اسم المورد", "test")
                test_json = test_json.replace("YYYY-MM-DD", "2024-01-01")
                test_json = test_json.replace("الكمية", "1")
                test_json = test_json.replace("سعر الوحدة", "100")
                json.loads(test_json)
            except json.JSONDecodeError as e:
                frappe.throw(f"Invalid JSON format: {str(e)}")
        
        # Log change
        frappe.logger().info(f"Mistral Settings updated by {frappe.session.user}")

    def get_api_config(self):
        """Get API configuration"""
        return {
            'api_key': self.get_password('mistral_api_key'),
            'model': self.selected_model,
            'temperature': self.temperature
        }

    def get_prompt_config(self):
        """Get prompt configuration"""
        return {
            'system_instruction': self.system_instruction,
            'json_format': self.json_format,
            'prompt_instructions': self.prompt_instructions
        }

@frappe.whitelist()
def get_mistral_settings():
    """Get Mistral settings for frontend"""
    if frappe.db.exists("Mistral Settings", "Mistral Settings"):
        settings = frappe.get_doc("Mistral Settings", "Mistral Settings")
        return {
            'model': settings.selected_model,
            'temperature': settings.temperature,
            'has_api_key': bool(settings.get_password('mistral_api_key')),
            'debug_enabled': settings.enable_debug_log
        }
    return None

@frappe.whitelist()
def test_mistral_connection():
    """Test connection to Mistral API"""
    try:
        if not frappe.db.exists("Mistral Settings", "Mistral Settings"):
            return {
                "success": False,
                "error": "Mistral Settings not found"
            }
        
        settings = frappe.get_doc("Mistral Settings", "Mistral Settings")
        api_key = settings.get_password('mistral_api_key')
        
        if not api_key:
            return {
                "success": False,
                "error": "API Key not set"
            }
        
        from mistralai import Mistral
        
        # Initialize client with test call
        client = Mistral(api_key=api_key)
        
        # Try to list available models (lightweight API call)
        models = client.models.list()
        
        return {
            "success": True,
            "message": f"Connected successfully. Available models: {len(models.data)}",
            "models": [model.id for model in models.data[:5]]  # Show first 5 models
        }
        
    except Exception as e:
        frappe.log_error(f"Mistral connection test failed: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }