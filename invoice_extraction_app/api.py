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
    استخراج البيانات من الملف وإرجاعها فقط (بدون إنشاء سجل)
    """
    try:
        # التحقق من وجود Gemini Settings
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
        
        # تكوين Gemini
        genai.configure(api_key=settings.gemini_api_key)
        
        # قراءة الملف
        file_doc = frappe.get_doc("File", {"file_url": file_url})
        file_path = file_doc.get_full_path()
        
        with open(file_path, 'rb') as f:
            file_bytes = f.read()
        
        file_ext = os.path.splitext(file_path)[1].lower()
        
        # استخراج البيانات
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
        
        # إرجاع البيانات فقط (بدون إنشاء سجل)
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
    استخراج البيانات باستخدام Gemini مع إعدادات قابلة للتخصيص
    """
    try:
        # تحديد نوع MIME
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
        
        # اختيار النموذج
        model = genai.GenerativeModel(model_name)
        
        # استخدام التعليمات من Gemini Settings
        system_instruction = getattr(settings, 'system_instruction', 
            "أنت متخصص في استخراج البيانات من فواتير الشراء. استخرج البيانات بدقة مع التركيز على تفاصيل الضرائب والحسابات المالية.")
        
        json_format = getattr(settings, 'json_format', """{
    "supplier": "اسم المورد",
    "supplier_ar": "اسم المورد بالعربية",
    "invoice_number": "رقم الفاتورة",
    "date": "تاريخ الفاتورة (YYYY-MM-DD)",
    "due_date": "تاريخ الاستحقاق (YYYY-MM-DD)",
    "subtotal": "المبلغ قبل الضريبة",
    "tax_amount": "مبلغ الضريبة الإجمالي",
    "total_amount": "المبلغ الإجمالي بعد الضريبة",
    "currency": "العملة",
    "items": [
        {
            "description": "وصف الصنف",
            "description_ar": "وصف الصنف بالعربية",
            "quantity": الكمية,
            "unit_price": سعر الوحدة,
            "item_total": "المبلغ الإجمالي للصنف (الكمية × السعر)",
            "tax_amount": "مبلغ الضريبة للصنف",
            "total_with_tax": "المبلغ الإجمالي للصنف بعد الضريبة"
        }
    ]
}""")
        
        prompt_instructions = getattr(settings, 'prompt_instructions', 
            """**القواعد المهمة بالترتيب:**

1. **استخراج الضريبة:**
   - استخرج `tax_amount` (مبلغ الضريبة) فقط - لا حاجة لنسبة الضريبة
   - إذا كانت الفاتورة تحتوي على ضريبة: استخرج `tax_amount` كقيمة رقمية
   - إذا لم تكن هناك ضريبة: ضع `tax_amount = 0`

2. **استخراج الأصناف:**
   - لكل صنف، استخرج:
     - `tax_amount` للصنف (مبلغ الضريبة لهذا الصنف فقط)
     - `item_total` (الكمية × سعر الوحدة)
     - `total_with_tax` (item_total + tax_amount للصنف)
   - إذا لم يكن الصنف خاضع للضريبة: `tax_amount = 0` للصنف
   - `total_with_tax` يجب أن يساوي `item_total + tax_amount` لكل صنف

3. **حساب الإجماليات:**
   - `subtotal` = مجموع `item_total` لجميع الأصناف
   - `tax_amount` (للإجمالي) = مجموع `tax_amount` لجميع الأصناف
   - `total_amount` = `subtotal + tax_amount` (للإجمالي)
   - إذا كان `total_amount` ناقصاً: احسبه = `subtotal + tax_amount`

4. **التحقق من الحسابات:**
   - تأكد أن: مجموع `item_total` لجميع الأصناف ≈ `subtotal`
   - تأكد أن: مجموع `tax_amount` لجميع الأصناف ≈ `tax_amount` للإجمالي
   - تأكد أن: `total_amount` = `subtotal + tax_amount`

5. **التنسيق:**
   - التواريخ: YYYY-MM-DD
   - العملة: SAR أو USD أو EUR (الرمز فقط)
   - الأرقام: قيم رقمية فقط (بدون رموز العملة)

**سيناريوهات خاصة:**
1. إذا كانت الضريبة موضحة كقيمة إجمالية فقط: وزعها على الأصناف تناسبياً
2. إذا كانت الضريبة موضحة لكل صنف: استخدم القيم كما هي
3. إذا لم تظهر الضريبة في الفاتورة: `tax_amount = 0` للجميع
4. إذا كان هناك خصم: أضفه كصنف منفصل أو اطرحه من subtotal

**هام جداً:** 
- `tax_amount` هو مبلغ الضريبة فقط (قيمة رقمية)
- إذا لم توجد ضريبة: `tax_amount = 0`
- `total_amount` = `subtotal + tax_amount`""")
        
        # بناء الـ Prompt النهائي
        prompt = f"""{system_instruction}

من فضلك استخرج البيانات من هذه الفاتورة وأرجعها بتنسيق JSON التالي:

{json_format}

{prompt_instructions}"""
        
        generation_config = {
            "temperature": temperature,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 4000,
        }
        
        # تسجيل الـ Prompt المستخدم للتصحيح
        frappe.logger().info(f"Using prompt for extraction: {prompt[:500]}...")
        
        # إرسال الطلب
        response = model.generate_content(
            contents=[
                {"mime_type": mime_type, "data": file_bytes},
                prompt
            ],
            generation_config=generation_config
        )
        
        response_text = response.text.strip()
        
        # تسجيل الاستجابة للتصحيح
        frappe.logger().info(f"Gemini response: {response_text[:500]}...")
        
        # استخراج JSON
        json_str = response_text
        if '```json' in json_str:
            json_str = json_str.split('```json')[1].split('```')[0].strip()
        elif '```' in json_str:
            json_str = json_str.split('```')[1].split('```')[0].strip()
        
        # إيجاد كائن JSON
        start_idx = json_str.find('{')
        end_idx = json_str.rfind('}') + 1
        if start_idx != -1 and end_idx > start_idx:
            json_str = json_str[start_idx:end_idx]
        
        # إصلاح المشاكل الشائعة
        json_str = json_str.replace("'", '"')
        json_str = json_str.replace("None", "null")
        json_str = json_str.replace("True", "true")
        json_str = json_str.replace("False", "false")
        
        data = json.loads(json_str)
        
        # 1. معالجة الأصناف
        items = data.get("items", [])
        
        # 1.1. التأكد من أن كل صنف لديه الحقول المطلوبة
        for item in items:
            # تحويل القيم إلى أرقام
            quantity = float(item.get("quantity", 0))
            unit_price = float(item.get("unit_price", 0))
            
            # حساب item_total إذا كان ناقصاً
            if not item.get("item_total") or float(item.get("item_total", 0)) == 0:
                item["item_total"] = round(quantity * unit_price, 2)
            else:
                item["item_total"] = round(float(item.get("item_total", 0)), 2)
            
            # معالجة tax_amount للصنف
            if not item.get("tax_amount"):
                item["tax_amount"] = 0
            else:
                item["tax_amount"] = round(float(item.get("tax_amount", 0)), 2)
            
            # حساب total_with_tax للصنف
            item_total = float(item["item_total"])
            item_tax = float(item["tax_amount"])
            item["total_with_tax"] = round(item_total + item_tax, 2)
        
        # 2. حساب الإجماليات
        # 2.1. حساب subtotal من الأصناف
        calculated_subtotal = sum(float(item.get("item_total", 0)) for item in items)
        calculated_subtotal = round(calculated_subtotal, 2)
        
        # تحديث subtotal إذا كان ناقصاً أو مختلفاً
        subtotal = float(data.get("subtotal", 0))
        if subtotal == 0 or abs(subtotal - calculated_subtotal) > 0.01:
            data["subtotal"] = calculated_subtotal
        else:
            data["subtotal"] = round(subtotal, 2)
        
        subtotal = data["subtotal"]
        
        # 2.2. حساب إجمالي الضريبة من الأصناف
        calculated_tax = sum(float(item.get("tax_amount", 0)) for item in items)
        calculated_tax = round(calculated_tax, 2)
        
        # تحديث tax_amount إذا كان ناقصاً أو مختلفاً
        tax_amount = float(data.get("tax_amount", 0))
        if abs(tax_amount - calculated_tax) > 0.01 and calculated_tax > 0:
            data["tax_amount"] = calculated_tax
        else:
            data["tax_amount"] = round(tax_amount, 2)
        
        tax_amount = data["tax_amount"]
        
        # 2.3. حساب total_amount
        total_amount = float(data.get("total_amount", 0))
        calculated_total = round(subtotal + tax_amount, 2)
        
        if total_amount == 0 or abs(total_amount - calculated_total) > 0.01:
            data["total_amount"] = calculated_total
        else:
            data["total_amount"] = round(total_amount, 2)
        
        # 3. التحقق النهائي من الحسابات
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
        
        # 4. إضافة تفاصيل العملة إذا كانت ناقصة
        if not data.get("currency"):
            data["currency"] = "SAR"  # قيمة افتراضية
        
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

