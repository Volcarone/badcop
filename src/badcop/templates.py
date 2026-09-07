"""Plain-text email templates: first line `Subject: ...`, blank line, body."""
from __future__ import annotations

from pathlib import Path

from .config import Config
from .schedule import DueStep

PLACEHOLDERS = ("client_name", "invoice_id", "amount", "currency", "issued_date", "due_date", "days_overdue",
                "late_fee", "total_due", "pay_link", "sender_name", "owner_name", "steps_sent")


class TemplateError(ValueError):
    pass


DEFAULT_TEMPLATES = {
    "courtesy": """Subject: Invoice {invoice_id} is due on {due_date}

Hi {client_name},

A quick heads-up that invoice {invoice_id} for {currency} {amount} is due on {due_date}.
{pay_link}
If it is already on its way, thank you, and please ignore this note.

Kind regards,
{sender_name}
""",
    "friendly": """Subject: Invoice {invoice_id} was due on {due_date}

Hi {client_name},

Our records show invoice {invoice_id} for {currency} {amount} was due on {due_date} and has not been received yet.
{pay_link}
Could you let us know when we can expect payment? If it has already been sent, please disregard this message.

Kind regards,
{sender_name}
""",
    "firm": """Subject: Overdue: invoice {invoice_id} ({days_overdue} days past due)

Hi {client_name},

Invoice {invoice_id} for {currency} {amount} is now {days_overdue} days past its due date of {due_date}.
{pay_link}
Please arrange payment within the next 5 business days, or reply with a date we can expect it. Per our agreed terms,
late fees apply to overdue balances, and we would rather not have to add them.

Regards,
{sender_name}
""",
    "final": """Subject: Final notice: invoice {invoice_id}, {currency} {total_due} now due

Hi {client_name},

This is a final notice for invoice {invoice_id}, originally {currency} {amount}, due on {due_date} and now
{days_overdue} days overdue. In line with our agreed terms a late fee of {currency} {late_fee} has been applied,
bringing the balance to {currency} {total_due}.
{pay_link}
Please settle the balance within 7 days. If there is a problem with this invoice, reply to this email and we will
sort it out quickly.

Regards,
{sender_name}
""",
    "escalate": """Subject: [BadCop] Invoice {invoice_id} needs a human: {days_overdue} days overdue

{owner_name},

Invoice {invoice_id} for {client_name} ({currency} {amount}, due {due_date}) is {days_overdue} days overdue.
Reminders already sent: {steps_sent}.

The automated ladder is exhausted. Suggested next steps: a phone call, a payment plan offer, or a demand letter /
small-claims filing if the amount justifies it. Late fee accrued so far: {currency} {late_fee}
(balance {currency} {total_due}).

-- BadCop
""",
}


def write_default_templates(directory: Path, overwrite: bool = False) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in DEFAULT_TEMPLATES.items():
        target = directory / f"{name}.txt"
        if target.exists() and not overwrite:
            continue
        target.write_text(text, encoding="utf-8")
        written.append(target)
    return written


def load_template(step_name: str, templates_dir: Path) -> str:
    custom = templates_dir / f"{step_name}.txt"
    if custom.exists():
        return custom.read_text(encoding="utf-8")
    if step_name in DEFAULT_TEMPLATES:
        return DEFAULT_TEMPLATES[step_name]
    raise TemplateError(f"no template for step {step_name!r}: create {custom}")


def split_template(text: str) -> tuple[str, str]:
    first, _, rest = text.partition("\n")
    if not first.lower().startswith("subject:"):
        raise TemplateError("template must start with a 'Subject:' line")
    return first[len("subject:"):].strip(), rest.lstrip("\n")


def build_context(due: DueStep, config: Config, steps_sent: list[str]) -> dict[str, str]:
    inv = due.invoice
    return {
        "client_name": inv.client_name, "invoice_id": inv.invoice_id, "amount": f"{inv.amount:,.2f}",
        "currency": inv.currency, "issued_date": inv.issued_date.isoformat(), "due_date": inv.due_date.isoformat(),
        "days_overdue": str(max(due.days_overdue, 0)), "late_fee": f"{due.late_fee:,.2f}",
        "total_due": f"{due.total_due:,.2f}", "pay_link": f"Pay online: {inv.pay_link}\n" if inv.pay_link else "",
        "sender_name": config.sender_name, "owner_name": config.owner_name or "Hi",
        "steps_sent": ", ".join(steps_sent) if steps_sent else "none",
    }


def render(due: DueStep, config: Config, steps_sent: list[str]) -> tuple[str, str]:
    subject, body = split_template(load_template(due.step.name, config.templates_dir))
    context = build_context(due, config, steps_sent)
    try:
        return subject.format_map(context), body.format_map(context)
    except (KeyError, IndexError, ValueError) as e:
        raise TemplateError(f"template {due.step.name!r}: unknown placeholder {e}; allowed: {PLACEHOLDERS}") from e
