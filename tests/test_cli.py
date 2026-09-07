import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers
from badcop import cli
from badcop.mailer import DryRunMailer, SendError

CONFIG = """[sender]
name = "Accounts, Test Studio"
email = "accounts@test.example"
reply_to = "me@test.example"
owner_email = "owner@test.example"
owner_name = "Sam"
[smtp]
host = "smtp.test.example"
username = "u"
password_env = "TEST_SMTP_PW"
[terms]
late_fee_pct = 1.5
"""


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


class Workspace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.prev = os.getcwd()
        os.chdir(self.dir)
        (self.dir / "badcop.toml").write_text(CONFIG)
        (self.dir / "invoices.csv").write_text(helpers.LEDGER_CSV)

    def tearDown(self):
        os.chdir(self.prev)
        self.tmp.cleanup()


class InitTests(unittest.TestCase):
    def test_init_creates_workspace_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, _ = run(["init", "--dir", d])
            self.assertEqual(code, 0)
            self.assertTrue((Path(d) / "badcop.toml").exists())
            self.assertTrue((Path(d) / "invoices.csv").exists())
            self.assertEqual(len(list((Path(d) / "templates").glob("*.txt"))), 5)
            code, _, err = run(["init", "--dir", d])
            self.assertEqual(code, 1)
            self.assertIn("--force", err)
            self.assertEqual(run(["init", "--dir", d, "--force"])[0], 0)
            # the generated workspace is itself valid
            code, out, err = run(["--config", f"{d}/badcop.toml", "--ledger", f"{d}/invoices.csv", "--state", f"{d}/state.json", "run", "--dry-run"])
            self.assertEqual(code, 0, err)


class RunTests(Workspace):
    def test_dry_run_sends_nothing_and_writes_no_state(self):
        code, out, _ = run(["run", "--dry-run", "--today", "2026-03-12"])
        self.assertEqual(code, 0)
        self.assertIn("DRY RUN INV-1 -> ap@acme.example [final, +25d]", out)
        self.assertIn("DRY RUN INV-2 -> hi@bluefern.example [courtesy, -3d]", out)
        self.assertIn("2 would be sent", out)
        self.assertFalse((self.dir / "state.json").exists())

    def test_verbose_dry_run_prints_body(self):
        _, out, _ = run(["run", "--dry-run", "-v", "--today", "2026-03-12"])
        self.assertIn("late fee of USD 12.50", out)  # 1000 * 1.5% * 25/30

    def test_nothing_due(self):
        code, out, _ = run(["run", "--dry-run", "--today", "2026-02-01"])
        self.assertEqual(code, 0)
        self.assertIn("nothing due", out)

    def test_real_run_records_state_and_is_idempotent(self):
        mailer = DryRunMailer()
        with mock.patch.object(cli, "SmtpMailer", return_value=mailer):
            code, out, _ = run(["run", "--today", "2026-03-12"])
            self.assertEqual(code, 0)
            self.assertIn("SENT    INV-1", out)
            self.assertEqual(len(mailer.sent), 2)
            self.assertEqual([m["To"] for m in mailer.sent], ["ap@acme.example", "hi@bluefern.example"])
            state = json.loads((self.dir / "state.json").read_text())
            self.assertEqual([s["step"] for s in state["INV-1"]["sent"]], ["final"])
            self.assertEqual([s["step"] for s in state["INV-2"]["sent"]], ["courtesy"])
            self.assertEqual(state["INV-1"]["sent"][0]["message_id"], mailer.sent[0]["Message-ID"])
            code, out, _ = run(["run", "--today", "2026-03-12"])
            self.assertEqual(code, 0)
            self.assertIn("nothing due", out)
            self.assertEqual(len(mailer.sent), 2)
            # a month later the escalation goes to the owner, and mentions what was already sent
            code, out, _ = run(["run", "--today", "2026-05-01"])
            self.assertEqual(code, 0)
            self.assertEqual(mailer.sent[2]["To"], "owner@test.example")
            self.assertIn("Reminders already sent: final", mailer.sent[2].get_content())

    def test_send_failure_exit_code_and_error_recorded(self):
        class Flaky:
            def send(self, msg, config):
                if msg.to.startswith("ap@"):
                    raise SendError("boom")
                return "<ok@x>"
        with mock.patch.object(cli, "SmtpMailer", return_value=Flaky()):
            code, out, err = run(["run", "--today", "2026-03-12"])
        self.assertEqual(code, 3)
        self.assertIn("FAILED  INV-1", err)
        self.assertIn("1 sent, 1 failed", out)
        state = json.loads((self.dir / "state.json").read_text())
        self.assertEqual(state["INV-1"]["last_error"], "boom")
        self.assertEqual(state["INV-1"]["sent"], [])
        self.assertEqual(state["INV-2"]["sent"][0]["step"], "courtesy")

    def test_bad_today(self):
        code, _, err = run(["run", "--dry-run", "--today", "31/03/2026"])
        self.assertEqual(code, 1)
        self.assertIn("--today", err)