# باقي الدوال تبقى كما هي بدون تغيير
@frappe.whitelist()
def create_purchase_invoice_draft(invoice_name: str) -> dict:
    """
    إنشاء مسودة فاتورة شراء من الفاتورة المستخرجة
    """
    try:
        extracted = frappe.get_doc("Extracted Invoice", invoice_name)
        
        if extracted.status == "Converted":
            return {
                "success": False,
                "error": "This invoice has already been converted"
            }
        
        # التحقق من البيانات المطلوبة
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
        
        # إنشاء فاتورة الشراء
        pi = frappe.new_doc("Purchase Invoice")
        pi.supplier = extracted.supplier_link
        pi.supplier_name = frappe.db.get_value("Supplier", extracted.supplier_link, "supplier_name")
        pi.bill_no = extracted.invoice_number
        pi.posting_date = extracted.invoice_date or frappe.utils.nowdate()
        pi.due_date = extracted.due_date or frappe.utils.add_days(pi.posting_date, 30)
        pi.currency = extracted.currency or "SAR"
        pi.company = frappe.defaults.get_user_default("company")
        
        # إضافة الأصناف
        for item in extracted.items:
            item_name = frappe.db.get_value("Item", item.item_link, "item_name") if item.item_link else item.item_name
            
            pi.append("items", {
                "item_code": item.item_link or "",
                "item_name": item_name or item.item_name,
                "description": item.description or item.item_name,
                "qty": item.quantity,
                "rate": item.rate,
                "amount": item.amount,
                "warehouse": "",  # يترك فارغاً للمستخدم
                "expense_account": "",  # يترك فارغاً للمستخدم
                "cost_center": "",  # يترك فارغاً للمستخدم
                "uom": frappe.db.get_value("Item", item.item_link, "stock_uom") if item.item_link else "Unit"
            })
        
        # إضافة الضريبة إذا كانت موجودة
        if extracted.tax_amount and extracted.tax_amount > 0:
            # حساب نسبة الضريبة
            tax_rate = 15  # نسبة افتراضية
            if extracted.subtotal and extracted.subtotal > 0:
                tax_rate = (extracted.tax_amount / extracted.subtotal) * 100
                tax_rate = round(tax_rate, 2)
            
            # البحث عن حساب الضريبة
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
        
        # حفظ الفاتورة
        pi.insert()
        
        # تحديث حالة الفاتورة المستخرجة
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
    ربط الفاتورة المستخرجة بفاتورة الشراء
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

