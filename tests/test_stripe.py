import json
import os
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest import mock

import helpers
from badcop import cli
from badcop.ledger import LedgerError, load_ledger
from badcop.stripe import StripeError, api_key_from_env, fetch_invoices, merge, to_invoice

STRIPE_OPEN = {"id": "in_1", "number": "A-0001", "status": "open", "currency": "usd", "amount_due": 125050, "total": 125050,
               "customer_email": "ap@acme.example", "customer_name": "Acme Corp", "created": 1772323200,  # 2026-03-01
               "due_date": 1773532800, "hosted_invoice_url": "https://pay.stripe.example/x", "status_transitions": {"paid_at": None}}
STRIPE_PAID = {**STRIPE_OPEN, "id": "in_2", "number": "A-0002", "status": "paid", "status_transitions": {"paid_at": 1772928000}}


class MappingTests(unittest.TestCase):
    def test_open_invoice(self):
        inv = to_invoice(STRIPE_OPEN, net_days=14)
        self.assertEqual(inv.invoice_id, "A-0001")
        self.assertEqual(inv.amount, Decimal("1250.50"))
        self.assertEqual(inv.currency, "USD")
        self.assertEqual(inv.issued_date, date(2026, 3, 1))
        self.assertEqual(inv.due_date, date(2026, 3, 15))
        self.assertEqual(inv.status, "open")
        self.assertIsNone(inv.paid_date)
        self.assertEqual(inv.pay_link, "https://pay.stripe.example/x")
        self.assertEqual(inv.notes, "stripe:in_1")

    def test_paid_invoice_and_zero_decimal_currency(self):
        inv = to_invoice({**STRIPE_PAID, "currency": "jpy", "total": 5000, "amount_due": 5000}, net_days=14)
        self.assertEqual((inv.status, inv.paid_date, inv.amount), ("paid", date(2026, 3, 8), Decimal("5000")))

    def test_due_date_defaults_to_net_days(self):
        inv = to_invoice({**STRIPE_OPEN, "due_date": None}, net_days=30)
        self.assertEqual(inv.due_date, date(2026, 3, 31))

    def test_skips_unusable(self):
        self.assertIsNone(to_invoice({**STRIPE_OPEN, "status": "draft"}, 14))
        self.assertIsNone(to_invoice({**STRIPE_OPEN, "amount_due": 0, "total": 0}, 14))
        # total is the principal; amount_due can be lower after a credit and must not be used when total exists
        self.assertEqual(to_invoice({**STRIPE_OPEN, "amount_due": 100}, 14).amount, Decimal("1250.50"))
        self.assertEqual(to_invoice({**STRIPE_OPEN, "total": None, "amount_due": 100}, 14).amount, Decimal("1.00"))
        self.assertIsNone(to_invoice({**STRIPE_OPEN, "customer_email": None}, 14))

    def test_falls_back_to_id_and_email(self):
        inv = to_invoice({**STRIPE_OPEN, "number": None, "customer_name": None}, 14)
        self.assertEqual((inv.invoice_id, inv.client_name), ("in_1", "ap@acme.example"))


class FetchTests(unittest.TestCase):
    def test_pagination_per_status(self):
        calls = []
        def fake(url, key):
            calls.append(url)
            if "status=open" in url and "starting_after" not in url:
                return {"data": [{"id": "in_a"}, {"id": "in_b"}], "has_more": True}
            if "status=open" in url:
                return {"data": [{"id": "in_c"}], "has_more": False}
            return {"data": [], "has_more": False}
        got = fetch_invoices("sk_test", fetch=fake)
        self.assertEqual([g["id"] for g in got], ["in_a", "in_b", "in_c"])
        self.assertEqual(len(calls), 3)
        self.assertIn("starting_after=in_b", calls[1])
        self.assertIn("status=paid", calls[2])

    def test_api_key_from_env(self):
        os.environ.pop("STRIPE_TEST_KEY", None)
        with self.assertRaisesRegex(StripeError, "STRIPE_TEST_KEY"):
            api_key_from_env("STRIPE_TEST_KEY")
        os.environ["STRIPE_TEST_KEY"] = "rk_test"
        try:
            self.assertEqual(api_key_from_env("STRIPE_TEST_KEY"), "rk_test")
        finally:
            del os.environ["STRIPE_TEST_KEY"]