class ErrorTests(Workspace):
    def test_config_error_exit_1(self):
        (self.dir / "badcop.toml").write_text("[sender]\nname='x'\n")
        code, _, err = run(["run", "--dry-run"])
        self.assertEqual(code, 1)
        self.assertIn("[sender].email", err)

    def test_ledger_error_exit_2(self):
        (self.dir / "invoices.csv").write_text("invoice_id,client_name,client_email,amount,issued_date\nINV-1,A,a@b.c,-5,2026-01-01\n")
        code, _, err = run(["run", "--dry-run"])
        self.assertEqual(code, 2)
        self.assertIn("amount must be positive", err)

    def test_template_error_exit_2(self):
        (self.dir / "templates").mkdir()
        (self.dir / "templates" / "final.txt").write_text("Subject: x\n\n{nope}\n")
        code, _, err = run(["run", "--dry-run", "--today", "2026-03-31"])
        self.assertEqual(code, 2)
        self.assertIn("unknown placeholder", err)


class PreviewTests(Workspace):
    def test_preview_latest_step(self):
        code, out, _ = run(["preview", "INV-1", "--today", "2026-03-12"])
        self.assertEqual(code, 0)
        self.assertIn("To: ap@acme.example", out)
        self.assertIn("Subject: Final notice: invoice INV-1, USD 1,012.50 now due", out)

    def test_preview_named_step_and_owner_routing(self):
        code, out, _ = run(["preview", "INV-1", "--step", "escalate", "--today", "2026-03-31"])
        self.assertEqual(code, 0)
        self.assertIn("To: owner@test.example", out)
        self.assertIn("Sam,", out)

    def test_preview_before_first_step_uses_first(self):
        _, out, _ = run(["preview", "INV-1", "--today", "2026-01-01"])
        self.assertIn("Subject: Invoice INV-1 is due on 2026-02-15", out)

    def test_preview_errors(self):
        self.assertEqual(run(["preview", "NOPE"])[0], 2)
        code, _, err = run(["preview", "INV-1", "--step", "nuclear"])
        self.assertEqual(code, 1)
        self.assertIn("unknown step", err)


class MatchTests(Workspace):
    def test_match_dry_run_then_apply(self):
        (self.dir / "payments.csv").write_text("Date,Description,Amount\n2026-03-05,ACH ACME CORP,1000.00\n2026-03-06,Unknown,12.34\n")
        code, out, _ = run(["match", "payments.csv"])
        self.assertEqual(code, 0)
        self.assertIn("**1 matched**, 0 ambiguous, 1 unmatched", out)
        self.assertIn("re-run with --apply", out)
        self.assertTrue((self.dir / "match_report.md").exists())
        self.assertIn("INV-1,Acme Corp,ap@acme.example,1000.00,USD,2026-02-01,2026-02-15,open", (self.dir / "invoices.csv").read_text())
        code, out, _ = run(["match", "payments.csv", "--apply"])
        self.assertEqual(code, 0)
        self.assertIn("Marked 1 invoices paid", out)
        self.assertIn("INV-1,Acme Corp,ap@acme.example,1000.00,USD,2026-02-01,2026-02-15,paid,2026-03-05", (self.dir / "invoices.csv").read_text())
        self.assertTrue((self.dir / "invoices.csv.bak").exists())

    def test_match_errors(self):
        self.assertEqual(run(["match", "missing.csv"])[0], 2)
        (self.dir / "p.csv").write_text("a,b\n1,2\n")
        code, _, err = run(["match", "p.csv"])
        self.assertEqual(code, 2)
        self.assertIn("could not detect", err)


class ReportTests(Workspace):
    def test_report_md_and_csv(self):
        code, out, _ = run(["report", "--today", "2026-03-31"])
        self.assertEqual(code, 0)
        self.assertIn("**Outstanding: USD 1,480.00** across 2 open invoices", out)
        self.assertTrue((self.dir / "aging_report.md").exists())
        self.assertTrue((self.dir / "aging_report.csv").exists())
        code, out, _ = run(["report", "--format", "csv", "--today", "2026-03-31", "--out", "custom"])
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("invoice_id,client_name"))
        self.assertTrue((self.dir / "custom.csv").exists())


if __name__ == "__main__":
    unittest.main()
