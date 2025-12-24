import frappe
from frappe.model.document import Document
import google.generativeai as genai
import os

class GeminiSettings(Document):
    def validate(self):
        if self.gemini_api_key:
            self.test_api_key()
            
    def test_api_key(self):
        try:
            original_key = os.environ.get('GOOGLE_API_KEY')
            os.environ['GOOGLE_API_KEY'] = self.gemini_api_key
            
            genai.configure(api_key=self.gemini_api_key)
            models = genai.list_models()
            
            available_models = [m.name.split('/')[-1] for m in models 
                              if 'generateContent' in m.supported_generation_methods]
            
            # Check if selected model is available
            if self.selected_model not in available_models:
                frappe.msgprint(f"Selected model {self.selected_model} not available. Available: {', '.join(available_models[:3])}")
            
            if original_key:
                os.environ['GOOGLE_API_KEY'] = original_key
            else:
                del os.environ['GOOGLE_API_KEY']
                
            frappe.msgprint("API Key validated successfully")
            
        except Exception as e:
            frappe.throw(f"API Key validation failed: {str(e)}")