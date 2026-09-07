"""Pull open and paid invoices from Stripe Invoicing into the ledger. Standard library only."""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from decimal import Decimal

from .ledger import Invoice

API = "https://api.stripe.com/v1/invoices"
ZERO_DECIMAL = {"BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF"}


class StripeError(RuntimeError):
    pass


def _get(url: str, api_key: str) -> dict:
    auth = base64.b64encode(f"{api_key}:".encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {auth}", "User-Agent": "badcop"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        raise StripeError(f"Stripe API returned HTTP {e.code}: {detail}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise StripeError(f"could not reach Stripe: {e}") from e


def fetch_invoices(api_key: str, statuses: tuple[str, ...] = ("open", "paid"), fetch=_get) -> list[dict]:
    """All invoices with the given statuses, following pagination."""
    out: list[dict] = []
    for status in statuses:
        after = None
        while True:
            params = {"status": status, "limit": "100"}
            if after:
                params["starting_after"] = after
            page = fetch(f"{API}?{urllib.parse.urlencode(params)}", api_key)
            out.extend(page.get("data", []))
            if not page.get("has_more") or not page.get("data"):
                break
            after = page["data"][-1]["id"]
    return out


def _amount(raw: int, currency: str) -> Decimal:
    return Decimal(raw) if currency.upper() in ZERO_DECIMAL else (Decimal(raw) / 100).quantize(Decimal("0.01"))


def _day(ts: int | None) -> date | None:
    return datetime.fromtimestamp(ts, tz=timezone.utc).date() if ts else None


def to_invoice(inv: dict, net_days: int) -> Invoice | None:
    """Map a Stripe invoice object to a ledger row. Skips drafts, voids and zero-amount invoices."""
    currency = (inv.get("currency") or "usd").upper()
    raw_total = inv.get("total") if inv.get("total") is not None else inv.get("amount_due")
    amount = _amount(int(raw_total or 0), currency)
    email = inv.get("customer_email") or ""
    if amount <= 0 or not email or inv.get("status") not in ("open", "paid"):
        return None
    issued = _day(inv.get("created")) or date.today()
    due = _day(inv.get("due_date")) or date.fromordinal(issued.toordinal() + net_days)
    paid_at = None
    if inv.get("status") == "paid":
        paid_at = _day((inv.get("status_transitions") or {}).get("paid_at")) or due
    return Invoice(invoice_id=inv.get("number") or inv["id"], client_name=inv.get("customer_name") or email,
                   client_email=email, amount=amount, currency=currency, issued_date=issued, due_date=due,
                   status=inv.get("status"), paid_date=paid_at, pay_link=inv.get("hosted_invoice_url") or "",
                   notes=f"stripe:{inv['id']}")


def merge(existing: list[Invoice], incoming: list[Invoice]) -> tuple[list[Invoice], int, int]:
    """Add new invoices and update status/paid_date of known ones. Returns (ledger, added, updated)."""
    by_id = {inv.invoice_id: inv for inv in existing}
    added = updated = 0
    for inv in incoming:
        cur = by_id.get(inv.invoice_id)
        if cur is None:
            existing.append(inv)
            by_id[inv.invoice_id] = inv
            added += 1
        elif (cur.status, cur.paid_date, cur.amount) != (inv.status, inv.paid_date, inv.amount):
            cur.status, cur.paid_date, cur.amount, cur.pay_link = inv.status, inv.paid_date, inv.amount, inv.pay_link or cur.pay_link
            updated += 1
    return existing, added, updated


def api_key_from_env(var: str) -> str:
    key = os.environ.get(var, "")
    if not key:
        raise StripeError(f"set {var} to a Stripe restricted key with Invoices: Read permission")
    return key
