from __future__ import annotations
import re, io, hashlib
from decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import Any
import fitz

def money(value: Any):
    if value is None:
        return None
    s = str(value).replace(",", "").replace("₹", "").replace("$", "").replace("INR", "").strip()
    try:
        return Decimal(re.sub(r"[^0-9.\-]", "", s))
    except (InvalidOperation, ValueError):
        return None

def extract_text(pdf_bytes: bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = [p.get_text("text") for p in doc]
    text = "\n".join(pages).strip()
    method = "Embedded PDF text"
    if len(text) < 30:
        # Optional OCR fallback. Tesseract must be installed on the host.
        try:
            import pytesseract
            from PIL import Image
            chunks = []
            for page in doc:
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                chunks.append(pytesseract.image_to_string(img))
            text = "\n".join(chunks).strip()
            method = "OCR (Tesseract)"
        except Exception:
            method = "No readable text; OCR unavailable"
    return text, method

def _capture(patterns, text, flags=re.I|re.M):
    for pattern in patterns:
        m = re.search(pattern, text, flags)
        if m:
            return m.group(1).strip(" \t:,-")
    return None

def extract_invoice_fields(text: str):
    # Deliberately conservative regex extraction; ambiguous values are sent to review.
    vendor = _capture([
        r"(?:Vendor|Supplier|From)\s*[:\-]\s*(.+)",
        r"^([A-Z][A-Za-z0-9&.,'() \-]{2,50})\s*$"
    ], text)
    invoice_no = _capture([
        r"(?:Invoice\s*(?:Number|No\.?|#)|Inv\.?\s*#)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-\/]+)"
    ], text)
    po_no = _capture([
        r"(?:Purchase\s*Order|P\.?O\.?)\s*(?:Number|No\.?|#)?\s*[:\-]?\s*(PO[-A-Z0-9\/]+)"
    ], text)
    date = _capture([
        r"(?:Invoice\s*Date|Date)\s*[:\-]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})",
        r"(?:Invoice\s*Date|Date)\s*[:\-]\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})"
    ], text)
    currency = _capture([r"\b(INR|USD|EUR|GBP)\b"], text) or ("INR" if "₹" in text or "Rs." in text else None)
    subtotal_s = _capture([
        r"(?:Sub\s*total|Subtotal|Taxable\s*Amount)\s*[:\-]?\s*(?:INR|USD|₹|\$)?\s*([0-9,]+\.?[0-9]{0,2})"
    ], text)
    tax_s = _capture([
        r"(?:GST|IGST|CGST|SGST|VAT|Tax)\s*(?:Amount)?\s*[:\-]?\s*(?:INR|USD|₹|\$)?\s*([0-9,]+\.?[0-9]{0,2})"
    ], text)
    total_s = _capture([
        r"(?:Grand\s*Total|Invoice\s*Total|Total\s*Due|Total\s*Amount|\bTotal\b)\s*[:\-]?\s*(?:INR|USD|₹|\$)?\s*([0-9,]+\.?[0-9]{0,2})"
    ], text)
    return {
        "vendor_name": vendor, "invoice_number": invoice_no, "po_number": po_no,
        "invoice_date": date, "currency": currency,
        "subtotal": money(subtotal_s), "tax": money(tax_s), "total": money(total_s)
    }

def process_invoice(pdf_bytes: bytes, filename: str, vendors: list[dict], purchase_orders: list[dict],
                    prior_invoices: list[dict], tolerance_pct=Decimal("2.0")):
    text, extraction_method = extract_text(pdf_bytes)
    fields = extract_invoice_fields(text)
    checks, reasons, warnings = [], [], []
    digest = hashlib.sha256(pdf_bytes).hexdigest()

    def check(name, passed, detail, severity="block"):
        checks.append({"check": name, "passed": bool(passed), "detail": detail, "severity": severity})
        if not passed:
            (reasons if severity == "block" else warnings).append(detail)

    # Required data
    missing = [k for k in ("vendor_name", "invoice_number", "po_number", "total") if not fields.get(k)]
    check("Required fields", not missing, "All critical fields extracted." if not missing else "Missing/uncertain fields: " + ", ".join(missing), "review")

    # Vendor matching: exact normalized match only; never silently guess.
    norm = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower())
    vendor = next((v for v in vendors if norm(v["vendor_name"]) == norm(fields.get("vendor_name"))), None)
    check("Vendor identity", vendor is not None,
          f"Matched vendor: {vendor['vendor_name']}." if vendor else f"Vendor '{fields.get('vendor_name')}' is not in the vendor master.", "review")
    if vendor:
        check("Vendor status", vendor["status"].lower() == "active",
              f"Vendor status is {vendor['status']}." if vendor["status"].lower() != "active" else "Vendor is active.")

    # Duplicate detection by vendor + invoice number and exact file hash.
    duplicate = any(
        (fields.get("invoice_number") and x.get("invoice_number","").lower() == fields["invoice_number"].lower()
         and norm(x.get("vendor_name")) == norm(fields.get("vendor_name")))
        or x.get("file_hash") == digest for x in prior_invoices
    )
    check("Duplicate detection", not duplicate, "No duplicate found." if not duplicate else "Duplicate invoice number/vendor combination or identical PDF already processed.")

    po = next((p for p in purchase_orders if p["po_number"].lower() == (fields.get("po_number") or "").lower()), None)
    check("Purchase order match", po is not None,
          f"Matched {po['po_number']}." if po else f"PO '{fields.get('po_number')}' was not found.", "review" if not fields.get("po_number") else "block")

    if po and vendor:
        check("PO/vendor consistency", norm(po["vendor_name"]) == norm(vendor["vendor_name"]),
              "Invoice vendor matches the PO vendor." if norm(po["vendor_name"]) == norm(vendor["vendor_name"]) else "The PO belongs to a different vendor.")
    if po:
        check("Currency consistency", (fields.get("currency") or po["currency"]).upper() == po["currency"].upper(),
              f"Currency is {fields.get('currency') or 'not stated'}; PO currency is {po['currency']}." if fields.get("currency") and fields["currency"].upper() != po["currency"].upper() else f"Currency aligns with PO ({po['currency']}).")

    # Arithmetic validation
    subtotal, tax, total = fields.get("subtotal"), fields.get("tax"), fields.get("total")
    if total is not None and subtotal is not None and tax is not None:
        arithmetic_ok = abs((subtotal + tax) - total) <= Decimal("1.00")
        check("Invoice arithmetic", arithmetic_ok,
              "Subtotal + tax reconciles to invoice total." if arithmetic_ok else f"Subtotal + tax ({subtotal + tax}) does not equal total ({total}).")
    else:
        check("Invoice arithmetic", False, "Subtotal or tax could not be confidently extracted.", "review")

    if po and total is not None:
        # Include previously approved invoices against this PO to support split invoices.
        already_used = sum((money(x.get("total")) or Decimal("0")) for x in prior_invoices
                           if x.get("po_number","").lower() == po["po_number"].lower()
                           and x.get("status") == "APPROVED")
        remaining = money(po["amount"]) - already_used
        variance = abs(total - remaining) / max(remaining, Decimal("1")) * Decimal("100")
        within = total <= remaining * (Decimal("1") + tolerance_pct / Decimal("100"))
        check("PO amount / remaining balance", within,
              f"Invoice total {total} {po['currency']}; remaining PO balance {remaining} {po['currency']} (including {already_used} already approved)." if within
              else f"Invoice total {total} exceeds remaining PO balance {remaining} by {total-remaining}.")
        if total < remaining:
            warnings.append(f"Partial invoice: {total} against PO balance {remaining}; remaining balance will stay available for later invoices.")

    # Status precedence: hard blockers reject; uncertainty or review flags require human review.
    hard_fail = any(not c["passed"] and c["severity"] == "block" for c in checks)
    review_fail = any(not c["passed"] and c["severity"] == "review" for c in checks)
    if hard_fail:
        status = "REJECTED"
    elif review_fail:
        status = "PENDING REVIEW"
    else:
        status = "APPROVED"

    summary = {
        "status": status, "filename": filename, "file_hash": digest,
        "extraction_method": extraction_method, "raw_text": text,
        "fields": {k: (str(v) if isinstance(v, Decimal) else v) for k,v in fields.items()},
        "checks": checks, "reasons": reasons, "warnings": warnings,
        "vendor_name": fields.get("vendor_name"), "invoice_number": fields.get("invoice_number"),
        "po_number": fields.get("po_number"), "total": str(total) if total is not None else None,
        "processed_at": datetime.now().isoformat(timespec="seconds")
    }
    return summary