class MergeTests(unittest.TestCase):
    def test_add_and_update(self):
        existing = [helpers.make_invoice("A-0001", amount="1250.50")]
        incoming = [to_invoice(STRIPE_OPEN, 14), to_invoice(STRIPE_PAID, 14)]
        ledger, added, updated = merge(existing, incoming)
        self.assertEqual((added, updated, len(ledger)), (1, 0, 2))
        paid_version = to_invoice({**STRIPE_OPEN, "status": "paid", "status_transitions": {"paid_at": 1772928000}}, 14)
        ledger, added, updated = merge(ledger, [paid_version])
        self.assertEqual((added, updated), (0, 1))
        self.assertEqual(ledger[0].status, "paid")
        self.assertEqual(ledger[0].paid_date, date(2026, 3, 8))


class UrlLedgerTests(unittest.TestCase):
    def test_load_from_url(self):
        cfg = helpers.make_config()
        class Resp:
            def __init__(self, data): self.data = data
            def read(self): return self.data
            def __enter__(self): return self
            def __exit__(self, *a): return False
        with mock.patch("badcop.ledger.urllib.request.urlopen", return_value=Resp(helpers.LEDGER_CSV.encode("utf-8"))) as u:
            invoices = load_ledger("https://docs.google.com/spreadsheets/d/x/pub?output=csv", cfg)
        self.assertEqual(len(invoices), 3)
        self.assertEqual(u.call_args.args[0].full_url, "https://docs.google.com/spreadsheets/d/x/pub?output=csv")

    def test_url_failure(self):
        cfg = helpers.make_config()
        import urllib.error
        with mock.patch("badcop.ledger.urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            with self.assertRaisesRegex(LedgerError, "could not fetch ledger"):
                load_ledger("https://example.com/l.csv", cfg)


class SyncCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.prev = os.getcwd()
        os.chdir(self.dir)
        (self.dir / "badcop.toml").write_text('[sender]\nname="A"\nemail="a@b.c"\n')
        os.environ["STRIPE_API_KEY"] = "rk_test"

    def tearDown(self):
        os.chdir(self.prev)
        self.tmp.cleanup()
        os.environ.pop("STRIPE_API_KEY", None)

    def run_cli(self, argv):
        import contextlib, io
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_sync_creates_and_updates_ledger(self):
        with mock.patch.object(cli, "fetch_invoices", return_value=[STRIPE_OPEN, STRIPE_PAID]):
            code, out, _ = self.run_cli(["sync", "stripe", "--dry-run"])
            self.assertEqual(code, 0)
            self.assertIn("would add 2", out)
            self.assertFalse((self.dir / "invoices.csv").exists())
            code, out, _ = self.run_cli(["sync", "stripe"])
            self.assertEqual(code, 0)
            self.assertIn("2 added, 0 updated", out)
        text = (self.dir / "invoices.csv").read_text()
        self.assertIn("A-0001,Acme Corp,ap@acme.example,1250.50,USD,2026-03-01,2026-03-15,open", text)
        self.assertIn("A-0002,Acme Corp,ap@acme.example,1250.50,USD,2026-03-01,2026-03-15,paid,2026-03-08", text)
        with mock.patch.object(cli, "fetch_invoices", return_value=[{**STRIPE_OPEN, "status": "paid", "status_transitions": {"paid_at": 1772928000}}]):
            code, out, _ = self.run_cli(["sync", "stripe"])
        self.assertIn("0 added, 1 updated", out)
        self.assertTrue((self.dir / "invoices.csv.bak").exists())

    def test_sync_errors(self):
        del os.environ["STRIPE_API_KEY"]
        code, _, err = self.run_cli(["sync", "stripe"])
        self.assertEqual(code, 2)
        self.assertIn("STRIPE_API_KEY", err)
        code, _, err = self.run_cli(["--ledger", "https://x/l.csv", "sync", "stripe"])
        self.assertEqual(code, 2)
        self.assertIn("not a URL", err)


if __name__ == "__main__":
    unittest.main()
