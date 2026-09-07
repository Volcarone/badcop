"""Which reminder is due for which invoice, and what it costs the client."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from .config import Config, Step
from .ledger import Invoice
from .state import State

CENT = Decimal("0.01")


@dataclass(frozen=True)
class DueStep:
    invoice: Invoice
    step: Step
    days_overdue: int
    late_fee: Decimal
    total_due: Decimal


def days_overdue(invoice: Invoice, today: date) -> int:
    """Negative before the due date, zero on it, positive after."""
    return (today - invoice.due_date).days


def late_fee(invoice: Invoice, config: Config, today: date) -> Decimal:
    """Simple monthly interest on the principal after the grace period, plus any flat fee.

    Computed only from the user's own terms; BadCop never invents a fee.
    """
    grace = invoice.grace_days if invoice.grace_days is not None else config.grace_days
    overdue = days_overdue(invoice, today)
    if overdue <= grace:
        return Decimal("0.00")
    pct = invoice.late_fee_pct if invoice.late_fee_pct is not None else config.late_fee_pct
    fee = invoice.amount * pct / Decimal(100) * Decimal(overdue) / Decimal(30) + config.late_fee_flat
    return fee.quantize(CENT, rounding=ROUND_HALF_UP)


def steps_due(invoice: Invoice, config: Config, today: date, state: State) -> list[Step]:
    """Steps whose offset has passed and which have not been sent yet.

    With catch_up=False (default) only the latest such step is returned, so the first run
    against an old ledger does not fire a whole ladder of emails at one client.
    """
    if not invoice.is_open:
        return []
    overdue = days_overdue(invoice, today)
    reached = [s for s in config.steps if s.offset_days <= overdue]
    if not reached:
        return []
    if not config.catch_up:
        reached = reached[-1:]
    return [s for s in reached if not state.has_sent(invoice.invoice_id, s.name)]


def fee_applies(step: Step, config: Config) -> bool:
    """The late fee is applied from the first step flagged apply_late_fee and stays applied after it."""
    return any(s.apply_late_fee for s in config.steps if s.offset_days <= step.offset_days)


def build_due_step(invoice: Invoice, step: Step, config: Config, today: date) -> DueStep:
    fee = late_fee(invoice, config, today) if fee_applies(step, config) else Decimal("0.00")
    return DueStep(invoice=invoice, step=step, days_overdue=days_overdue(invoice, today), late_fee=fee,
                   total_due=(invoice.amount + fee).quantize(CENT))


def plan(invoices: list[Invoice], config: Config, today: date, state: State) -> list[DueStep]:
    """Everything that should go out today, in ledger order then ladder order."""
    return [build_due_step(inv, step, config, today) for inv in invoices for step in steps_due(inv, config, today, state)]
