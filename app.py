import streamlit as st
import pandas as pd, json, io
from decimal import Decimal
from pathlib import Path
from engine import process_invoice
from database import history, save_run

ROOT = Path(__file__).parent
st.set_page_config(page_title="AP Invoice Intelligence", page_icon="🧾", layout="wide")
st.markdown("""
<style>
.block-container {padding-top: 1.6rem; max-width: 1450px;}
[data-testid="stMetric"] {background: #f7f9fc; border: 1px solid #e8edf4; padding: 14px; border-radius: 12px;}
.small-muted {color:#667085;font-size:0.88rem}
</style>
""", unsafe_allow_html=True)

@st.cache_data
def load_csv(name):
    return pd.read_csv(ROOT/"data"/name).fillna("").to_dict("records")

vendors = load_csv("vendors.csv")
pos = load_csv("purchase_orders.csv")
runs = history()
st.title("🧾 AP Invoice Intelligence")
st.caption("Invoice-to-PO processing · deterministic controls · explainable decisions · human review")

tab_process, tab_dashboard, tab_rules = st.tabs(["⚡ Process invoice", "📊 Operations dashboard", "⚙️ Rules & reference data"])

with tab_process:
    left, right = st.columns([1.05, 1])
    with left:
        st.subheader("1. Submit an invoice")
        uploaded = st.file_uploader("Upload invoice PDF", type=["pdf"], help="Text PDFs are supported. Scanned PDFs use optional Tesseract OCR.")
        sample_files = sorted((ROOT/"sample_invoices").glob("*.pdf"))
        selected_sample = st.selectbox("Or try a prepared test invoice", ["— Select sample —"]+[p.name for p in sample_files])
        tolerance = st.slider("PO amount tolerance (%)", 0.0, 10.0, 2.0, 0.5)
        run_btn = st.button("Run invoice processing", type="primary", disabled=(uploaded is None and selected_sample == "— Select sample —"), use_container_width=True)
        st.info("The system never initiates payment. APPROVED means the invoice passed configured checks and is eligible for AP review/payment workflow.")
    with right:
        st.subheader("2. What happens")
        stages = ["Extract invoice fields", "Identify vendor", "Detect duplicates", "Match purchase order", "Validate amounts & tax", "Produce decision + audit trail"]
        for i, stage in enumerate(stages, 1):
            st.markdown(f"**{i}.** {stage}")
        st.caption("Each stage is logged and its result is visible after execution.")

    if run_btn:
        if uploaded is not None:
            pdf_bytes, filename = uploaded.getvalue(), uploaded.name
        else:
            p = ROOT/"sample_invoices"/selected_sample
            pdf_bytes, filename = p.read_bytes(), p.name
        prior = []
        for row in history():
            try:
                prior.append(json.loads(row["result_json"]))
            except Exception:
                pass
        progress = st.progress(0)
        status_box = st.status("Processing invoice…", expanded=True)
        with status_box:
            st.write("① Reading PDF and extracting text…")
            progress.progress(15)
            result = process_invoice(pdf_bytes, filename, vendors, pos, prior, Decimal(str(tolerance)))
            st.write(f"② Extraction method: **{result['extraction_method']}**")
            progress.progress(35)
            st.write("③ Checking vendor identity and status…")
            progress.progress(50)
            st.write("④ Checking duplicate history and matching PO…")
            progress.progress(70)
            st.write("⑤ Validating arithmetic, currency and PO balance…")
            progress.progress(90)
            save_run(result)
            st.write("⑥ Decision saved to audit history.")
            progress.progress(100)
            status_box.update(label=f"Completed — {result['status']}", state="complete", expanded=True)
        st.session_state["latest_result"] = result

    result = st.session_state.get("latest_result")
    if result:
        st.divider()
        st.subheader("3. Processing decision")
        color = {"APPROVED":"green", "PENDING REVIEW":"orange", "REJECTED":"red"}.get(result["status"], "gray")
        st.markdown(f"### :{color}[{result['status']}]")
        a,b,c,d = st.columns(4)
        a.metric("Vendor", result.get("vendor_name") or "Not extracted")
        b.metric("Invoice #", result.get("invoice_number") or "Not extracted")
        c.metric("PO #", result.get("po_number") or "Not matched")
        d.metric("Invoice total", result.get("total") or "Unknown")
        st.markdown("#### Validation checklist")
        st.dataframe(pd.DataFrame(result["checks"]), use_container_width=True, hide_index=True)
        if result["reasons"]:
            st.error("Issues requiring action\n\n" + "\n".join("• "+x for x in result["reasons"]))
        if result["warnings"]:
            st.warning("Notes\n\n" + "\n".join("• "+x for x in result["warnings"]))
        with st.expander("Extracted fields and source text"):
            st.json(result["fields"])
            st.text_area("Extracted PDF text", result["raw_text"], height=180)
        st.download_button("Download decision report (JSON)", json.dumps(result, indent=2), file_name=f"decision_{result.get('invoice_number') or 'invoice'}.json", mime="application/json")

with tab_dashboard:
    st.subheader("Processing overview")
    rows = history()
    if rows:
        df = pd.DataFrame([{k:r.get(k) for k in ["id","processed_at","filename","status","vendor_name","invoice_number","po_number","total"]} for r in rows])
        total = len(df)
        approved = int((df.status=="APPROVED").sum())
        review = int((df.status=="PENDING REVIEW").sum())
        rejected = int((df.status=="REJECTED").sum())
        m1,m2,m3,m4 = st.columns(4)
        m1.metric("Total processed", total)
        m2.metric("Approved", approved)
        m3.metric("Pending review", review)
        m4.metric("Rejected", rejected)
        st.dataframe(df, use_container_width=True, hide_index=True)
        csv = df.to_csv(index=False).encode()
        st.download_button("Export run history (CSV)", csv, "invoice_run_history.csv", "text/csv")
    else:
        st.info("No invoices processed yet. Run a sample invoice to populate the dashboard.")

with tab_rules:
    st.subheader("Configured controls")
    st.markdown("""
    | Control | Behaviour |
    |---|---|
    | Required fields | Vendor, invoice number, PO number and total must be extracted |
    | Vendor master | Exact normalized vendor-name match; vendor must be active |
    | Duplicate detection | Vendor + invoice number and exact PDF hash |
    | PO matching | Invoice must reference a PO present in the PO register |
    | Vendor / PO consistency | Invoice vendor must match the PO vendor |
    | Currency | Invoice currency must align with PO currency |
    | Arithmetic | Subtotal + tax must reconcile to total within ₹1 |
    | PO tolerance | Configurable percentage above remaining PO balance |
    | Split invoices | Previously approved invoices reduce remaining PO balance |
    | Human review | Uncertain arithmetic/extraction is not auto-approved |
    """)
    st.markdown("#### Vendor master")
    st.dataframe(pd.DataFrame(vendors), use_container_width=True, hide_index=True)
    st.markdown("#### Purchase order register")
    st.dataframe(pd.DataFrame(pos), use_container_width=True, hide_index=True)
    st.caption("Demo data only. Replace CSV files with an ERP/procurement connector before production use.")
