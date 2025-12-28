# invoice_extraction_app/api.py
import frappe
import json
import os
from frappe import _
from frappe.utils import now
import google.generativeai as genai
import traceback
from PIL import Image
import io

@frappe.whitelist()
def extract_invoice_data_only(file_url: str) -> dict:
    """
    ط§ط³طھط®ط±ط§ط¬ ط§ظ„ط¨ظٹط§ظ†ط§طھ ظ…ظ† ط§ظ„ظ…ظ„ظپ ظˆط¥ط±ط¬ط§ط¹ظ‡ط§ ظپظ‚ط· (ط¨ط¯ظˆظ† ط¥ظ†ط´ط§ط، ط³ط¬ظ„)
    """
    try:
        # ط§ظ„طھط­ظ‚ظ‚ ظ…ظ† ظˆط¬ظˆط¯ Gemini Settings
        if not frappe.db.exists("Gemini Settings", "Gemini Settings"):
            return {
                "success": False,
                "error": "Gemini Settings not found. Please create it first."
            }
        
        settings = frappe.get_single("Gemini Settings")
        
        if not settings.gemini_api_key:
            return {
                "success": False,
                "error": "Gemini API Key not set. Please add it in Gemini Settings."
            }
        
        # طھظƒظˆظٹظ† Gemini
        genai.configure(api_key=settings.gemini_api_key)
        
        # ظ‚ط±ط§ط،ط© ط§ظ„ظ…ظ„ظپ
        file_doc = frappe.get_doc("File", {"file_url": file_url})
        file_path = file_doc.get_full_path()
        
        with open(file_path, 'rb') as f:
            file_bytes = f.read()
        
        file_ext = os.path.splitext(file_path)[1].lower()
        
        # ط§ط³طھط®ط±ط§ط¬ ط§ظ„ط¨ظٹط§ظ†ط§طھ
        result = extract_with_gemini_frappe(
            file_bytes=file_bytes,
            file_ext=file_ext,
            model_name=settings.selected_model,
            temperature=settings.temperature,
            settings=settings
        )
        
        if not result.get("success"):
            return {
                "success": False,
                "error": result.get("error", "Extraction failed")
            }
        
        extracted_data = result.get("data", {})
        
        # ط¥ط±ط¬ط§ط¹ ط§ظ„ط¨ظٹط§ظ†ط§طھ ظپظ‚ط· (ط¨ط¯ظˆظ† ط¥ظ†ط´ط§ط، ط³ط¬ظ„)
        return {
            "success": True,
            "data": extracted_data,
            "model_used": settings.selected_model,
            "extraction_time": now()
        }
        
    except Exception as e:
        frappe.log_error(f"Extraction error: {str(e)}", "Invoice Extraction")
        return {
            "success": False,
            "error": str(e)
        }

