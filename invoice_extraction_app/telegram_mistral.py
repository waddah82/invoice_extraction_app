"""
Telegram webhook integration for Frappe/ERPNext (webhook only).

Endpoint:
  /api/method/invoice_extraction_app.telegram_mistral.webhook

Behavior:
  - Accepts PDF documents and images (photo messages or image documents)
  - Creates a new "Extracted Invoice" doc
  - Saves the received file into "original_file" (Attach field)

Security:
  - Enabled via Telegram Settings.t_enabled
  - If Telegram Settings.admin_chat_id is set, only that chat is accepted

Notes:
  - Telegram webhook requires a public HTTPS URL (e.g., ngrok)
  - Do not use polling with this module
"""



from __future__ import annotations

import os
import mimetypes
from typing import Any, Dict, Optional, Tuple

import frappe
import requests
from frappe.model.naming import make_autoname


def _get_telegram_settings():
    """Read Telegram settings from single DocType 'Telegram Settings'."""
    if not frappe.db.exists("Telegram Settings", "Telegram Settings"):
        return None
    return frappe.get_single("Telegram Settings")


def _extract_message(update: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return update.get("message") or update.get("edited_message") or update.get("channel_post")


def _get_chat_id(message: Dict[str, Any]) -> Optional[int]:
    chat = message.get("chat") or {}
    return chat.get("id")


def _telegram_get_file(bot_token: str, file_id: str) -> Dict[str, Any]:
    url = f"https://api.telegram.org/bot{bot_token}/getFile"
    resp = requests.get(url, params={"file_id": file_id}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram getFile failed: {data}")
    return data["result"]


def _telegram_download_file(bot_token: str, file_path: str) -> bytes:
    url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    return resp.content


def _pick_file_from_message(message: Dict[str, Any]) -> Optional[Tuple[str, str, str]]:
    """Return (file_id, filename, kind) where kind is 'pdf' or 'image'."""
    doc = message.get("document")
    if doc:
        mime = (doc.get("mime_type") or "").lower()
        file_id = doc.get("file_id")
        file_name = doc.get("file_name") or "telegram_document"

        if mime == "application/pdf" or file_name.lower().endswith(".pdf"):
            return file_id, file_name, "pdf"

        if mime.startswith("image/") or any(file_name.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]):
            return file_id, file_name, "image"

        return None

    photos = message.get("photo")
    if photos and isinstance(photos, list):
        best = max(
            photos,
            key=lambda p: (p.get("file_size") or 0, p.get("width") or 0, p.get("height") or 0),
        )
        file_id = best.get("file_id")
        return file_id, "telegram_photo.jpg", "image"

    return None


def _infer_extension(filename: str, kind: str, mime_type: Optional[str] = None) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext:
        return ext
    if kind == "pdf":
        return ".pdf"
    if mime_type:
        guess = mimetypes.guess_extension(mime_type)
        if guess:
            return guess
    return ".jpg" if kind == "image" else ""

def _create_extracted_invoice_with_attachment(*, file_name: str, content: bytes, kind: str) -> str:
    # Pre-generate a Telegram-specific name
    inv_name = make_autoname("TG-EXT-INV-.#####")

    # Create File first (we already know attached_to_name)
    file_doc = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": file_name,
            "attached_to_doctype": "Extracted Invoice",
            "attached_to_name": inv_name,
            "is_private": 1,
            "content": content,
        }
    )
    file_doc.insert(ignore_permissions=True)

    # Now create invoice with mandatory original_file already set
    inv = frappe.new_doc("Extracted Invoice")
    inv.name = inv_name
    inv.flags.name_set = True  # prevent DocType autoname from overriding

    if hasattr(inv, "status"):
        inv.status = "Draft"
    if hasattr(inv, "file_type"):
        inv.file_type = kind

    inv.original_file = file_doc.file_url
    inv.insert(ignore_permissions=True)
    
    frappe.enqueue(
        "invoice_extraction_app.mistral.extract_and_update_extracted_invoice",
        queue="default",
        job_name=f"auto_extract_{inv.name}",
        invoice_name=inv.name,
        enqueue_after_commit=True,
    )

    frappe.db.commit()
    return inv.name

