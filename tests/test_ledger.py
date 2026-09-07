import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

import helpers
from badcop.ledger import COLUMNS, LedgerError, load_ledger, save_ledger

HEADER = ",".join(COLUMNS) + "\n"


class LoadLedgerTests(unittest.TestCase):
    def setUp(self):
        self.cfg = helpers.make_config()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "invoices.csv"

    def tearDown(self):
        self.tmp.cleanup()

    def load(self, text):
        self.path.write_text(text, encoding="utf-8")
        return load_ledger(self.path, self.cfg)

    def test_valid_ledger(self):
        invoices = self.load(helpers.LEDGER_CSV)
        self.assertEqual([i.invoice_id for i in invoices], ["INV-1", "INV-2", "INV-3"])
        self.assertEqual(invoices[0].amount, Decimal("1000.00"))
        self.assertEqual(invoices[0].pay_link, "https://pay.example/1")
        self.assertTrue(invoices[0].is_open)
        self.assertFalse(invoices[2].is_open)
        self.assertEqual(invoices[2].paid_date, date(2026, 1, 20))

    def test_due_date_and_currency_default(self):
        inv = self.load(helpers.LEDGER_CSV)[1]
        self.assertEqual(inv.due_date, date(2026, 3, 15))  # issued + net_days 14
        self.assertEqual(inv.currency, "USD")

    def test_bom_and_blank_lines_and_whitespace(self):
        text = "﻿" + HEADER + " INV-9 , Zed , z@z.example , 10 ,,2026-01-01,,,,,,,\n\n,,,,,,,,,,,,\n"
        invoices = self.load(text)
        self.assertEqual(len(invoices), 1)
        self.assertEqual(invoices[0].invoice_id, "INV-9")
        self.assertEqual(invoices[0].client_name, "Zed")

    def test_missing_required_columns(self):
        with self.assertRaisesRegex(LedgerError, "missing required columns"):
            self.load("invoice_id,client_name\nINV-1,A\n")

    def test_missing_required_value(self):
        with self.assertRaisesRegex(LedgerError, "line 2: client_email is required"):
            self.load(HEADER + "INV-1,A,,10,,2026-01-01,,,,,,,\n")

    def test_bad_values(self):
        cases = {
            "INV-1,A,nope,10,,2026-01-01,,,,,,,": "not an email",
            "INV-1,A,a@b.c,0,,2026-01-01,,,,,,,": "amount must be positive",
            "INV-1,A,a@b.c,ten,,2026-01-01,,,,,,,": "amount must be a number",
            "INV-1,A,a@b.c,10,,01/01/2026,,,,,,,": "issued_date must be YYYY-MM-DD",
            "INV-1,A,a@b.c,10,,2026-01-10,2026-01-01,,,,,,": "before issued_date",
            "INV-1,A,a@b.c,10,,2026-01-01,,pending,,,,,": "status must be one of",
            "INV-1,A,a@b.c,10,,2026-01-01,,paid,,,,,": "paid invoices need a paid_date",
            "INV-1,A,a@b.c,10,,2026-01-01,,,,,x,,": "grace_days must be an integer",
        }
        for row, message in cases.items():
            with self.subTest(row=row), self.assertRaisesRegex(LedgerError, message):
                self.load(HEADER + row + "\n")

    def test_duplicate_ids(self):
        with self.assertRaisesRegex(LedgerError, "duplicate invoice_id"):
            self.load(HEADER + "INV-1,A,a@b.c,10,,2026-01-01,,,,,,,\nINV-1,B,b@b.c,20,,2026-01-01,,,,,,,\n")

    def test_missing_file(self):
        with self.assertRaisesRegex(LedgerError, "ledger not found"):
            load_ledger(self.path, self.cfg)

    def test_empty_file(self):
        with self.assertRaisesRegex(LedgerError, "empty file"):
            self.load("")

    def test_per_invoice_overrides(self):
        inv = self.load(HEADER + "INV-1,A,a@b.c,10,eur,2026-01-01,,,,2.5,10,,note here\n")[0]
        self.assertEqual(inv.currency, "EUR")
        self.assertEqual(inv.late_fee_pct, Decimal("2.5"))
        self.assertEqual(inv.grace_days, 10)
        self.assertEqual(inv.notes, "note here")


class SaveLedgerTests(unittest.TestCase):
    def test_round_trip_with_backup(self):
        cfg = helpers.make_config()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "invoices.csv"
            path.write_text(helpers.LEDGER_CSV, encoding="utf-8")
            invoices = load_ledger(path, cfg)
            invoices[0].status, invoices[0].paid_date = "paid", date(2026, 3, 1)
            save_ledger(path, invoices)
            self.assertTrue((Path(d) / "invoices.csv.bak").exists())
            self.assertEqual((Path(d) / "invoices.csv.bak").read_text(encoding="utf-8"), helpers.LEDGER_CSV)
            reloaded = load_ledger(path, cfg)
            self.assertEqual(reloaded[0].status, "paid")
            self.assertEqual(reloaded[0].paid_date, date(2026, 3, 1))
            self.assertEqual(reloaded[1].due_date, invoices[1].due_date)
            self.assertEqual(path.read_text(encoding="utf-8").splitlines()[0], ",".join(COLUMNS))


if __name__ == "__main__":
    unittest.main()
