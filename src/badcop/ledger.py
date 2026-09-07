"""The invoice ledger: a strictly validated CSV."""
from __future__ import annotations

import csv
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .config import Config

STATUSES = ("open", "paid", "void")
COLUMNS = ["invoice_id", "client_name", "client_email", "amount", "currency", "issued_date", "due_date",
           "status", "paid_date", "late_fee_pct", "grace_days", "pay_link", "notes"]
REQUIRED = ("invoice_id", "client_name", "client_email", "amount", "issued_date")


class LedgerError(ValueError):
    """The ledger failed validation. Nothing is sent from an invalid ledger."""


@dataclass
class Invoice:
    invoice_id: str
    client_name: str
    client_email: str
    amount: Decimal
    currency: str
    issued_date: date
    due_date: date
    status: str = "open"
    paid_date: date | None = None
    late_fee_pct: Decimal | None = None
    grace_days: int | None = None
    pay_link: str = ""
    notes: str = ""

    @property
    def is_open(self) -> bool:
        return self.status == "open"

    def to_row(self) -> dict[str, str]:
        return {
            "invoice_id": self.invoice_id, "client_name": self.client_name, "client_email": self.client_email,
            "amount": f"{self.amount:.2f}", "currency": self.currency, "issued_date": self.issued_date.isoformat(),
            "due_date": self.due_date.isoformat(), "status": self.status,
            "paid_date": self.paid_date.isoformat() if self.paid_date else "",
            "late_fee_pct": "" if self.late_fee_pct is None else str(self.late_fee_pct),
            "grace_days": "" if self.grace_days is None else str(self.grace_days),
            "pay_link": self.pay_link, "notes": self.notes,
        }


def parse_date(raw: str, field: str, line: int) -> date:
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d").date()
    except ValueError as e:
        raise LedgerError(f"line {line}: {field} must be YYYY-MM-DD, got {raw!r}") from e


def parse_decimal(raw: str, field: str, line: int) -> Decimal:
    try:
        return Decimal(raw.strip().replace(",", ""))
    except InvalidOperation as e:
        raise LedgerError(f"line {line}: {field} must be a number, got {raw!r}") from e


def _row_to_invoice(row: dict[str, str], line: int, config: Config) -> Invoice:
    row = {k: (v or "").strip() for k, v in row.items() if k is not None}
    for key in REQUIRED:
        if not row.get(key):
            raise LedgerError(f"line {line}: {key} is required")
    if "@" not in row["client_email"]:
        raise LedgerError(f"line {line}: client_email {row['client_email']!r} is not an email address")
    amount = parse_decimal(row["amount"], "amount", line)
    if amount <= 0:
        raise LedgerError(f"line {line}: amount must be positive, got {amount}")
    status = (row.get("status") or "open").lower()
    if status not in STATUSES:
        raise LedgerError(f"line {line}: status must be one of {STATUSES}, got {row.get('status')!r}")
    issued = parse_date(row["issued_date"], "issued_date", line)
    due = parse_date(row["due_date"], "due_date", line) if row.get("due_date") else issued + timedelta(days=config.net_days)
    if due < issued:
        raise LedgerError(f"line {line}: due_date {due} is before issued_date {issued}")
    paid = parse_date(row["paid_date"], "paid_date", line) if row.get("paid_date") else None
    if status == "paid" and paid is None:
        raise LedgerError(f"line {line}: paid invoices need a paid_date")
    fee_pct = parse_decimal(row["late_fee_pct"], "late_fee_pct", line) if row.get("late_fee_pct") else None
    grace = None
    if row.get("grace_days"):
        try:
            grace = int(row["grace_days"])
        except ValueError as e:
            raise LedgerError(f"line {line}: grace_days must be an integer") from e
    return Invoice(invoice_id=row["invoice_id"], client_name=row["client_name"], client_email=row["client_email"],
                   amount=amount, currency=(row.get("currency") or config.currency).upper(), issued_date=issued,
                   due_date=due, status=status, paid_date=paid, late_fee_pct=fee_pct, grace_days=grace,
                   pay_link=row.get("pay_link", ""), notes=row.get("notes", ""))


def is_url(value: str | Path) -> bool:
    return str(value).lower().startswith(("http://", "https://"))


def read_ledger_text(path: str | Path) -> str:
    """Read the ledger from a file or an HTTPS URL (e.g. a Google Sheet published as CSV)."""
    if is_url(path):
        req = urllib.request.Request(str(path), headers={"User-Agent": "badcop"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8-sig")
        except (urllib.error.URLError, TimeoutError) as e:
            raise LedgerError(f"could not fetch ledger from {path}: {e}") from e
    try:
        return Path(path).read_text(encoding="utf-8-sig")
    except FileNotFoundError as e:
        raise LedgerError(f"ledger not found: {path}") from e


def load_ledger(path: str | Path, config: Config) -> list[Invoice]:
    text = read_ledger_text(path)
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        raise LedgerError(f"{path}: empty file")
    missing = [c for c in REQUIRED if c not in reader.fieldnames]
    if missing:
        raise LedgerError(f"{path}: missing required columns {missing}")
    invoices, seen = [], set()
    for line, row in enumerate(reader, start=2):
        if not any((v or "").strip() for v in row.values()):
            continue  # blank line
        inv = _row_to_invoice(row, line, config)
        if inv.invoice_id in seen:
            raise LedgerError(f"line {line}: duplicate invoice_id {inv.invoice_id!r}")
        seen.add(inv.invoice_id)
        invoices.append(inv)
    return invoices


def save_ledger(path: Path, invoices: list[Invoice], backup: bool = True) -> None:
    if backup and path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for inv in invoices:
            writer.writerow(inv.to_row())