def _create_extracted_invoice_with_attachment1(*, file_name: str, content: bytes, kind: str) -> str:
    """Create Extracted Invoice, attach file into original_file, return docname."""
    # Telegram naming series (independent)
    inv_name = make_autoname("TG-EXT-INV-.#####")

    inv = frappe.new_doc("Extracted Invoice")
    inv.name = inv_name  # enforce independent name
    inv.status = "Draft"
    inv.file_type = kind
    inv.insert(ignore_permissions=True)

    file_doc = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": file_name,
            "attached_to_doctype": "Extracted Invoice",
            "attached_to_name": inv.name,
            "is_private": 1,
            "content": content,
        }
    )
    file_doc.insert(ignore_permissions=True)

    inv.original_file = file_doc.file_url
    inv.save(ignore_permissions=True)

    # Enqueue auto-extraction after commit to avoid race issues
    frappe.enqueue(
        "invoice_extraction_app.mistral.extract_and_update_extracted_invoice",
        queue="default",
        job_name=f"tg_extract_{inv.name}",
        invoice_name=inv.name,
        enqueue_after_commit=True,
    )

    frappe.db.commit()
    return inv.name


@frappe.whitelist(allow_guest=True)
def webhook() -> Dict[str, Any]:
    """Telegram webhook endpoint. Telegram will POST updates here."""
    try:
        settings = _get_telegram_settings()
        if not settings:
            return {"ok": False, "error": "Telegram Settings not found"}

        if not getattr(settings, "t_enabled", 0):
            return {"ok": True, "ignored": "Telegram integration disabled"}

        bot_token = getattr(settings, "bot_token", None)
        if not bot_token:
            return {"ok": False, "error": "bot_token is not set in Telegram Settings"}

        update = frappe.local.form_dict or {}
        if not update and frappe.request:
            try:
                update = frappe.request.get_json(silent=True) or {}
            except Exception:
                update = {}

        message = _extract_message(update)
        if not message:
            return {"ok": True, "ignored": "No message in update"}

        chat_id = _get_chat_id(message)
        admin_chat_id = getattr(settings, "admin_chat_id", None)
        if admin_chat_id not in (None, "", 0):
            try:
                if int(chat_id or 0) != int(admin_chat_id):
                    return {"ok": True, "ignored": "Unauthorized chat"}
            except Exception:
                return {"ok": True, "ignored": "Unauthorized chat"}

        picked = _pick_file_from_message(message)
        if not picked:
            return {"ok": True, "ignored": "No supported file"}

        file_id, file_name, kind = picked

        file_meta = _telegram_get_file(bot_token, file_id)
        file_path = file_meta.get("file_path")
        if not file_path:
            return {"ok": False, "error": "Telegram did not return file_path"}

        content = _telegram_download_file(bot_token, file_path)

        ext = _infer_extension(file_name, kind, file_meta.get("mime_type"))
        if ext and not file_name.lower().endswith(ext):
            file_name = f"{file_name}{ext}" if not file_name.endswith(".") else f"{file_name}{ext.lstrip('.')}"

        inv_name = _create_extracted_invoice_with_attachment(
            file_name=file_name,
            content=content,
            kind=kind,
        )

        return {
            "ok": True,
            "created": {"doctype": "Extracted Invoice", "name": inv_name},
            "auto_extract_enqueued": True,
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Telegram Webhook Error")
        return {"ok": False, "error": str(e)}


@frappe.whitelist()
def setup_webhook1(webhook_base_url: Optional[str] = None) -> Dict[str, Any]:
    """
    Sets Telegram webhook using Telegram Settings.
    Stores computed URLs back into Telegram Settings (read-only fields).

    Usage (server-side):
      bench --site <site> execute invoice_extraction_app.telegram_mistral.setup_webhook --kwargs "{'webhook_base_url':'https://...'}"
    """
    settings = _get_settings()
    if not settings:
        return {"ok": False, "error": "missing_settings"}

    if not _is_enabled(settings):
        return {"ok": False, "error": "disabled"}

    bot_token = _get_bot_token(settings)
    if not bot_token:
        return {"ok": False, "error": "missing_bot_token"}

    base = (webhook_base_url or "").strip().rstrip("/")
    if not base:
        base = _public_base_url(settings) or frappe.utils.get_url().rstrip("/")

    webhook_url = f"{base}/api/method/invoice_extraction_app.telegram_mistral.webhook"

    if not webhook_url.lower().startswith("https://"):
        return {"ok": False, "error": "webhook_requires_https", "computed_webhook_url": webhook_url}

    url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
    resp = requests.post(url, data={"url": webhook_url}, timeout=30)

    try:
        payload = resp.json()
    except Exception:
        payload = {"ok": False, "raw": resp.text}

    if not resp.ok or not payload.get("ok"):
        return {"ok": False, "computed_webhook_url": webhook_url, "telegram_response": payload}

    # Store computed URLs in settings (ignore permissions to allow non-admin setup via UI button if needed)
    try:
        settings.webhook_url = webhook_url
        settings.public_base_url = base
        settings.ngrok_url = base
        settings.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        pass

    return {"ok": True, "computed_webhook_url": webhook_url, "telegram_response": payload}


@frappe.whitelist()
def setup_webhook() -> Dict[str, Any]:
    """Activate webhook using Telegram Settings (UI friendly)."""
    settings = _get_telegram_settings()
    if not settings:
        return {"ok": False, "error": "Telegram Settings not found"}

    if not getattr(settings, "t_enabled", 0):
        return {"ok": False, "error": "Telegram integration is disabled"}

    bot_token = getattr(settings, "bot_token", None)
    if not bot_token:
        return {"ok": False, "error": "bot_token is not set in Telegram Settings"}

    public_base_url = (getattr(settings, "public_base_url", None) or getattr(settings, "ngrok_url", None) or "").strip()
    if not public_base_url:
        return {"ok": False, "error": "public_base_url is empty"}

    public_base_url = public_base_url.rstrip("/")
    webhook_url = f"{public_base_url}/api/method/invoice_extraction_app.telegram_mistral.webhook"

    if not webhook_url.lower().startswith("https://"):
        return {"ok": False, "error": "webhook_requires_https", "computed_webhook_url": webhook_url}

    api_url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
    resp = requests.post(api_url, data={"url": webhook_url}, timeout=30)
    data = resp.json()

    # Save display fields
    try:
        settings.ngrok_url = public_base_url
    except Exception:
        pass
    try:
        settings.public_base_url = public_base_url
    except Exception:
        pass
    try:
        settings.webhook_url = webhook_url
    except Exception:
        pass

    settings.save(ignore_permissions=True)
    frappe.db.commit()

    if not data.get("ok"):
        return {"ok": False, "computed_webhook_url": webhook_url, "telegram_response": data}

    return {"ok": True, "computed_webhook_url": webhook_url, "telegram_response": data}


@frappe.whitelist()
def webhook_info() -> Dict[str, Any]:
    """Return Telegram getWebhookInfo."""
    settings = _get_telegram_settings()
    if not settings:
        return {"ok": False, "error": "Telegram Settings not found"}

    bot_token = getattr(settings, "bot_token", None)
    if not bot_token:
        return {"ok": False, "error": "bot_token is not set in Telegram Settings"}

    url = f"https://api.telegram.org/bot{bot_token}/getWebhookInfo"
    resp = requests.get(url, timeout=30)
    try:
        return resp.json()
    except Exception:
        return {"ok": False, "raw": resp.text}


@frappe.whitelist()
def disable_webhook(drop_pending_updates: int = 0) -> Dict[str, Any]:
    """Disable Telegram webhook."""
    settings = _get_telegram_settings()
    if not settings:
        return {"ok": False, "error": "Telegram Settings not found"}

    bot_token = getattr(settings, "bot_token", None)
    if not bot_token:
        return {"ok": False, "error": "bot_token is not set in Telegram Settings"}

    url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
    resp = requests.post(
        url,
        data={"url": "", "drop_pending_updates": bool(int(drop_pending_updates or 0))},
        timeout=30,
    )

    try:
        data = resp.json()
    except Exception:
        data = {"ok": False, "raw": resp.text}

    if not resp.ok or not data.get("ok"):
        return {"ok": False, "telegram_response": data}

    # Clear stored URL field for display
    try:
        settings.webhook_url = ""
        settings.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        pass

    return {"ok": True, "telegram_response": data}
