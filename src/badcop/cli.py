"""Command-line interface: init, run, preview, match, report."""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from . import __version__
from .config import Config, ConfigError, load_config
from .ledger import COLUMNS, LedgerError, is_url, load_ledger, save_ledger
from .mailer import DryRunMailer, Message, SendError, SmtpMailer
from .matcher import PaymentsError, apply_matches, load_payments, match_payments, match_report_md
from .report import aging, report_csv, report_md
from .schedule import build_due_step, plan
from .state import State
from .stripe import StripeError, api_key_from_env, fetch_invoices, merge, to_invoice
from .templates import TemplateError, render, write_default_templates

EXIT_OK, EXIT_CONFIG, EXIT_LEDGER, EXIT_SEND = 0, 1, 2, 3

SAMPLE_CONFIG = """[sender]
name        = "Accounts, Example Studio"
email       = "accounts@example.com"
reply_to    = "you@example.com"
owner_email = "you@example.com"
owner_name  = "Sam"

[smtp]
host = "smtp.postmarkapp.com"
port = 587
username = "your-smtp-username"
password_env = "BADCOP_SMTP_PASSWORD"
starttls = true

[terms]
currency      = "USD"
net_days      = 14
grace_days    = 3
late_fee_pct  = 1.5      # per month, simple interest; set to what YOUR contract says
late_fee_flat = 0

[behaviour]
catch_up = false         # true: send every missed step on first run; false: only the latest due step
templates_dir = "templates"

[[steps]]
offset_days = -3
name = "courtesy"

[[steps]]
offset_days = 1
name = "friendly"

[[steps]]
offset_days = 7
name = "firm"

[[steps]]
offset_days = 14
name = "final"
apply_late_fee = true

[[steps]]
offset_days = 30
name = "escalate"
notify_owner = true
"""

SAMPLE_LEDGER = ",".join(COLUMNS) + "\n" + "\n".join([
    "INV-1001,Acme Corp,ap@acme.example,1250.00,USD,{d1},,open,,,,https://pay.example/INV-1001,",
    "INV-1002,Blue Fern Studio,hello@bluefern.example,480.00,USD,{d2},,open,,,,,",
    "INV-1003,Acme Corp,ap@acme.example,300.00,USD,{d3},,paid,{d3p},,,,",
]) + "\n"


