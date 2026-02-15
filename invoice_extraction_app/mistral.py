# invoice_extraction_app/mistral.py
import frappe
import json
import os
import base64
import traceback
from frappe.utils import now, get_site_path

# ✅ Mistral SDK
try:
    from mistralai import Mistral
    MISTRAL_AVAILABLE = True
except Exception as e:
    MISTRAL_AVAILABLE = False
    frappe.log_error(f"Mistral import error: {str(e)}", "Mistral Import Error")


# ---------------- Helpers ----------------
def _log(title: str, msg: str):
    try:
        frappe.log_error(message=str(msg)[:2000], title=title[:140])
    except Exception:
        pass


def _get_settings():
    if not frappe.db.exists("Mistral Settings", "Mistral Settings"):
        return None
    return frappe.get_single("Mistral Settings")


def _read_file(file_url: str):
    """Read file bytes from ERPNext File URLs."""
    if file_url.startswith("/files/"):
        path = get_site_path("public" + file_url)
    elif file_url.startswith("/private/files/"):
        path = get_site_path(file_url.lstrip("/"))
    else:
        fdoc = frappe.get_doc("File", {"file_url": file_url})
        path = fdoc.get_full_path()

    with open(path, "rb") as f:
        b = f.read()
    return b, os.path.splitext(path)[1].lower(), os.path.basename(path)


def _to_data_url(file_bytes: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(file_bytes).decode('utf-8')}"


def _json_extract(text: str):
    """Extract JSON safely from model response."""
    if not text:
        return None
    t = text.strip()
    if "```json" in t:
        t = t.split("```json")[1].split("```")[0].strip()
    elif "```" in t:
        t = t.split("```")[1].split("```")[0].strip()

    s = t.find("{")
    e = t.rfind("}") + 1
    if s != -1 and e > s:
        t = t[s:e]
    try:
        return json.loads(t)
    except Exception:
        return None


def _to_float(v):
    try:
        s = str(v).strip().replace(",", "")
        trans = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
        s = s.translate(trans)
        return float(s) if s else 0.0
    except Exception:
        return 0.0


def _post_process(data: dict) -> dict:
    """Normalize numeric fields + recompute totals from items."""
    try:
        items = data.get("items", []) or []
        subtotal = 0.0
        tax_total = 0.0

        for it in items:
            qty = _to_float(it.get("quantity", 0))
            price = _to_float(it.get("unit_price", 0))
            tax = _to_float(it.get("tax_amount", 0))

            item_total = qty * price
            it["quantity"] = qty
            it["unit_price"] = price
            it["tax_amount"] = round(tax, 2)
            it["item_total"] = round(item_total, 2)
            it["total_with_tax"] = round(item_total + tax, 2)

            subtotal += item_total
            tax_total += tax

        subtotal = round(subtotal, 2)
        tax_total = round(tax_total, 2)
        total = round(subtotal + tax_total, 2)

        if items:
            data["subtotal"] = subtotal
            data["tax_amount"] = tax_total
            data["total_amount"] = total
        else:
            data["subtotal"] = round(_to_float(data.get("subtotal", 0)), 2)
            data["tax_amount"] = round(_to_float(data.get("tax_amount", 0)), 2)
            data["total_amount"] = round(_to_float(data.get("total_amount", 0)), 2)

        if not data.get("currency"):
            data["currency"] = "SAR"

        data["validation"] = {
            "subtotal_calculated": subtotal,
            "tax_calculated": tax_total,
            "total_calculated": total,
        }
        return data
    except Exception:
        return data


# ---------------- Public API ----------------
@frappe.whitelist()
def get_mistral_settings():
    try:
        s = _get_settings()
        if not s:
            return {"success": False, "error": "Mistral Settings not found", "mistral_available": MISTRAL_AVAILABLE}

        api_key = s.get_password("mistral_api_key") if getattr(s, "mistral_api_key", None) else None
        return {
            "success": True,
            "model": s.selected_model or "mistral-large-latest",
            "temperature": s.temperature or 0.1,
            "ocr_model": getattr(s, "ocr_model", None) or "mistral-ocr-2512",
            "has_api_key": bool(api_key),
            "debug_enabled": int(getattr(s, "enable_debug_log", 0) or 0),
            "mistral_available": MISTRAL_AVAILABLE,
        }
    except Exception as e:
        return {"success": False, "error": str(e), "mistral_available": MISTRAL_AVAILABLE}


@frappe.whitelist()
def extract_invoice_data_only(file_url: str, model_name: str = None, temperature: float = None):
    """
    ✅ مطابق للدوكس:
    PDF: upload -> signed_url -> ocr.process(document_url)
    ثم Chat لاستخراج JSON من نص OCR.
    """
    try:
        if not MISTRAL_AVAILABLE:
            return {"success": False, "error": "mistralai not installed"}

        s = _get_settings()
        if not s:
            return {"success": False, "error": "Mistral Settings not found. Please create it first."}

        api_key = s.get_password("mistral_api_key")
        if not api_key:
            return {"success": False, "error": "Mistral API Key not set."}

        chat_model = model_name or s.selected_model or "mistral-large-latest"
        temp = temperature if temperature is not None else (s.temperature or 0.1)
        ocr_model = getattr(s, "ocr_model", None) or "mistral-ocr-2512"
        debug = int(getattr(s, "enable_debug_log", 0) or 0)

        file_bytes, ext, fname = _read_file(file_url)

        client = Mistral(api_key=api_key)

        # ---------------- PDF path (exact docs) ----------------
        if ext == ".pdf":
            data = _pdf_upload_signedurl_ocr_then_extract(
                client=client,
                pdf_bytes=file_bytes,
                file_name=fname,
                ocr_model=ocr_model,
                chat_model=chat_model,
                temperature=temp,
                settings=s,
                debug=debug,
            )
            return {"success": True, "data": data, "model_used": f"{ocr_model}+{chat_model}", "temperature": temp, "extraction_time": now()}

        # ---------------- Image path (basic_ocr supports image_url too) ----------------
        if ext in [".jpg", ".jpeg", ".png"]:
            data = _image_ocr_then_extract(
                client=client,
                img_bytes=file_bytes,
                ext=ext,
                ocr_model=ocr_model,
                chat_model=chat_model,
                temperature=temp,
                settings=s,
                debug=debug,
            )
            return {"success": True, "data": data, "model_used": f"{ocr_model}+{chat_model}", "temperature": temp, "extraction_time": now()}

        return {"success": False, "error": f"Unsupported file type: {ext}"}

    except Exception as e:
        _log("Mistral Extraction Error", traceback.format_exc())
        return {"success": False, "error": str(e)}