def extract_with_gemini_frappe(file_bytes: bytes, file_ext: str, model_name: str, 
                               temperature: float, settings) -> dict:
    """
    ط§ط³طھط®ط±ط§ط¬ ط§ظ„ط¨ظٹط§ظ†ط§طھ ط¨ط§ط³طھط®ط¯ط§ظ… Gemini ظ…ط¹ ط¥ط¹ط¯ط§ط¯ط§طھ ظ‚ط§ط¨ظ„ط© ظ„ظ„طھط®طµظٹطµ
    """
    try:
        # طھط­ط¯ظٹط¯ ظ†ظˆط¹ MIME
        if file_ext == '.pdf':
            mime_type = "application/pdf"
        elif file_ext in ['.jpg', '.jpeg']:
            mime_type = "image/jpeg"
        elif file_ext == '.png':
            mime_type = "image/png"
        else:
            return {
                "success": False,
                "error": f"Unsupported file type: {file_ext}"
            }
        
        # ط§ط®طھظٹط§ط± ط§ظ„ظ†ظ…ظˆط°ط¬
        model = genai.GenerativeModel(model_name)
        
        # ط§ط³طھط®ط¯ط§ظ… ط§ظ„طھط¹ظ„ظٹظ…ط§طھ ظ…ظ† Gemini Settings
        system_instruction = getattr(settings, 'system_instruction', 
            "ط£ظ†طھ ظ…طھط®طµطµ ظپظٹ ط§ط³طھط®ط±ط§ط¬ ط§ظ„ط¨ظٹط§ظ†ط§طھ ظ…ظ† ظپظˆط§طھظٹط± ط§ظ„ط´ط±ط§ط،. ط§ط³طھط®ط±ط¬ ط§ظ„ط¨ظٹط§ظ†ط§طھ ط¨ط¯ظ‚ط© ظ…ط¹ ط§ظ„طھط±ظƒظٹط² ط¹ظ„ظ‰ طھظپط§طµظٹظ„ ط§ظ„ط¶ط±ط§ط¦ط¨ ظˆط§ظ„ط­ط³ط§ط¨ط§طھ ط§ظ„ظ…ط§ظ„ظٹط©.")
        
        json_format = getattr(settings, 'json_format', """{
    "supplier": "ط§ط³ظ… ط§ظ„ظ…ظˆط±ط¯",
    "supplier_ar": "ط§ط³ظ… ط§ظ„ظ…ظˆط±ط¯ ط¨ط§ظ„ط¹ط±ط¨ظٹط©",
    "invoice_number": "ط±ظ‚ظ… ط§ظ„ظپط§طھظˆط±ط©",
    "date": "طھط§ط±ظٹط® ط§ظ„ظپط§طھظˆط±ط© (YYYY-MM-DD)",
    "due_date": "طھط§ط±ظٹط® ط§ظ„ط§ط³طھط­ظ‚ط§ظ‚ (YYYY-MM-DD)",
    "subtotal": "ط§ظ„ظ…ط¨ظ„ط؛ ظ‚ط¨ظ„ ط§ظ„ط¶ط±ظٹط¨ط©",
    "tax_amount": "ظ…ط¨ظ„ط؛ ط§ظ„ط¶ط±ظٹط¨ط© ط§ظ„ط¥ط¬ظ…ط§ظ„ظٹ",
    "total_amount": "ط§ظ„ظ…ط¨ظ„ط؛ ط§ظ„ط¥ط¬ظ…ط§ظ„ظٹ ط¨ط¹ط¯ ط§ظ„ط¶ط±ظٹط¨ط©",
    "currency": "ط§ظ„ط¹ظ…ظ„ط©",
    "items": [
        {
            "description": "ظˆطµظپ ط§ظ„طµظ†ظپ",
            "description_ar": "ظˆطµظپ ط§ظ„طµظ†ظپ ط¨ط§ظ„ط¹ط±ط¨ظٹط©",
            "quantity": ط§ظ„ظƒظ…ظٹط©,
            "unit_price": ط³ط¹ط± ط§ظ„ظˆط­ط¯ط©,
            "item_total": "ط§ظ„ظ…ط¨ظ„ط؛ ط§ظ„ط¥ط¬ظ…ط§ظ„ظٹ ظ„ظ„طµظ†ظپ (ط§ظ„ظƒظ…ظٹط© أ— ط§ظ„ط³ط¹ط±)",
            "tax_amount": "ظ…ط¨ظ„ط؛ ط§ظ„ط¶ط±ظٹط¨ط© ظ„ظ„طµظ†ظپ",
            "total_with_tax": "ط§ظ„ظ…ط¨ظ„ط؛ ط§ظ„ط¥ط¬ظ…ط§ظ„ظٹ ظ„ظ„طµظ†ظپ ط¨ط¹ط¯ ط§ظ„ط¶ط±ظٹط¨ط©"
        }
    ]
}""")
        
        prompt_instructions = getattr(settings, 'prompt_instructions', 
            """**ط§ظ„ظ‚ظˆط§ط¹ط¯ ط§ظ„ظ…ظ‡ظ…ط© ط¨ط§ظ„طھط±طھظٹط¨:**

1. **ط§ط³طھط®ط±ط§ط¬ ط§ظ„ط¶ط±ظٹط¨ط©:**
   - ط§ط³طھط®ط±ط¬ `tax_amount` (ظ…ط¨ظ„ط؛ ط§ظ„ط¶ط±ظٹط¨ط©) ظپظ‚ط· - ظ„ط§ ط­ط§ط¬ط© ظ„ظ†ط³ط¨ط© ط§ظ„ط¶ط±ظٹط¨ط©
   - ط¥ط°ط§ ظƒط§ظ†طھ ط§ظ„ظپط§طھظˆط±ط© طھط­طھظˆظٹ ط¹ظ„ظ‰ ط¶ط±ظٹط¨ط©: ط§ط³طھط®ط±ط¬ `tax_amount` ظƒظ‚ظٹظ…ط© ط±ظ‚ظ…ظٹط©
   - ط¥ط°ط§ ظ„ظ… طھظƒظ† ظ‡ظ†ط§ظƒ ط¶ط±ظٹط¨ط©: ط¶ط¹ `tax_amount = 0`

2. **ط§ط³طھط®ط±ط§ط¬ ط§ظ„ط£طµظ†ط§ظپ:**
   - ظ„ظƒظ„ طµظ†ظپطŒ ط§ط³طھط®ط±ط¬:
     - `tax_amount` ظ„ظ„طµظ†ظپ (ظ…ط¨ظ„ط؛ ط§ظ„ط¶ط±ظٹط¨ط© ظ„ظ‡ط°ط§ ط§ظ„طµظ†ظپ ظپظ‚ط·)
     - `item_total` (ط§ظ„ظƒظ…ظٹط© أ— ط³ط¹ط± ط§ظ„ظˆط­ط¯ط©)
     - `total_with_tax` (item_total + tax_amount ظ„ظ„طµظ†ظپ)
   - ط¥ط°ط§ ظ„ظ… ظٹظƒظ† ط§ظ„طµظ†ظپ ط®ط§ط¶ط¹ ظ„ظ„ط¶ط±ظٹط¨ط©: `tax_amount = 0` ظ„ظ„طµظ†ظپ
   - `total_with_tax` ظٹط¬ط¨ ط£ظ† ظٹط³ط§ظˆظٹ `item_total + tax_amount` ظ„ظƒظ„ طµظ†ظپ

3. **ط­ط³ط§ط¨ ط§ظ„ط¥ط¬ظ…ط§ظ„ظٹط§طھ:**
   - `subtotal` = ظ…ط¬ظ…ظˆط¹ `item_total` ظ„ط¬ظ…ظٹط¹ ط§ظ„ط£طµظ†ط§ظپ
   - `tax_amount` (ظ„ظ„ط¥ط¬ظ…ط§ظ„ظٹ) = ظ…ط¬ظ…ظˆط¹ `tax_amount` ظ„ط¬ظ…ظٹط¹ ط§ظ„ط£طµظ†ط§ظپ
   - `total_amount` = `subtotal + tax_amount` (ظ„ظ„ط¥ط¬ظ…ط§ظ„ظٹ)
   - ط¥ط°ط§ ظƒط§ظ† `total_amount` ظ†ط§ظ‚طµط§ظ‹: ط§ط­ط³ط¨ظ‡ = `subtotal + tax_amount`

4. **ط§ظ„طھط­ظ‚ظ‚ ظ…ظ† ط§ظ„ط­ط³ط§ط¨ط§طھ:**
   - طھط£ظƒط¯ ط£ظ†: ظ…ط¬ظ…ظˆط¹ `item_total` ظ„ط¬ظ…ظٹط¹ ط§ظ„ط£طµظ†ط§ظپ â‰ˆ `subtotal`
   - طھط£ظƒط¯ ط£ظ†: ظ…ط¬ظ…ظˆط¹ `tax_amount` ظ„ط¬ظ…ظٹط¹ ط§ظ„ط£طµظ†ط§ظپ â‰ˆ `tax_amount` ظ„ظ„ط¥ط¬ظ…ط§ظ„ظٹ
   - طھط£ظƒط¯ ط£ظ†: `total_amount` = `subtotal + tax_amount`

5. **ط§ظ„طھظ†ط³ظٹظ‚:**
   - ط§ظ„طھظˆط§ط±ظٹط®: YYYY-MM-DD
   - ط§ظ„ط¹ظ…ظ„ط©: SAR ط£ظˆ USD ط£ظˆ EUR (ط§ظ„ط±ظ…ط² ظپظ‚ط·)
   - ط§ظ„ط£ط±ظ‚ط§ظ…: ظ‚ظٹظ… ط±ظ‚ظ…ظٹط© ظپظ‚ط· (ط¨ط¯ظˆظ† ط±ظ…ظˆط² ط§ظ„ط¹ظ…ظ„ط©)

**ط³ظٹظ†ط§ط±ظٹظˆظ‡ط§طھ ط®ط§طµط©:**
1. ط¥ط°ط§ ظƒط§ظ†طھ ط§ظ„ط¶ط±ظٹط¨ط© ظ…ظˆط¶ط­ط© ظƒظ‚ظٹظ…ط© ط¥ط¬ظ…ط§ظ„ظٹط© ظپظ‚ط·: ظˆط²ط¹ظ‡ط§ ط¹ظ„ظ‰ ط§ظ„ط£طµظ†ط§ظپ طھظ†ط§ط³ط¨ظٹط§ظ‹
2. ط¥ط°ط§ ظƒط§ظ†طھ ط§ظ„ط¶ط±ظٹط¨ط© ظ…ظˆط¶ط­ط© ظ„ظƒظ„ طµظ†ظپ: ط§ط³طھط®ط¯ظ… ط§ظ„ظ‚ظٹظ… ظƒظ…ط§ ظ‡ظٹ
3. ط¥ط°ط§ ظ„ظ… طھط¸ظ‡ط± ط§ظ„ط¶ط±ظٹط¨ط© ظپظٹ ط§ظ„ظپط§طھظˆط±ط©: `tax_amount = 0` ظ„ظ„ط¬ظ…ظٹط¹
4. ط¥ط°ط§ ظƒط§ظ† ظ‡ظ†ط§ظƒ ط®طµظ…: ط£ط¶ظپظ‡ ظƒطµظ†ظپ ظ…ظ†ظپطµظ„ ط£ظˆ ط§ط·ط±ط­ظ‡ ظ…ظ† subtotal

**ظ‡ط§ظ… ط¬ط¯ط§ظ‹:** 
- `tax_amount` ظ‡ظˆ ظ…ط¨ظ„ط؛ ط§ظ„ط¶ط±ظٹط¨ط© ظپظ‚ط· (ظ‚ظٹظ…ط© ط±ظ‚ظ…ظٹط©)
- ط¥ط°ط§ ظ„ظ… طھظˆط¬ط¯ ط¶ط±ظٹط¨ط©: `tax_amount = 0`
- `total_amount` = `subtotal + tax_amount`""")
        
        # ط¨ظ†ط§ط، ط§ظ„ظ€ Prompt ط§ظ„ظ†ظ‡ط§ط¦ظٹ
        prompt = f"""{system_instruction}

ظ…ظ† ظپط¶ظ„ظƒ ط§ط³طھط®ط±ط¬ ط§ظ„ط¨ظٹط§ظ†ط§طھ ظ…ظ† ظ‡ط°ظ‡ ط§ظ„ظپط§طھظˆط±ط© ظˆط£ط±ط¬ط¹ظ‡ط§ ط¨طھظ†ط³ظٹظ‚ JSON ط§ظ„طھط§ظ„ظٹ:

{json_format}

{prompt_instructions}"""
        
        generation_config = {
            "temperature": temperature,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 4000,
        }
        
        # طھط³ط¬ظٹظ„ ط§ظ„ظ€ Prompt ط§ظ„ظ…ط³طھط®ط¯ظ… ظ„ظ„طھطµط­ظٹط­
        frappe.logger().info(f"Using prompt for extraction: {prompt[:500]}...")
        
        # ط¥ط±ط³ط§ظ„ ط§ظ„ط·ظ„ط¨
        response = model.generate_content(
            contents=[
                {"mime_type": mime_type, "data": file_bytes},
                prompt
            ],
            generation_config=generation_config
        )
        
        response_text = response.text.strip()
        
        # طھط³ط¬ظٹظ„ ط§ظ„ط§ط³طھط¬ط§ط¨ط© ظ„ظ„طھطµط­ظٹط­
        frappe.logger().info(f"Gemini response: {response_text[:500]}...")
        
        # ط§ط³طھط®ط±ط§ط¬ JSON
        json_str = response_text
        if '```json' in json_str:
            json_str = json_str.split('```json')[1].split('```')[0].strip()
        elif '```' in json_str:
            json_str = json_str.split('```')[1].split('```')[0].strip()
        
        # ط¥ظٹط¬ط§ط¯ ظƒط§ط¦ظ† JSON
        start_idx = json_str.find('{')
        end_idx = json_str.rfind('}') + 1
        if start_idx != -1 and end_idx > start_idx:
            json_str = json_str[start_idx:end_idx]
        
        # ط¥طµظ„ط§ط­ ط§ظ„ظ…ط´ط§ظƒظ„ ط§ظ„ط´ط§ط¦ط¹ط©
        json_str = json_str.replace("'", '"')
        json_str = json_str.replace("None", "null")
        json_str = json_str.replace("True", "true")
        json_str = json_str.replace("False", "false")
        
        data = json.loads(json_str)
        
        # 1. ظ…ط¹ط§ظ„ط¬ط© ط§ظ„ط£طµظ†ط§ظپ
        items = data.get("items", [])
        
        # 1.1. ط§ظ„طھط£ظƒط¯ ظ…ظ† ط£ظ† ظƒظ„ طµظ†ظپ ظ„ط¯ظٹظ‡ ط§ظ„ط­ظ‚ظˆظ„ ط§ظ„ظ…ط·ظ„ظˆط¨ط©
        for item in items:
            # طھط­ظˆظٹظ„ ط§ظ„ظ‚ظٹظ… ط¥ظ„ظ‰ ط£ط±ظ‚ط§ظ…
            quantity = float(item.get("quantity", 0))
            unit_price = float(item.get("unit_price", 0))
            
            # ط­ط³ط§ط¨ item_total ط¥ط°ط§ ظƒط§ظ† ظ†ط§ظ‚طµط§ظ‹
            if not item.get("item_total") or float(item.get("item_total", 0)) == 0:
                item["item_total"] = round(quantity * unit_price, 2)
            else:
                item["item_total"] = round(float(item.get("item_total", 0)), 2)
            
            # ظ…ط¹ط§ظ„ط¬ط© tax_amount ظ„ظ„طµظ†ظپ
            if not item.get("tax_amount"):
                item["tax_amount"] = 0
            else:
                item["tax_amount"] = round(float(item.get("tax_amount", 0)), 2)
            
            # ط­ط³ط§ط¨ total_with_tax ظ„ظ„طµظ†ظپ
            item_total = float(item["item_total"])
            item_tax = float(item["tax_amount"])
            item["total_with_tax"] = round(item_total + item_tax, 2)
        
        # 2. ط­ط³ط§ط¨ ط§ظ„ط¥ط¬ظ…ط§ظ„ظٹط§طھ
        # 2.1. ط­ط³ط§ط¨ subtotal ظ…ظ† ط§ظ„ط£طµظ†ط§ظپ
        calculated_subtotal = sum(float(item.get("item_total", 0)) for item in items)
        calculated_subtotal = round(calculated_subtotal, 2)
        
        # طھط­ط¯ظٹط« subtotal ط¥ط°ط§ ظƒط§ظ† ظ†ط§ظ‚طµط§ظ‹ ط£ظˆ ظ…ط®طھظ„ظپط§ظ‹
        subtotal = float(data.get("subtotal", 0))
        if subtotal == 0 or abs(subtotal - calculated_subtotal) > 0.01:
            data["subtotal"] = calculated_subtotal
        else:
            data["subtotal"] = round(subtotal, 2)
        
        subtotal = data["subtotal"]
        
        # 2.2. ط­ط³ط§ط¨ ط¥ط¬ظ…ط§ظ„ظٹ ط§ظ„ط¶ط±ظٹط¨ط© ظ…ظ† ط§ظ„ط£طµظ†ط§ظپ
        calculated_tax = sum(float(item.get("tax_amount", 0)) for item in items)
        calculated_tax = round(calculated_tax, 2)
        
        # طھط­ط¯ظٹط« tax_amount ط¥ط°ط§ ظƒط§ظ† ظ†ط§ظ‚طµط§ظ‹ ط£ظˆ ظ…ط®طھظ„ظپط§ظ‹
        tax_amount = float(data.get("tax_amount", 0))
        if abs(tax_amount - calculated_tax) > 0.01 and calculated_tax > 0:
            data["tax_amount"] = calculated_tax
        else:
            data["tax_amount"] = round(tax_amount, 2)
        
        tax_amount = data["tax_amount"]
        
        # 2.3. ط­ط³ط§ط¨ total_amount
        total_amount = float(data.get("total_amount", 0))
        calculated_total = round(subtotal + tax_amount, 2)
        
        if total_amount == 0 or abs(total_amount - calculated_total) > 0.01:
            data["total_amount"] = calculated_total
        else:
            data["total_amount"] = round(total_amount, 2)
        
        # 3. ط§ظ„طھط­ظ‚ظ‚ ط§ظ„ظ†ظ‡ط§ط¦ظٹ ظ…ظ† ط§ظ„ط­ط³ط§ط¨ط§طھ
        data["validation"] = {
            "subtotal_calculated": calculated_subtotal,
            "subtotal_extracted": round(subtotal, 2),
            "tax_calculated": calculated_tax,
            "tax_extracted": round(tax_amount, 2),
            "total_calculated": calculated_total,
            "total_extracted": round(data["total_amount"], 2),
            "subtotal_match": abs(calculated_subtotal - subtotal) < 0.01,
            "tax_match": abs(calculated_tax - tax_amount) < 0.01,
            "total_match": abs(calculated_total - data["total_amount"]) < 0.01
        }
        
        # 4. ط¥ط¶ط§ظپط© طھظپط§طµظٹظ„ ط§ظ„ط¹ظ…ظ„ط© ط¥ط°ط§ ظƒط§ظ†طھ ظ†ط§ظ‚طµط©
        if not data.get("currency"):
            data["currency"] = "SAR"  # ظ‚ظٹظ…ط© ط§ظپطھط±ط§ط¶ظٹط©
        
        return {
            "success": True,
            "data": data
        }
        
    except json.JSONDecodeError as e:
        frappe.log_error(f"JSON decode error: {str(e)}\nResponse text: {response_text}", "Gemini Extraction")
        return {
            "success": False,
            "error": f"Failed to parse JSON: {str(e)}",
            "raw_response": response_text[:500] if 'response_text' in locals() else "No response"
        }
    except Exception as e:
        frappe.log_error(f"Gemini API error: {str(e)}", "Gemini Extraction")
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }

# ط¨ط§ظ‚ظٹ ط§ظ„ط¯ظˆط§ظ„ طھط¨ظ‚ظ‰ ظƒظ…ط§ ظ‡ظٹ ط¨ط¯ظˆظ† طھط؛ظٹظٹط±
@frappe.whitelist()
def create_purchase_invoice_draft(invoice_name: str) -> dict:
    """
    ط¥ظ†ط´ط§ط، ظ…ط³ظˆط¯ط© ظپط§طھظˆط±ط© ط´ط±ط§ط، ظ…ظ† ط§ظ„ظپط§طھظˆط±ط© ط§ظ„ظ…ط³طھط®ط±ط¬ط©
    """
    try:
        extracted = frappe.get_doc("Extracted Invoice", invoice_name)
        
        if extracted.status == "Converted":
            return {
                "success": False,
                "error": "This invoice has already been converted"
            }
        
        # ط§ظ„طھط­ظ‚ظ‚ ظ…ظ† ط§ظ„ط¨ظٹط§ظ†ط§طھ ط§ظ„ظ…ط·ظ„ظˆط¨ط©
        if not extracted.supplier_link:
            return {
                "success": False,
                "error": "Please select a supplier first"
            }
        
        if not extracted.items or len(extracted.items) == 0:
            return {
                "success": False,
                "error": "No items found in the extracted invoice"
            }
        
        # ط¥ظ†ط´ط§ط، ظپط§طھظˆط±ط© ط§ظ„ط´ط±ط§ط،
        pi = frappe.new_doc("Purchase Invoice")
        pi.supplier = extracted.supplier_link
        pi.supplier_name = frappe.db.get_value("Supplier", extracted.supplier_link, "supplier_name")
        pi.bill_no = extracted.invoice_number
        pi.posting_date = extracted.invoice_date or frappe.utils.nowdate()
        pi.due_date = extracted.due_date or frappe.utils.add_days(pi.posting_date, 30)
        pi.currency = extracted.currency or "SAR"
        pi.company = frappe.defaults.get_user_default("company")
        
        # ط¥ط¶ط§ظپط© ط§ظ„ط£طµظ†ط§ظپ
        for item in extracted.items:
            item_name = frappe.db.get_value("Item", item.item_link, "item_name") if item.item_link else item.item_name
            
            pi.append("items", {
                "item_code": item.item_link or "",
                "item_name": item_name or item.item_name,
                "description": item.description or item.item_name,
                "qty": item.quantity,
                "rate": item.rate,
                "amount": item.amount,
                "warehouse": "",  # ظٹطھط±ظƒ ظپط§ط±ط؛ط§ظ‹ ظ„ظ„ظ…ط³طھط®ط¯ظ…
                "expense_account": "",  # ظٹطھط±ظƒ ظپط§ط±ط؛ط§ظ‹ ظ„ظ„ظ…ط³طھط®ط¯ظ…
                "cost_center": "",  # ظٹطھط±ظƒ ظپط§ط±ط؛ط§ظ‹ ظ„ظ„ظ…ط³طھط®ط¯ظ…
                "uom": frappe.db.get_value("Item", item.item_link, "stock_uom") if item.item_link else "Unit"
            })
        
        # ط¥ط¶ط§ظپط© ط§ظ„ط¶ط±ظٹط¨ط© ط¥ط°ط§ ظƒط§ظ†طھ ظ…ظˆط¬ظˆط¯ط©
        if extracted.tax_amount and extracted.tax_amount > 0:
            # ط­ط³ط§ط¨ ظ†ط³ط¨ط© ط§ظ„ط¶ط±ظٹط¨ط©
            tax_rate = 15  # ظ†ط³ط¨ط© ط§ظپطھط±ط§ط¶ظٹط©
            if extracted.subtotal and extracted.subtotal > 0:
                tax_rate = (extracted.tax_amount / extracted.subtotal) * 100
                tax_rate = round(tax_rate, 2)
            
            # ط§ظ„ط¨ط­ط« ط¹ظ† ط­ط³ط§ط¨ ط§ظ„ط¶ط±ظٹط¨ط©
            tax_accounts = frappe.get_all("Account",
                filters={
                    "account_type": "Tax",
                    "company": pi.company,
                    "is_group": 0
                },
                fields=["name"],
                limit=1
            )
            
            if tax_accounts:
                pi.append("taxes", {
                    "charge_type": "On Net Total",
                    "account_head": tax_accounts[0].name,
                    "description": f"Tax {tax_rate}%",
                    "rate": tax_rate
                })
        
        # ط­ظپط¸ ط§ظ„ظپط§طھظˆط±ط©
        pi.insert()
        
        # طھط­ط¯ظٹط« ط­ط§ظ„ط© ط§ظ„ظپط§طھظˆط±ط© ط§ظ„ظ…ط³طھط®ط±ط¬ط©
        extracted.purchase_invoice_link = pi.name
        extracted.status = "Converted"
        extracted.save()
        
        return {
            "success": True,
            "purchase_invoice": pi.name,
            "message": "Purchase invoice draft created successfully"
        }
        
    except Exception as e:
        frappe.log_error(f"Purchase invoice draft creation error: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

@frappe.whitelist()
def link_to_purchase_invoice(extracted_invoice_name: str, purchase_invoice_name: str) -> dict:
    """
    ط±ط¨ط· ط§ظ„ظپط§طھظˆط±ط© ط§ظ„ظ…ط³طھط®ط±ط¬ط© ط¨ظپط§طھظˆط±ط© ط§ظ„ط´ط±ط§ط،
    """
    try:
        extracted = frappe.get_doc("Extracted Invoice", extracted_invoice_name)
        
        extracted.purchase_invoice_link = purchase_invoice_name
        extracted.status = "Converted"
        extracted.save()
        
        return {"success": True}
        
    except Exception as e:
        frappe.log_error(f"Link to purchase invoice error: {str(e)}")
        return {"success": False, "error": str(e)}

# ط¨ط§ظ‚ظٹ ط§ظ„ط¯ظˆط§ظ„ (search_suppliers, search_items, validate_tax_calculations, fix_tax_calculation)
# طھط¨ظ‚ظ‰ ظƒظ…ط§ ظ‡ظٹ ط¨ط¯ظˆظ† طھط؛ظٹظٹط±


@frappe.whitelist()
def search_suppliers(supplier_name: str) -> list:
    """ط¨ط­ط« ط¹ظ† ظ…ظˆط±ط¯ظٹظ†"""
    suppliers = frappe.get_all("Supplier",
        filters={"supplier_name": ["like", f"%{supplier_name}%"]},
        fields=["name", "supplier_name", "supplier_type", "tax_id"]
    )
    return suppliers

@frappe.whitelist()
def search_items(item_name: str) -> list:
    """ط¨ط­ط« ط¹ظ† ط£طµظ†ط§ظپ"""
    items = frappe.get_all("Item",
        filters={"item_name": ["like", f"%{item_name}%"]},
        fields=["name", "item_name", "item_code", "stock_uom", "description"]
    )
    return items

@frappe.whitelist()
def validate_tax_calculations(invoice_name: str) -> dict:
    """
    ط§ظ„طھط­ظ‚ظ‚ ظ…ظ† ط­ط³ط§ط¨ط§طھ ط§ظ„ط¶ط±ظٹط¨ط© ظپظٹ ط§ظ„ظپط§طھظˆط±ط© ط§ظ„ظ…ط³طھط®ط±ط¬ط©
    """
    try:
        extracted = frappe.get_doc("Extracted Invoice", invoice_name)
        
        # ط­ط³ط§ط¨ ط§ظ„ظ…ط¬ط§ظ…ظٹط¹ ظ…ظ† ط§ظ„ط£طµظ†ط§ظپ
        items_subtotal = 0
        items_tax_total = 0
        
        for item in extracted.items:
            item_total = item.quantity * item.rate
            items_subtotal += item_total
            
            item_tax = getattr(item, 'tax_amount', 0)
            items_tax_total += float(item_tax)
        
        items_subtotal = round(items_subtotal, 2)
        items_tax_total = round(items_tax_total, 2)
        items_grand_total = round(items_subtotal + items_tax_total, 2)
        
        # ظ…ظ‚ط§ط±ظ†ط© ظ…ط¹ ط§ظ„ظ‚ظٹظ… ط§ظ„ط¥ط¬ظ…ط§ظ„ظٹط©
        extracted_subtotal = extracted.subtotal or 0
        extracted_tax = extracted.tax_amount or 0
        extracted_total = extracted.total_amount or 0
        
        # ط­ط³ط§ط¨ ظ†ط³ط¨ط© ط§ظ„ط¶ط±ظٹط¨ط© ط§ظ„ظپط¹ظ„ظٹط©
        actual_tax_rate = 0
        if extracted_subtotal > 0:
            actual_tax_rate = (extracted_tax / extracted_subtotal) * 100
        
        # ط§ظ„طھط­ظ‚ظ‚ ظ…ظ† ط§ظ„ظ…ط·ط§ط¨ظ‚ط©
        subtotal_match = abs(items_subtotal - extracted_subtotal) < 0.01
        tax_match = abs(items_tax_total - extracted_tax) < 0.01
        total_match = abs(items_grand_total - extracted_total) < 0.01
        
        # ط­ط³ط§ط¨ ط§ظ„ظپط±ظˆظ‚ط§طھ
        subtotal_diff = round(items_subtotal - extracted_subtotal, 2)
        tax_diff = round(items_tax_total - extracted_tax, 2)
        total_diff = round(items_grand_total - extracted_total, 2)
        
        return {
            "success": True,
            "calculations": {
                "from_items": {
                    "subtotal": items_subtotal,
                    "tax_amount": items_tax_total,
                    "total_amount": items_grand_total
                },
                "from_extracted": {
                    "subtotal": extracted_subtotal,
                    "tax_amount": extracted_tax,
                    "total_amount": extracted_total
                },
                "tax_rate_percentage": round(actual_tax_rate, 2)
            },
            "validation": {
                "subtotal_match": subtotal_match,
                "tax_match": tax_match,
                "total_match": total_match,
                "all_match": subtotal_match and tax_match and total_match
            },
            "differences": {
                "subtotal_diff": subtotal_diff,
                "tax_diff": tax_diff,
                "total_diff": total_diff
            },
            "items_summary": [
                {
                    "item_name": item.item_name,
                    "quantity": item.quantity,
                    "rate": item.rate,
                    "item_total": round(item.quantity * item.rate, 2),
                    "tax_amount": round(getattr(item, 'tax_amount', 0), 2),
                    "total_with_tax": round((item.quantity * item.rate) + getattr(item, 'tax_amount', 0), 2)
                }
                for item in extracted.items
            ]
        }
        
    except Exception as e:
        frappe.log_error(f"Tax validation error: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

@frappe.whitelist()
def fix_tax_calculation(invoice_name: str) -> dict:
    """
    طھطµط­ظٹط­ ط­ط³ط§ط¨ط§طھ ط§ظ„ط¶ط±ظٹط¨ط© ظپظٹ ط§ظ„ظپط§طھظˆط±ط© ط§ظ„ظ…ط³طھط®ط±ط¬ط©
    """
    try:
        extracted = frappe.get_doc("Extracted Invoice", invoice_name)
        
        # ط­ط³ط§ط¨ ط§ظ„ظ‚ظٹظ… ط§ظ„طµط­ظٹط­ط© ظ…ظ† ط§ظ„ط£طµظ†ط§ظپ
        new_subtotal = 0
        new_tax_amount = 0
        
        for item in extracted.items:
            item_total = item.quantity * item.rate
            new_subtotal += item_total
            
            item_tax = getattr(item, 'tax_amount', 0)
            new_tax_amount += float(item_tax)
        
        new_subtotal = round(new_subtotal, 2)
        new_tax_amount = round(new_tax_amount, 2)
        new_total_amount = round(new_subtotal + new_tax_amount, 2)
        
        # طھط­ط¯ظٹط« ط§ظ„ظ‚ظٹظ…
        extracted.subtotal = new_subtotal
        extracted.tax_amount = new_tax_amount
        extracted.total_amount = new_total_amount
        
        # ط­ط³ط§ط¨ ظ†ط³ط¨ط© ط§ظ„ط¶ط±ظٹط¨ط© ط§ظ„ط¬ط¯ظٹط¯ط©
        if new_subtotal > 0:
            extracted.tax_rate = (new_tax_amount / new_subtotal) * 100
        
        extracted.save()
        
        return {
            "success": True,
            "message": "Tax calculations fixed successfully",
            "updated_values": {
                "subtotal": new_subtotal,
                "tax_amount": new_tax_amount,
                "total_amount": new_total_amount,
                "tax_rate": extracted.tax_rate
            }
        }
        
    except Exception as e:
        frappe.log_error(f"Fix tax calculation error: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }
        
        




from frappe.utils import nowdate


def _safe_float(v, default=0.0) -> float:
    try:
        if v is None or v == "":
            return float(default)
        return float(v)
    except Exception:
        return float(default)


def _match_supplier_link(supplier_name: str) -> str:
    if not supplier_name:
        return ""
    rows = frappe.get_all(
        "Supplier",
        filters=[["supplier_name", "like", f"%{supplier_name}%"]],
        fields=["name", "supplier_name"],
        limit=1,
    )
    return rows[0]["name"] if rows else ""


def _match_item_link(description: str) -> str:
    if not description:
        return ""

    # Tag pattern: #TAG#
    tag = None
    try:
        import re
        m = re.search(r"#([^#]+)#", description)
        if m:
            tag = m.group(1).strip()
    except Exception:
        tag = None

    # If tag exists, try Item.description contains #TAG#
    if tag:
        rows = frappe.get_all(
            "Item",
            filters=[["description", "like", f"%#{tag}#%"]],
            fields=["name", "item_name", "item_code"],
            limit=1,
        )
        if rows:
            return rows[0]["name"]

    # Fallback: item_name like description
    rows = frappe.get_all(
        "Item",
        filters=[["item_name", "like", f"%{description}%"]],
        fields=["name", "item_name", "item_code"],
        limit=1,
    )
    return rows[0]["name"] if rows else ""


def _apply_extracted_data_to_invoice(inv, data: dict) -> None:
    supplier_name = (data.get("supplier_ar") or data.get("supplier") or "").strip()

    inv.supplier_name = supplier_name
    inv.supplier_link = _match_supplier_link(supplier_name)
    inv.invoice_number = (data.get("invoice_number") or "").strip()

    inv.invoice_date = data.get("date") or None
    inv.due_date = data.get("due_date") or None

    inv.subtotal = _safe_float(data.get("subtotal"))
    inv.tax_amount = _safe_float(data.get("tax_amount"))
    inv.total_amount = _safe_float(data.get("total_amount"))

    # Currency is Link to Currency doctype. Use only if exists.
    currency = (data.get("currency") or "").strip() or "SAR"
    if frappe.db.exists("Currency", currency):
        inv.currency = currency
    else:
        inv.currency = ""

    inv.extracted_data = json.dumps(data, ensure_ascii=False, indent=2)

    # Items
    inv.set("items", [])
    for it in (data.get("items") or []):
        desc = (it.get("description_ar") or it.get("description") or "").strip()
        if not desc:
            desc = "Item"

        qty = _safe_float(it.get("quantity"), 1.0)
        rate = _safe_float(it.get("unit_price"), 0.0)
        amount = _safe_float(it.get("item_total"), qty * rate)
        tax_amount = _safe_float(it.get("tax_amount"), 0.0)
        total_with_tax = _safe_float(it.get("total_with_tax"), amount + tax_amount)

        item_link = _match_item_link(desc)

        row = inv.append("items", {})
        row.extracted_text = desc
        row.item_link = item_link
        row.quantity = qty
        row.rate = rate
        row.amount = amount
        row.tax_amount = tax_amount
        row.total_with_tax = total_with_tax
        row.language = "ar" if it.get("description_ar") else "en"
        row.taxable = 1 if tax_amount > 0 else 0

    inv.status = "Ready"


@frappe.whitelist()
def extract_and_update_extracted_invoice(invoice_name: str) -> dict:
    """Server-side extraction + write results into Extracted Invoice."""
    try:
        inv = frappe.get_doc("Extracted Invoice", invoice_name)

        if not inv.original_file:
            return {"success": False, "error": "original_file is empty"}

        res = extract_invoice_data_only(inv.original_file)
        if not res.get("success"):
            inv.status = "Processing"
            inv.save(ignore_permissions=True, ignore_version=True)
            return {"success": False, "error": res.get("error")}

        data = res.get("data") or {}
        inv.extraction_model = res.get("model_used") or ""
        _apply_extracted_data_to_invoice(inv, data)

        inv.save(ignore_permissions=True, ignore_version=True)
        frappe.db.commit()

        return {"success": True, "invoice": inv.name, "updated": True, "extraction_time": res.get("extraction_time")}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Auto Extraction Error")
        return {"success": False, "error": str(e)}
