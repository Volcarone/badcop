"""Shared fixtures for the BadCop test suite (standard-library unittest only)."""
from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from badcop.config import Config, parse_config  # noqa: E402
from badcop.ledger import Invoice  # noqa: E402

TODAY = date(2026, 3, 15)

CONFIG_TOML = {
    "sender": {"name": "Accounts, Test Studio", "email": "accounts@test.example", "reply_to": "me@test.example",
               "owner_email": "owner@test.example", "owner_name": "Sam"},
    "smtp": {"host": "smtp.test.example", "port": 2525, "username": "user", "password_env": "TEST_SMTP_PW", "starttls": True},
    "terms": {"currency": "USD", "net_days": 14, "grace_days": 3, "late_fee_pct": 1.5, "late_fee_flat": 0},
    "behaviour": {"catch_up": False, "templates_dir": "templates"},
    "steps": [
        {"offset_days": -3, "name": "courtesy"},
        {"offset_days": 1, "name": "friendly"},
        {"offset_days": 7, "name": "firm"},
        {"offset_days": 14, "name": "final", "apply_late_fee": True},
        {"offset_days": 30, "name": "escalate", "notify_owner": True},
    ],
}


def make_config(base_dir: Path | None = None, **overrides) -> Config:
    data = {k: dict(v) if isinstance(v, dict) else list(v) for k, v in CONFIG_TOML.items()}
    for section, values in overrides.items():
        if isinstance(values, dict):
            data.setdefault(section, {}).update(values)
        else:
            data[section] = values
    return parse_config(data, base_dir or Path("/nonexistent"))


def make_invoice(invoice_id="INV-1", client="Acme Corp", email="ap@acme.example", amount="1000.00",
                 issued=date(2026, 2, 1), due=date(2026, 2, 15), status="open", **kw) -> Invoice:
    return Invoice(invoice_id=invoice_id, client_name=client, client_email=email, amount=Decimal(amount),
                   currency="USD", issued_date=issued, due_date=due, status=status, **kw)


LEDGER_CSV = """invoice_id,client_name,client_email,amount,currency,issued_date,due_date,status,paid_date,late_fee_pct,grace_days,pay_link,notes
INV-1,Acme Corp,ap@acme.example,1000.00,USD,2026-02-01,2026-02-15,open,,,,https://pay.example/1,
INV-2,Blue Fern,hi@bluefern.example,480.00,,2026-03-01,,open,,,,,
INV-3,Acme Corp,ap@acme.example,300.00,USD,2026-01-05,2026-01-19,paid,2026-01-20,,,,
"""
