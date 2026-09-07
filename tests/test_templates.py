import tempfile
import unittest
from datetime import date
from pathlib import Path

import helpers
from badcop.schedule import build_due_step
from badcop.templates import DEFAULT_TEMPLATES, TemplateError, build_context, render, split_template, write_default_templates


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.cfg = helpers.make_config(base_dir=self.base)
        self.inv = helpers.make_invoice(amount="1250.5", due=date(2026, 3, 1), pay_link="https://pay.example/1")
        self.steps = {s.name: s for s in self.cfg.steps}

    def tearDown(self):
        self.tmp.cleanup()

    def due(self, step, today=date(2026, 3, 31)):
        return build_due_step(self.inv, self.steps[step], self.cfg, today)

    def test_every_default_template_renders(self):
        for name in DEFAULT_TEMPLATES:
            with self.subTest(step=name):
                subject, body = render(self.due(name), self.cfg, ["courtesy"])
                self.assertIn("INV-1", subject)
                self.assertNotIn("{", body)
                self.assertNotIn("}", subject)

    def test_context_values(self):
        ctx = build_context(self.due("final"), self.cfg, ["courtesy", "firm"])
        self.assertEqual(ctx["amount"], "1,250.50")
        self.assertEqual(ctx["days_overdue"], "30")
        self.assertEqual(ctx["late_fee"], "18.76")   # 1250.5*1.5%*30/30 = 18.7575 -> 18.76
        self.assertEqual(ctx["total_due"], "1,269.26")
        self.assertEqual(ctx["steps_sent"], "courtesy, firm")
        self.assertTrue(ctx["pay_link"].startswith("Pay online: https://pay.example/1"))
        self.assertEqual(ctx["owner_name"], "Sam")

    def test_days_overdue_never_negative_in_copy(self):
        ctx = build_context(self.due("courtesy", today=date(2026, 2, 26)), self.cfg, [])
        self.assertEqual(ctx["days_overdue"], "0")
        self.assertEqual(ctx["steps_sent"], "none")

    def test_empty_pay_link(self):
        self.inv.pay_link = ""
        ctx = build_context(self.due("friendly"), self.cfg, [])
        self.assertEqual(ctx["pay_link"], "")

    def test_custom_template_overrides_default(self):
        tpl_dir = self.cfg.templates_dir
        tpl_dir.mkdir()
        (tpl_dir / "firm.txt").write_text("Subject: Custom {invoice_id}\n\nPay up, {client_name}. {total_due}\n")
        subject, body = render(self.due("firm"), self.cfg, [])
        self.assertEqual(subject, "Custom INV-1")
        self.assertEqual(body, "Pay up, Acme Corp. 1,250.50\n")

    def test_unknown_placeholder_is_an_error(self):
        tpl_dir = self.cfg.templates_dir
        tpl_dir.mkdir()
        (tpl_dir / "firm.txt").write_text("Subject: x\n\n{bank_account}\n")
        with self.assertRaisesRegex(TemplateError, "unknown placeholder"):
            render(self.due("firm"), self.cfg, [])

    def test_template_must_start_with_subject(self):
        with self.assertRaisesRegex(TemplateError, "Subject"):
            split_template("Hello\n\nbody")

    def test_unknown_step_without_template(self):
        cfg = helpers.make_config(base_dir=self.base, steps=[{"offset_days": 1, "name": "mystery"}])
        due = build_due_step(self.inv, cfg.steps[0], cfg, date(2026, 3, 5))
        with self.assertRaisesRegex(TemplateError, "no template for step 'mystery'"):
            render(due, cfg, [])

    def test_write_default_templates(self):
        written = write_default_templates(self.base / "tpl")
        self.assertEqual(len(written), len(DEFAULT_TEMPLATES))
        (self.base / "tpl" / "firm.txt").write_text("Subject: mine\n\nkeep\n")
        self.assertEqual(write_default_templates(self.base / "tpl"), [])  # no overwrite by default
        self.assertEqual((self.base / "tpl" / "firm.txt").read_text(), "Subject: mine\n\nkeep\n")
        self.assertEqual(len(write_default_templates(self.base / "tpl", overwrite=True)), len(DEFAULT_TEMPLATES))


if __name__ == "__main__":
    unittest.main()