# ---------------- Core: EXACT docs flow ----------------
def _pdf_upload_signedurl_ocr_then_extract(client, pdf_bytes: bytes, file_name: str,
                                          ocr_model: str, chat_model: str,
                                          temperature: float, settings, debug: int):
    """
    1) upload file purpose="ocr"
    2) get_signed_url(file_id)
    3) ocr.process(model=..., document={"type":"document_url","document_url": signed_url})
    """
    # 1) Save temp + upload
    tmp_path = f"/tmp/{file_name}"
    with open(tmp_path, "wb") as f:
        f.write(pdf_bytes)

    if debug:
        frappe.logger().info(f"[Mistral] Uploading PDF: {file_name}")

    with open(tmp_path, "rb") as f:
        uploaded_pdf = client.files.upload(
            file={"file_name": file_name, "content": f},
            purpose="ocr"
        )

    try:
        os.remove(tmp_path)
    except Exception:
        pass

    file_id = uploaded_pdf.id
    if debug:
        frappe.logger().info(f"[Mistral] Uploaded file_id: {file_id}")

    # 2) signed url
    signed = client.files.get_signed_url(file_id=file_id)
    signed_url = signed.url

    if debug:
        frappe.logger().info(f"[Mistral] Signed URL obtained")

    # 3) OCR
    ocr_resp = client.ocr.process(
        model=ocr_model,
        document={"type": "document_url", "document_url": signed_url}
    )

    ocr_text = _ocr_pages_to_text(ocr_resp)
    if not ocr_text:
        raise Exception("OCR returned no text")

    # 4) Chat extract JSON
    data = _extract_from_ocr_text(client, ocr_text, chat_model, temperature, settings)
    return _post_process(data)


def _image_ocr_then_extract(client, img_bytes: bytes, ext: str,
                            ocr_model: str, chat_model: str,
                            temperature: float, settings, debug: int):
    """
    doc: ocr.process(document=image_url/base64))
    """
    if ext in [".jpg", ".jpeg"]:
        mime = "image/jpeg"
    else:
        mime = "image/png"

    doc = {"type": "image_url", "image_url": _to_data_url(img_bytes, mime)}

    ocr_resp = client.ocr.process(model=ocr_model, document=doc)
    ocr_text = _ocr_pages_to_text(ocr_resp)
    if not ocr_text:
        raise Exception("OCR returned no text")

    data = _extract_from_ocr_text(client, ocr_text, chat_model, temperature, settings)
    return _post_process(data)


def _ocr_pages_to_text(ocr_resp) -> str:
    pages = getattr(ocr_resp, "pages", None) or []
    out = []
    for p in pages:
        md = getattr(p, "markdown", "") or ""
        if md.strip():
            out.append(md.strip())
    return "\n\n".join(out).strip()


def _extract_from_ocr_text(client, ocr_text: str, chat_model: str, temperature: float, settings):
    json_format = getattr(settings, "json_format", None) or """{
  "supplier": "اسم المورد",
  "supplier_ar": "اسم المورد بالعربية",
  "invoice_number": "رقم الفاتورة",
  "date": "تاريخ الفاتورة (YYYY-MM-DD)",
  "due_date": "تاريخ الاستحقاق (YYYY-MM-DD)",
  "subtotal": "المبلغ قبل الضريبة",
  "tax_amount": "مبلغ الضريبة",
  "total_amount": "المبلغ الإجمالي",
  "currency": "العملة",
  "items": [
    {
      "description": "وصف الصنف",
      "description_ar": "وصف الصنف بالعربية",
      "quantity": "الكمية",
      "unit_price": "سعر الوحدة",
      "item_total": "الإجمالي",
      "tax_amount": "ضريبة الصنف",
      "total_with_tax": "الإجمالي مع الضريبة"
    }
  ]
}"""

    system_instruction = getattr(settings, "system_instruction", None) or "أنت متخصص في استخراج بيانات الفواتير بدقة."
    prompt_instructions = getattr(settings, "prompt_instructions", None) or ""

    prompt = f"""
استخرج بيانات الفاتورة من نص OCR التالي.
- ممنوع التخمين أو اختراع قيم.
- أي قيمة غير موجودة: اتركها "" أو 0 للأرقام.
- أخرج JSON فقط وبنفس الشكل التالي:

{json_format}

{prompt_instructions}

نص OCR:
{ocr_text}
"""

    resp = client.chat.complete(
        model=chat_model,
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_tokens=4000,
        response_format={"type": "json_object"},
    )

    text = resp.choices[0].message.content
    data = _json_extract(text)
    if not data:
        raise Exception("Failed to parse JSON from chat response")
    return data

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