# باقي الدوال (search_suppliers, search_items, validate_tax_calculations, fix_tax_calculation)
# تبقى كما هي بدون تغيير


@frappe.whitelist()
def search_suppliers(supplier_name: str) -> list:
    """بحث عن موردين"""
    suppliers = frappe.get_all("Supplier",
        filters={"supplier_name": ["like", f"%{supplier_name}%"]},
        fields=["name", "supplier_name", "supplier_type", "tax_id"]
    )
    return suppliers

@frappe.whitelist()
def search_items(item_name: str) -> list:
    """بحث عن أصناف"""
    items = frappe.get_all("Item",
        filters={"item_name": ["like", f"%{item_name}%"]},
        fields=["name", "item_name", "item_code", "stock_uom", "description"]
    )
    return items

@frappe.whitelist()
def validate_tax_calculations(invoice_name: str) -> dict:
    """
    التحقق من حسابات الضريبة في الفاتورة المستخرجة
    """
    try:
        extracted = frappe.get_doc("Extracted Invoice", invoice_name)
        
        # حساب المجاميع من الأصناف
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
        
        # مقارنة مع القيم الإجمالية
        extracted_subtotal = extracted.subtotal or 0
        extracted_tax = extracted.tax_amount or 0
        extracted_total = extracted.total_amount or 0
        
        # حساب نسبة الضريبة الفعلية
        actual_tax_rate = 0
        if extracted_subtotal > 0:
            actual_tax_rate = (extracted_tax / extracted_subtotal) * 100
        
        # التحقق من المطابقة
        subtotal_match = abs(items_subtotal - extracted_subtotal) < 0.01
        tax_match = abs(items_tax_total - extracted_tax) < 0.01
        total_match = abs(items_grand_total - extracted_total) < 0.01
        
        # حساب الفروقات
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
    تصحيح حسابات الضريبة في الفاتورة المستخرجة
    """
    try:
        extracted = frappe.get_doc("Extracted Invoice", invoice_name)
        
        # حساب القيم الصحيحة من الأصناف
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
        
        # تحديث القيم
        extracted.subtotal = new_subtotal
        extracted.tax_amount = new_tax_amount
        extracted.total_amount = new_total_amount
        
        # حساب نسبة الضريبة الجديدة
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