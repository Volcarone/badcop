import csv
import io
import unittest
from datetime import date
from decimal import Decimal

import helpers
from badcop.report import aging, bucket_for, report_csv, report_md


class BucketTests(unittest.TestCase):
    def test_buckets(self):
        self.assertEqual(bucket_for(-10), "current")
        self.assertEqual(bucket_for(0), "current")
        self.assertEqual(bucket_for(1), "1-7")
        self.assertEqual(bucket_for(7), "1-7")
        self.assertEqual(bucket_for(8), "8-14")
        self.assertEqual(bucket_for(14), "8-14")
        self.assertEqual(bucket_for(15), "15-30")
        self.assertEqual(bucket_for(30), "15-30")
        self.assertEqual(bucket_for(31), "31+")
        self.assertEqual(bucket_for(400), "31+")


class AgingTests(unittest.TestCase):
    def setUp(self):
        self.cfg = helpers.make_config()  # 1.5%/mo, grace 3
        self.today = date(2026, 3, 31)
        self.invoices = [
            helpers.make_invoice("A", client="Acme", amount="1000.00", due=date(2026, 3, 1)),     # 30 days -> fee 15.00
            helpers.make_invoice("B", client="Acme", amount="200.00", due=date(2026, 3, 28)),     # 3 days, in grace
            helpers.make_invoice("C", client="Blue", amount="500.00", due=date(2026, 4, 10)),     # not yet due
            helpers.make_invoice("D", client="Blue", amount="999.00", due=date(2026, 1, 1), status="paid", paid_date=date(2026, 1, 2)),
        ]
        self.data = aging(self.invoices, self.cfg, self.today)

    def test_totals(self):
        self.assertEqual(self.data["total_outstanding"], Decimal("1700.00"))
        self.assertEqual(self.data["total_late_fees"], Decimal("15.00"))
        self.assertEqual(len(self.data["rows"]), 3)

    def test_buckets_and_clients(self):
        b = self.data["buckets"]
        self.assertEqual((b["current"]["count"], b["current"]["amount"]), (1, Decimal("500.00")))
        self.assertEqual((b["1-7"]["count"], b["1-7"]["amount"]), (1, Decimal("200.00")))
        self.assertEqual((b["15-30"]["count"], b["15-30"]["amount"]), (1, Decimal("1000.00")))
        self.assertEqual(self.data["clients"]["Acme"], {"count": 2, "amount": Decimal("1200.00"), "oldest_days": 30})
        self.assertEqual(self.data["clients"]["Blue"]["oldest_days"], -10)

    def test_rows_sorted_oldest_first(self):
        self.assertEqual([r["invoice_id"] for r in self.data["rows"]], ["A", "B", "C"])
        self.assertEqual(self.data["rows"][0]["total_due"], Decimal("1015.00"))

    def test_markdown(self):
        md = report_md(self.data, "USD")
        self.assertIn("# Aging report as of 2026-03-31", md)
        self.assertIn("**Outstanding: USD 1,700.00** across 3 open invoices", md)
        self.assertIn("| 15-30 | 1 | 1,000.00 |", md)
        self.assertIn("| Acme | 2 | 1,200.00 | 30 |", md)
        self.assertIn("| A | Acme | 2026-03-01 | 30 | 1,000.00 | 15.00 | 1,015.00 |", md)

    def test_csv(self):
        rows = list(csv.DictReader(io.StringIO(report_csv(self.data))))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0], {"invoice_id": "A", "client_name": "Acme", "currency": "USD", "due_date": "2026-03-01",
                                   "days_overdue": "30", "bucket": "15-30", "amount": "1000.00", "late_fee": "15.00", "total_due": "1015.00"})

    def test_empty_ledger(self):
        data = aging([], self.cfg, self.today)
        self.assertEqual(data["total_outstanding"], Decimal("0"))
        self.assertIn("across 0 open invoices", report_md(data, "USD"))


if __name__ == "__main__":
    unittest.main()
