import sys, unittest
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from engine import process_invoice

class InvoiceWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vendors = pd.read_csv(ROOT/"data/vendors.csv").fillna("").to_dict("records")
        cls.pos = pd.read_csv(ROOT/"data/purchase_orders.csv").fillna("").to_dict("records")

    def run_sample(self, name, prior=None):
        p = ROOT/"sample_invoices"/name
        return process_invoice(p.read_bytes(), name, self.vendors, self.pos, prior or [])

    def test_happy_path_approved(self):
        result = self.run_sample("01_happy_path.pdf")
        self.assertEqual(result["status"], "APPROVED")
        self.assertEqual(result["total"], "118000.00")

    def test_blocked_vendor_rejected(self):
        result = self.run_sample("02_blocked_vendor.pdf")
        self.assertEqual(result["status"], "REJECTED")

    def test_po_overrun_rejected(self):
        result = self.run_sample("03_amount_mismatch.pdf")
        self.assertEqual(result["status"], "REJECTED")

    def test_missing_fields_pending_review(self):
        result = self.run_sample("04_missing_fields.pdf")
        self.assertEqual(result["status"], "PENDING REVIEW")

    def test_duplicate_detection(self):
        first = self.run_sample("01_happy_path.pdf")
        second = self.run_sample("01_happy_path.pdf", [first])
        self.assertEqual(second["status"], "REJECTED")
        self.assertTrue(any(c["check"] == "Duplicate detection" and not c["passed"] for c in second["checks"]))

if __name__ == "__main__":
    unittest.main()
