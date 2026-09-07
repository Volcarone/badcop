"""Aging report: what is outstanding, how old it is, and what it is costing the client."""
from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal

from .config import Config
from .ledger import Invoice
from .schedule import days_overdue, late_fee

BUCKETS = (("current", None, 0), ("1-7", 1, 7), ("8-14", 8, 14), ("15-30", 15, 30), ("31+", 31, None))


def bucket_for(days: int) -> str:
    for name, lo, hi in BUCKETS:
        if (lo is None or days >= lo) and (hi is None or days <= hi):
            return name
    return "31+"


def aging(invoices: list[Invoice], config: Config, today: date) -> dict:
    rows, buckets, clients = [], {b[0]: {"count": 0, "amount": Decimal("0")} for b in BUCKETS}, {}
    total, fees = Decimal("0"), Decimal("0")
    for inv in invoices:
        if not inv.is_open:
            continue
        days, fee = days_overdue(inv, today), late_fee(inv, config, today)
        b = bucket_for(days)
        rows.append({"invoice_id": inv.invoice_id, "client_name": inv.client_name, "amount": inv.amount, "currency": inv.currency,
                     "due_date": inv.due_date, "days_overdue": days, "bucket": b, "late_fee": fee, "total_due": inv.amount + fee})
        buckets[b]["count"] += 1
        buckets[b]["amount"] += inv.amount
        c = clients.setdefault(inv.client_name, {"count": 0, "amount": Decimal("0"), "oldest_days": days})
        c["count"] += 1
        c["amount"] += inv.amount
        c["oldest_days"] = max(c["oldest_days"], days)
        total += inv.amount
        fees += fee
    rows.sort(key=lambda r: r["days_overdue"], reverse=True)
    return {"today": today, "total_outstanding": total, "total_late_fees": fees, "buckets": buckets, "clients": clients, "rows": rows}


def report_md(data: dict, currency: str) -> str:
    lines = [f"# Aging report as of {data['today']}", "",
             f"**Outstanding: {currency} {data['total_outstanding']:,.2f}** across {len(data['rows'])} open invoices. "
             f"Late fees accrued: {currency} {data['total_late_fees']:,.2f}.", "",
             "| Bucket | Invoices | Amount |", "|---|---:|---:|"]
    for name, _, _ in BUCKETS:
        b = data["buckets"][name]
        lines.append(f"| {name} | {b['count']} | {b['amount']:,.2f} |")
    lines += ["", "| Client | Invoices | Amount | Oldest (days) |", "|---|---:|---:|---:|"]
    for name, c in sorted(data["clients"].items(), key=lambda kv: kv[1]["amount"], reverse=True):
        lines.append(f"| {name} | {c['count']} | {c['amount']:,.2f} | {c['oldest_days']} |")
    lines += ["", "| Invoice | Client | Due | Days overdue | Amount | Late fee | Total due |", "|---|---|---|---:|---:|---:|---:|"]
    for r in data["rows"]:
        lines.append(f"| {r['invoice_id']} | {r['client_name']} | {r['due_date']} | {r['days_overdue']} | "
                     f"{r['amount']:,.2f} | {r['late_fee']:,.2f} | {r['total_due']:,.2f} |")
    return "\n".join(lines) + "\n"


def report_csv(data: dict) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["invoice_id", "client_name", "currency", "due_date", "days_overdue", "bucket", "amount", "late_fee", "total_due"])
    for r in data["rows"]:
        writer.writerow([r["invoice_id"], r["client_name"], r["currency"], r["due_date"], r["days_overdue"], r["bucket"],
                         f"{r['amount']:.2f}", f"{r['late_fee']:.2f}", f"{r['total_due']:.2f}"])
    return out.getvalue()
