"""Match bank / processor CSV lines to open invoices and close the ones that were paid."""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .ledger import Invoice

DATE_COLS = ("date", "posted", "transaction date", "posting date", "value date", "booking date", "created")
AMOUNT_COLS = ("amount", "credit", "deposit", "paid in", "money in", "net", "gross")
DESC_COLS = ("description", "memo", "payee", "details", "reference", "narrative", "name", "counterparty")
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y", "%Y/%m/%d", "%d-%m-%Y", "%b %d, %Y", "%d %b %Y")
STOPWORDS = {"the", "and", "ltd", "llc", "inc", "gmbh", "payment", "transfer", "invoice", "inv", "ref", "from"}


class PaymentsError(ValueError):
    pass


@dataclass
class Payment:
    line: int
    date: date
    amount: Decimal
    description: str


@dataclass
class MatchResult:
    payment: Payment
    invoice: Invoice | None
    confidence: str  # "high" | "ambiguous" | "none"
    reason: str
    candidates: list[str] = field(default_factory=list)


def _find_col(fieldnames: list[str], wanted: tuple[str, ...], override: str | None, what: str) -> str:
    if override:
        if override not in fieldnames:
            raise PaymentsError(f"{what} column {override!r} not found; columns are {fieldnames}")
        return override
    lowered = {f.lower().strip(): f for f in fieldnames}
    for w in wanted:
        if w in lowered:
            return lowered[w]
    for f in fieldnames:  # substring fallback
        if any(w in f.lower() for w in wanted):
            return f
    raise PaymentsError(f"could not detect the {what} column in {fieldnames}; pass --{what}-col")


def parse_payment_date(raw: str) -> date:
    raw = raw.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise PaymentsError(f"unrecognised date {raw!r}")


def parse_amount(raw: str) -> Decimal:
    cleaned = re.sub(r"[^\d.,\-()]", "", raw.strip())
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.strip("()")
    if cleaned.count(",") and cleaned.count("."):
        cleaned = cleaned.replace(",", "") if cleaned.rfind(".") > cleaned.rfind(",") else cleaned.replace(".", "").replace(",", ".")
    elif cleaned.count(",") == 1 and len(cleaned.split(",")[1]) == 2:
        cleaned = cleaned.replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    try:
        value = Decimal(cleaned)
    except InvalidOperation as e:
        raise PaymentsError(f"unrecognised amount {raw!r}") from e
    return -value if negative else value


def load_payments(path: Path, date_col: str | None = None, amount_col: str | None = None,
                  desc_col: str | None = None) -> list[Payment]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError as e:
        raise PaymentsError(f"payments file not found: {path}") from e
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        raise PaymentsError(f"{path}: empty file")
    d, a, s = (_find_col(reader.fieldnames, DATE_COLS, date_col, "date"),
               _find_col(reader.fieldnames, AMOUNT_COLS, amount_col, "amount"),
               _find_col(reader.fieldnames, DESC_COLS, desc_col, "desc"))
    payments = []
    for line, row in enumerate(reader, start=2):
        if not (row.get(a) or "").strip():
            continue
        try:
            amount = parse_amount(row[a])
            when = parse_payment_date(row[d])
        except PaymentsError as e:
            raise PaymentsError(f"line {line}: {e}") from e
        if amount <= 0:
            continue  # outgoing money can't pay an invoice
        payments.append(Payment(line=line, date=when, amount=amount, description=(row.get(s) or "").strip()))
    return payments


def tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) >= 3 and t not in STOPWORDS}


def match_payments(payments: list[Payment], invoices: list[Invoice], tolerance: Decimal = Decimal("0.01"),
                   window_days: int = 120) -> list[MatchResult]:
    """Match each payment to at most one open invoice; each invoice is used at most once.

    High confidence needs a unique amount match, or an amount match whose description carries the
    invoice id or the client name. Everything else is reported as ambiguous or unmatched.
    """
    open_by_id = {inv.invoice_id: inv for inv in invoices if inv.is_open}
    used: set[str] = set()
    results = []
    for p in sorted(payments, key=lambda x: (x.date, x.line)):
        desc_tokens = tokens(p.description)
        desc_lower = p.description.lower()
        candidates = [inv for inv in open_by_id.values() if inv.invoice_id not in used
                      and abs(inv.amount - p.amount) <= tolerance
                      and inv.issued_date <= p.date <= date.fromordinal(inv.issued_date.toordinal() + window_days)]
        if not candidates:
            results.append(MatchResult(p, None, "none", "no open invoice with this amount in the date window"))
            continue
        by_id = [inv for inv in candidates if inv.invoice_id.lower() in desc_lower]
        by_name = [inv for inv in candidates if tokens(inv.client_name) & desc_tokens]
        if len(candidates) == 1:
            chosen, reason = candidates[0], "unique amount match"
        elif len(by_id) == 1:
            chosen, reason = by_id[0], "amount match and invoice id in description"
        elif len(by_name) == 1:
            chosen, reason = by_name[0], "amount match and client name in description"
        else:
            results.append(MatchResult(p, None, "ambiguous", f"{len(candidates)} open invoices share this amount",
                                       [c.invoice_id for c in candidates]))
            continue
        used.add(chosen.invoice_id)
        results.append(MatchResult(p, chosen, "high", reason))
    return results


def apply_matches(results: list[MatchResult]) -> int:
    n = 0
    for r in results:
        if r.confidence == "high" and r.invoice is not None:
            r.invoice.status, r.invoice.paid_date = "paid", r.payment.date
            n += 1
    return n


def match_report_md(results: list[MatchResult]) -> str:
    counts = {k: sum(1 for r in results if r.confidence == k) for k in ("high", "ambiguous", "none")}
    lines = ["# Payment match report", "",
             f"{len(results)} incoming payments: **{counts['high']} matched**, {counts['ambiguous']} ambiguous, {counts['none']} unmatched.",
             "", "| Line | Date | Amount | Description | Result | Invoice | Reason |", "|---:|---|---:|---|---|---|---|"]
    for r in results:
        inv = r.invoice.invoice_id if r.invoice else (", ".join(r.candidates) or "-")
        lines.append(f"| {r.payment.line} | {r.payment.date} | {r.payment.amount:.2f} | {r.payment.description[:40]} | "
                     f"{r.confidence} | {inv} | {r.reason} |")
    return "\n".join(lines) + "\n"