def _today(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as e:
        raise ConfigError(f"--today must be YYYY-MM-DD, got {value!r}") from e


def cmd_init(args: argparse.Namespace) -> int:
    base = Path(args.dir)
    base.mkdir(parents=True, exist_ok=True)
    config_path, ledger_path = base / "badcop.toml", base / "invoices.csv"
    if (config_path.exists() or ledger_path.exists()) and not args.force:
        print(f"{base} already has badcop.toml or invoices.csv; use --force to overwrite", file=sys.stderr)
        return EXIT_CONFIG
    today = date.today()
    d = lambda days: date.fromordinal(today.toordinal() - days).isoformat()  # noqa: E731
    config_path.write_text(SAMPLE_CONFIG, encoding="utf-8")
    ledger_path.write_text(SAMPLE_LEDGER.format(d1=d(20), d2=d(10), d3=d(40), d3p=d(25)), encoding="utf-8")
    written = write_default_templates(base / "templates", overwrite=args.force)
    print(f"Wrote {config_path}, {ledger_path} and {len(written)} templates in {base / 'templates'}")
    print("Next: edit badcop.toml (sender, SMTP, terms), replace invoices.csv, then `badcop run --dry-run`.")
    return EXIT_OK


def _load(args: argparse.Namespace) -> tuple[Config, list, State]:
    config = load_config(Path(args.config))
    invoices = load_ledger(args.ledger, config)
    state = State.load(Path(args.state))
    return config, invoices, state


def cmd_run(args: argparse.Namespace) -> int:
    config, invoices, state = _load(args)
    today = _today(args.today)
    due = plan(invoices, config, today, state)
    mailer = DryRunMailer() if args.dry_run else SmtpMailer()
    if not due:
        print(f"{today}: nothing due. {sum(1 for i in invoices if i.is_open)} open invoices.")
        return EXIT_OK
    failures = 0
    for item in due:
        inv, step = item.invoice, item.step
        subject, body = render(item, config, state.sent_steps(inv.invoice_id))
        to = config.owner_email if step.notify_owner else inv.client_email
        label = f"{inv.invoice_id} -> {to} [{step.name}, {item.days_overdue:+d}d]"
        if args.dry_run:
            print(f"DRY RUN {label}\n  Subject: {subject}")
            if args.verbose:
                print("  " + body.replace("\n", "\n  "))
            mailer.send(Message(to=to, subject=subject, body=body), config)
            continue
        try:
            message_id = mailer.send(Message(to=to, subject=subject, body=body), config)
        except SendError as e:
            failures += 1
            state.record_error(inv.invoice_id, str(e))
            print(f"FAILED  {label}: {e}", file=sys.stderr)
        else:
            state.record_sent(inv.invoice_id, step.name, message_id)
            print(f"SENT    {label}")
        state.save(Path(args.state))
    print(f"{len(due) - failures} sent, {failures} failed" if not args.dry_run else f"{len(due)} would be sent")
    return EXIT_SEND if failures else EXIT_OK


def cmd_preview(args: argparse.Namespace) -> int:
    config, invoices, state = _load(args)
    today = _today(args.today)
    inv = next((i for i in invoices if i.invoice_id == args.invoice_id), None)
    if inv is None:
        print(f"invoice {args.invoice_id!r} not in ledger", file=sys.stderr)
        return EXIT_LEDGER
    if args.step:
        step = next((s for s in config.steps if s.name == args.step), None)
        if step is None:
            print(f"unknown step {args.step!r}; steps are {[s.name for s in config.steps]}", file=sys.stderr)
            return EXIT_CONFIG
    else:
        reached = [s for s in config.steps if s.offset_days <= (today - inv.due_date).days]
        step = reached[-1] if reached else config.steps[0]
    item = build_due_step(inv, step, config, today)
    subject, body = render(item, config, state.sent_steps(inv.invoice_id))
    to = config.owner_email if step.notify_owner else inv.client_email
    print(f"To: {to}\nFrom: {config.sender_name} <{config.sender_email}>\nReply-To: {config.reply_to}\nSubject: {subject}\n\n{body}")
    return EXIT_OK


def cmd_match(args: argparse.Namespace) -> int:
    config, invoices, _ = _load(args)
    payments = load_payments(Path(args.payments), args.date_col, args.amount_col, args.desc_col)
    results = match_payments(payments, invoices, Decimal(str(args.tolerance)), args.window_days)
    report = match_report_md(results)
    Path(args.report).write_text(report, encoding="utf-8")
    print(report)
    if args.apply:
        if is_url(args.ledger):
            print("cannot write back to a URL ledger; mark these paid in the sheet yourself", file=sys.stderr)
            return EXIT_LEDGER
        n = apply_matches(results)
        save_ledger(Path(args.ledger), invoices, backup=True)
        print(f"Marked {n} invoices paid in {args.ledger} (backup written to {args.ledger}.bak)")
    else:
        print("Dry run: re-run with --apply to mark the high-confidence matches as paid.")
    return EXIT_OK


def cmd_sync(args: argparse.Namespace) -> int:
    config = load_config(Path(args.config))
    if is_url(args.ledger):
        print("sync writes to the ledger; use a local CSV, not a URL", file=sys.stderr)
        return EXIT_LEDGER
    ledger_path = Path(args.ledger)
    invoices = load_ledger(ledger_path, config) if ledger_path.exists() else []
    raw = fetch_invoices(api_key_from_env(args.api_key_env))
    incoming = [i for i in (to_invoice(r, config.net_days) for r in raw) if i is not None]
    invoices, added, updated = merge(invoices, incoming)
    if args.dry_run:
        print(f"Stripe: {len(raw)} invoices fetched, {len(incoming)} usable; would add {added} and update {updated} in {ledger_path}")
        return EXIT_OK
    save_ledger(ledger_path, invoices, backup=ledger_path.exists())
    print(f"Stripe: {len(incoming)} invoices synced; {added} added, {updated} updated in {ledger_path}")
    return EXIT_OK


def cmd_report(args: argparse.Namespace) -> int:
    config, invoices, _ = _load(args)
    data = aging(invoices, config, _today(args.today))
    md, csv_text = report_md(data, config.currency), report_csv(data)
    base = Path(args.out)
    base.with_suffix(".md").write_text(md, encoding="utf-8")
    base.with_suffix(".csv").write_text(csv_text, encoding="utf-8")
    print(csv_text if args.format == "csv" else md, end="")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="badcop", description="Chase unpaid invoices with an escalating reminder ladder. You stay the good cop.")
    p.add_argument("--version", action="version", version=f"badcop {__version__}")
    p.add_argument("--config", default="badcop.toml", help="path to badcop.toml")
    p.add_argument("--ledger", default="invoices.csv", help="path or https URL of the invoice ledger CSV (e.g. a Google Sheet published as CSV)")
    p.add_argument("--state", default="state.json", help="path to the send-log state file")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init", help="write a sample config, ledger and templates")
    s.add_argument("--dir", default=".")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("run", help="send every reminder that is due today")
    s.add_argument("--dry-run", action="store_true", help="print instead of sending; no state is written")
    s.add_argument("--verbose", "-v", action="store_true", help="with --dry-run, print the full email bodies")
    s.add_argument("--today", help="pretend today is YYYY-MM-DD")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("preview", help="render a step for one invoice without sending")
    s.add_argument("invoice_id")
    s.add_argument("--step", help="step name; default is the latest step reached")
    s.add_argument("--today")
    s.set_defaults(func=cmd_preview)

    s = sub.add_parser("match", help="match a bank/processor CSV to open invoices")
    s.add_argument("payments")
    s.add_argument("--apply", action="store_true", help="mark high-confidence matches paid and rewrite the ledger")
    s.add_argument("--tolerance", type=float, default=0.01)
    s.add_argument("--window-days", type=int, default=120, help="max days after issue date a payment can land")
    s.add_argument("--date-col")
    s.add_argument("--amount-col")
    s.add_argument("--desc-col")
    s.add_argument("--report", default="match_report.md")
    s.set_defaults(func=cmd_match)

    s = sub.add_parser("sync", help="pull open and paid invoices from a payment provider into the ledger")
    s.add_argument("provider", choices=("stripe",))
    s.add_argument("--api-key-env", default="STRIPE_API_KEY", help="environment variable holding the API key")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_sync)

    s = sub.add_parser("report", help="aging report of open invoices")
    s.add_argument("--format", choices=("md", "csv"), default="md")
    s.add_argument("--today")
    s.add_argument("--out", default="aging_report", help="basename; .md and .csv are written")
    s.set_defaults(func=cmd_report)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return EXIT_CONFIG
    except (LedgerError, PaymentsError, TemplateError, StripeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_LEDGER


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
