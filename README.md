# AP Invoice Intelligence — Zamp ASA Case Study (PS-1)

A runnable invoice-to-decision workflow for the Zamp AI Solutions Analyst case study.

## What it does

1. Accepts a PDF invoice (or one of four included test invoices).
2. Extracts vendor, invoice number/date, PO number, currency, subtotal, tax and total.
3. Matches the vendor against a vendor master and checks vendor status.
4. Detects duplicate invoices by vendor + invoice number and by PDF SHA-256.
5. Matches the PO and checks vendor/currency consistency.
6. Reconciles subtotal + tax against invoice total.
7. Checks the invoice against the remaining PO balance, accounting for prior approved split invoices.
8. Produces an explainable decision, validation checklist and persistent audit history.

## Decision policy

- **APPROVED** — all configured controls pass.
- **PENDING REVIEW** — information is missing/ambiguous or a business discrepancy needs a human decision.
- **REJECTED** — a hard-stop control fails (e.g. duplicate invoice or blocked vendor).

Approval is not payment authorisation. The app does not initiate payments.

## Run locally (macOS / Windows / Linux)

Use Python 3.10+.

```bash
cd zamp_invoice_processor
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
streamlit run app.py
```

Open the local URL printed by Streamlit (normally http://localhost:8501).

## Demo scenarios

Use the **Process invoice** tab and select one of the bundled PDFs:

| File | Expected result | What it demonstrates |
|---|---|---|
| `01_happy_path.pdf` | APPROVED | Complete invoice, active vendor, matching PO and reconciled totals |
| `02_blocked_vendor.pdf` | REJECTED | Vendor is blocked in the master |
| `03_amount_mismatch.pdf` | REJECTED / review-worthy PO overrun | Invoice exceeds PO amount |
| `04_missing_fields.pdf` | PENDING REVIEW | Missing invoice number and PO reference |

Run `01_happy_path.pdf` a second time to demonstrate duplicate detection.

## Project structure

```text
app.py                  Streamlit UI, run view and operations dashboard
engine.py               PDF extraction, deterministic validation and decision logic
database.py             SQLite audit history
data/vendors.csv        Vendor master (demo data)
data/purchase_orders.csv Purchase-order register (demo data)
sample_invoices/        Four generated PDF test inputs
requirements.txt        Python dependencies
```

## Design choices and assumptions

- **Deterministic controls, not an LLM deciding financial outcomes.** Extraction is conservative and all financial/vendor/PO decisions are rule-based and explainable.
- **Exact vendor matching.** No fuzzy identity match is silently accepted; uncertain vendor identity is routed for review.
- **PO tolerance.** The UI exposes a configurable tolerance (default 2%). A tolerance is a business policy, not a universal accounting rule.
- **Split invoices.** Previously approved invoices reduce the PO's remaining balance. Pending/rejected invoices do not consume it.
- **Duplicate detection.** A matching vendor + invoice number or identical file hash is treated as a duplicate.
- **Human review.** Missing fields and uncertain extraction are not auto-approved.
- **OCR.** Embedded PDF text is preferred. If a PDF is image-only, the app attempts OCR with Tesseract. Install the Tesseract binary separately for scanned PDFs; without it, the app reports that text could not be read.
- **Demo data.** The CSV registers and invoices are synthetic. Replace them with a procurement/ERP integration and approved policy configuration for production.

## Known limitations / next steps

1. Regex-based extraction is a transparent baseline, not production-grade document understanding. Real vendor layouts need a schema-guided LLM or document AI extractor with field-level confidence and evidence spans.
2. Line-item matching is not implemented; the demo validates invoice-level totals against PO value.
3. The demo assumes a single currency per PO and a single invoice per upload.
4. SQLite is suitable for a local take-home demo; production should use managed PostgreSQL, authentication, role-based approvals and immutable audit events.
5. Production hardening should add malware scanning, file-size limits, access controls, retention policy, structured logs, retries and ERP integration.

## Five-minute demo outline

- **0:00–0:30** — Explain the operational problem and the invoice-to-decision goal.
- **0:30–1:30** — Run the happy-path PDF; show extracted fields, each validation and APPROVED outcome.
- **1:30–2:15** — Run the blocked-vendor case; explain why the system rejects it.
- **2:15–3:00** — Run the PO-overrun case; show the amount comparison and explain review/rejection policy.
- **3:00–3:45** — Run the missing-fields case; show PENDING REVIEW rather than guessing.
- **3:45–4:30** — Re-run the happy-path file to demonstrate duplicate detection.
- **4:30–5:00** — Show the dashboard/audit history and explain limitations + production roadmap.

## Interview talking points

- Financial decisions are deterministic and auditable; AI should assist extraction, not invent policy.
- The system fails safely: uncertain data is sent to a person rather than auto-approved.
- Each validation is independently visible and explains its outcome.
- The next production step is confidence-scored extraction plus PO line-item matching and ERP integration.
