import unittest
from datetime import date
from decimal import Decimal

import helpers
from badcop.schedule import build_due_step, days_overdue, fee_applies, late_fee, plan, steps_due
from badcop.state import State


class DaysOverdueTests(unittest.TestCase):
    def test_before_on_after(self):
        inv = helpers.make_invoice(due=date(2026, 3, 15))
        self.assertEqual(days_overdue(inv, date(2026, 3, 12)), -3)
        self.assertEqual(days_overdue(inv, date(2026, 3, 15)), 0)
        self.assertEqual(days_overdue(inv, date(2026, 4, 14)), 30)


class LateFeeTests(unittest.TestCase):
    def setUp(self):
        self.cfg = helpers.make_config()  # 1.5%/month, 3 grace days
        self.inv = helpers.make_invoice(amount="1000.00", due=date(2026, 3, 1))

    def test_zero_within_grace(self):
        self.assertEqual(late_fee(self.inv, self.cfg, date(2026, 3, 1)), Decimal("0.00"))
        self.assertEqual(late_fee(self.inv, self.cfg, date(2026, 3, 4)), Decimal("0.00"))  # day 3 = grace

    def test_simple_monthly_interest(self):
        # 30 days overdue: 1000 * 1.5% * 30/30 = 15.00
        self.assertEqual(late_fee(self.inv, self.cfg, date(2026, 3, 31)), Decimal("15.00"))
        # 46 days: 1000 * 0.015 * 46/30 = 23.00
        self.assertEqual(late_fee(self.inv, self.cfg, date(2026, 4, 16)), Decimal("23.00"))

    def test_rounding_to_cents(self):
        inv = helpers.make_invoice(amount="1250.00", due=date(2026, 3, 1))
        # 7 days: 1250*0.015*7/30 = 4.375 -> 4.38 (half up)
        self.assertEqual(late_fee(inv, self.cfg, date(2026, 3, 8)), Decimal("4.38"))

    def test_flat_fee_added(self):
        cfg = helpers.make_config(terms={"late_fee_flat": 25, "late_fee_pct": 0})
        self.assertEqual(late_fee(self.inv, cfg, date(2026, 3, 10)), Decimal("25.00"))
        self.assertEqual(late_fee(self.inv, cfg, date(2026, 3, 2)), Decimal("0.00"))

    def test_per_invoice_overrides(self):
        inv = helpers.make_invoice(amount="1000.00", due=date(2026, 3, 1), late_fee_pct=Decimal("3"), grace_days=0)
        self.assertEqual(late_fee(inv, self.cfg, date(2026, 3, 2)), Decimal("1.00"))  # 1000*3%*1/30

    def test_no_fee_when_pct_zero(self):
        cfg = helpers.make_config(terms={"late_fee_pct": 0})
        self.assertEqual(late_fee(self.inv, cfg, date(2026, 6, 1)), Decimal("0.00"))


class StepsDueTests(unittest.TestCase):
    def setUp(self):
        self.cfg = helpers.make_config()
        self.inv = helpers.make_invoice(due=date(2026, 3, 15))
        self.state = State()

    def names(self, today, cfg=None, state=None):
        return [s.name for s in steps_due(self.inv, cfg or self.cfg, today, state or self.state)]

    def test_nothing_before_first_offset(self):
        self.assertEqual(self.names(date(2026, 3, 1)), [])

    def test_each_rung_in_turn(self):
        self.assertEqual(self.names(date(2026, 3, 12)), ["courtesy"])
        self.assertEqual(self.names(date(2026, 3, 15)), ["courtesy"])  # day 0: friendly is +1
        self.assertEqual(self.names(date(2026, 3, 16)), ["friendly"])
        self.assertEqual(self.names(date(2026, 3, 22)), ["firm"])
        self.assertEqual(self.names(date(2026, 3, 29)), ["final"])
        self.assertEqual(self.names(date(2026, 5, 1)), ["escalate"])

    def test_only_latest_step_without_catch_up(self):
        self.assertEqual(self.names(date(2026, 4, 1)), ["final"])

    def test_catch_up_sends_every_missed_step(self):
        cfg = helpers.make_config(behaviour={"catch_up": True})
        self.assertEqual(self.names(date(2026, 4, 1), cfg=cfg), ["courtesy", "friendly", "firm", "final"])

    def test_sent_steps_are_skipped(self):
        self.state.record_sent("INV-1", "final", "<id>")
        self.assertEqual(self.names(date(2026, 4, 1)), [])
        cfg = helpers.make_config(behaviour={"catch_up": True})
        self.state.record_sent("INV-1", "courtesy", "<id>")
        self.assertEqual(self.names(date(2026, 4, 1), cfg=cfg), ["friendly", "firm"])

    def test_closed_invoices_get_nothing(self):
        for status in ("paid", "void"):
            self.inv.status = status
            self.assertEqual(self.names(date(2026, 4, 1)), [])


class BuildDueStepTests(unittest.TestCase):
    def setUp(self):
        self.cfg = helpers.make_config()
        self.inv = helpers.make_invoice(amount="1000.00", due=date(2026, 3, 1))
        self.steps = {s.name: s for s in self.cfg.steps}

    def test_fee_applies_from_flagged_step_onward(self):
        self.assertFalse(fee_applies(self.steps["firm"], self.cfg))
        self.assertTrue(fee_applies(self.steps["final"], self.cfg))
        self.assertTrue(fee_applies(self.steps["escalate"], self.cfg))

    def test_no_fee_on_early_steps_even_if_overdue(self):
        due = build_due_step(self.inv, self.steps["firm"], self.cfg, date(2026, 3, 31))
        self.assertEqual(due.late_fee, Decimal("0.00"))
        self.assertEqual(due.total_due, Decimal("1000.00"))
        self.assertEqual(due.days_overdue, 30)

    def test_fee_on_final_and_escalate(self):
        final = build_due_step(self.inv, self.steps["final"], self.cfg, date(2026, 3, 31))
        self.assertEqual(final.late_fee, Decimal("15.00"))
        self.assertEqual(final.total_due, Decimal("1015.00"))
        esc = build_due_step(self.inv, self.steps["escalate"], self.cfg, date(2026, 3, 31))
        self.assertEqual(esc.late_fee, Decimal("15.00"))


class PlanTests(unittest.TestCase):
    def test_plan_covers_all_open_invoices_in_order(self):
        cfg = helpers.make_config()
        invoices = [helpers.make_invoice("A", due=date(2026, 3, 1)), helpers.make_invoice("B", due=date(2026, 3, 20), status="paid"),
                    helpers.make_invoice("C", due=date(2026, 3, 14))]
        result = plan(invoices, cfg, date(2026, 3, 15), State())
        self.assertEqual([(d.invoice.invoice_id, d.step.name) for d in result], [("A", "final"), ("C", "friendly")])


if __name__ == "__main__":
    unittest.main()
