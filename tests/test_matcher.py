import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

import helpers
from badcop.matcher import (Payment, PaymentsError, apply_matches, load_payments, match_payments, match_report_md,
                            parse_amount, parse_payment_date, tokens)


class ParsingTests(unittest.TestCase):
    def test_amounts(self):
        cases = {"1250.00": "1250.00", "1,250.00": "1250.00", "$1,250.00": "1250.00", "1.250,00": "1250.00",
                 "480": "480", "(99.00)": "-99.00", "-99.00": "-99.00", "12,50": "12.50", "€ 1 234,56": "1234.56"}
        for raw, want in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse_amount(raw), Decimal(want))
        with self.assertRaises(PaymentsError):
            parse_amount("n/a")

    def test_dates(self):
        for raw in ("2026-03-05", "05/03/2026", "05.03.2026", "2026/03/05", "05-03-2026", "Mar 05, 2026", "05 Mar 2026"):
            with self.subTest(raw=raw):
                self.assertEqual(parse_payment_date(raw), date(2026, 3, 5))
        with self.assertRaises(PaymentsError):
            parse_payment_date("yesterday")

    def test_tokens(self):
        self.assertEqual(tokens("ACH Payment from ACME Corp Ltd INV-1"), {"ach", "acme", "corp", "inv"} - {"inv"})


class LoadPaymentsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "payments.csv"

    def tearDown(self):
        self.tmp.cleanup()

    def load(self, text, **kw):
        self.path.write_text(text, encoding="utf-8")
        return load_payments(self.path, **kw)

    def test_bank_style_export(self):
        payments = self.load("Posting Date,Description,Amount\n03/05/2026,ACH ACME CORP,\"1,000.00\"\n03/06/2026,Card fee,-5.00\n03/07/2026,,\n")
        self.assertEqual(len(payments), 1)  # negative and blank amounts skipped
        self.assertEqual(payments[0], Payment(line=2, date=date(2026, 5, 3), amount=Decimal("1000.00"), description="ACH ACME CORP"))

    def test_processor_style_export_with_substring_detection(self):
        payments = self.load("created,customer name,net amount\n2026-03-05,Blue Fern,480.00\n")
        self.assertEqual(payments[0].description, "Blue Fern")
        self.assertEqual(payments[0].amount, Decimal("480.00"))

    def test_column_overrides_and_errors(self):
        text = "d,x,y\n2026-03-05,Blue Fern,480.00\n"
        payments = self.load(text, date_col="d", amount_col="y", desc_col="x")
        self.assertEqual(payments[0].amount, Decimal("480.00"))
        with self.assertRaisesRegex(PaymentsError, "could not detect the date column"):
            self.load(text)
        with self.assertRaisesRegex(PaymentsError, "could not detect the amount column"):
            self.load(text, date_col="d")
        with self.assertRaisesRegex(PaymentsError, "column 'nope' not found"):
            self.load(text, date_col="nope", amount_col="y", desc_col="x")
        with self.assertRaisesRegex(PaymentsError, "line 2: unrecognised date"):
            self.load("date,description,amount\nsoon,x,1\n")

    def test_missing_and_empty_files(self):
        with self.assertRaisesRegex(PaymentsError, "not found"):
            load_payments(self.path)
        with self.assertRaisesRegex(PaymentsError, "empty file"):
            self.load("")


class MatchTests(unittest.TestCase):
    def setUp(self):
        self.a = helpers.make_invoice("INV-1", client="Acme Corp", amount="1000.00", issued=date(2026, 2, 1))
        self.b = helpers.make_invoice("INV-2", client="Blue Fern Studio", email="hi@bf.example", amount="1000.00", issued=date(2026, 2, 10))
        self.c = helpers.make_invoice("INV-3", client="Acme Corp", amount="300.00", issued=date(2026, 2, 1), status="paid", paid_date=date(2026, 2, 20))
        self.d = helpers.make_invoice("INV-4", client="Zed", email="z@z.example", amount="55.55", issued=date(2026, 2, 1))

    def pay(self, amount, desc="", when=date(2026, 3, 1), line=2):
        return Payment(line=line, date=when, amount=Decimal(amount), description=desc)

    def test_unique_amount_match(self):
        r = match_payments([self.pay("55.55", "random")], [self.a, self.b, self.c, self.d])[0]
        self.assertEqual((r.confidence, r.invoice.invoice_id, r.reason), ("high", "INV-4", "unique amount match"))

    def test_tolerance(self):
        r = match_payments([self.pay("55.54")], [self.d])[0]
        self.assertEqual(r.confidence, "high")
        r = match_payments([self.pay("55.50")], [self.d])[0]
        self.assertEqual(r.confidence, "none")
        r = match_payments([self.pay("55.50")], [self.d], tolerance=Decimal("0.10"))[0]
        self.assertEqual(r.confidence, "high")

    def test_ambiguous_same_amount(self):
        r = match_payments([self.pay("1000.00", "wire transfer")], [self.a, self.b])[0]
        self.assertEqual(r.confidence, "ambiguous")
        self.assertIsNone(r.invoice)
        self.assertEqual(sorted(r.candidates), ["INV-1", "INV-2"])

    def test_disambiguate_by_invoice_id(self):
        r = match_payments([self.pay("1000.00", "Payment ref inv-2")], [self.a, self.b])[0]
        self.assertEqual((r.confidence, r.invoice.invoice_id), ("high", "INV-2"))
        self.assertIn("invoice id", r.reason)

    def test_disambiguate_by_client_name(self):
        r = match_payments([self.pay("1000.00", "ZELLE FROM BLUE FERN")], [self.a, self.b])[0]
        self.assertEqual((r.confidence, r.invoice.invoice_id), ("high", "INV-2"))
        self.assertIn("client name", r.reason)

    def test_paid_invoices_and_window_are_excluded(self):
        self.assertEqual(match_payments([self.pay("300.00", "ACME")], [self.c])[0].confidence, "none")
        self.assertEqual(match_payments([self.pay("1000.00", when=date(2026, 1, 31))], [self.a])[0].confidence, "none")  # before issue
        self.assertEqual(match_payments([self.pay("1000.00", when=date(2026, 9, 1))], [self.a])[0].confidence, "none")  # > 120 days
        self.assertEqual(match_payments([self.pay("1000.00", when=date(2026, 9, 1))], [self.a], window_days=365)[0].confidence, "high")

    def test_each_invoice_used_once(self):
        results = match_payments([self.pay("55.55", line=2), self.pay("55.55", line=3, when=date(2026, 3, 2))], [self.d])
        self.assertEqual([r.confidence for r in results], ["high", "none"])

    def test_apply_marks_paid_with_payment_date(self):
        results = match_payments([self.pay("55.55", when=date(2026, 3, 9)), self.pay("1000.00", "wire")], [self.a, self.b, self.d])
        self.assertEqual(apply_matches(results), 1)
        self.assertEqual((self.d.status, self.d.paid_date), ("paid", date(2026, 3, 9)))
        self.assertEqual(self.a.status, "open")

    def test_report(self):
        results = match_payments([self.pay("55.55"), self.pay("1000.00", "wire"), self.pay("1.00")], [self.a, self.b, self.d])
        md = match_report_md(results)
        self.assertIn("**1 matched**, 1 ambiguous, 1 unmatched", md)
        self.assertIn("| INV-1, INV-2 |", md)


if __name__ == "__main__":
    unittest.main()
