# Changelog

## 0.1.0 (2026-09-07)

First release.

- `run`: escalating reminder ladder relative to due date, one send per step per invoice, latest-step-only by default with `catch_up` option, owner escalation step.
- Late fees: monthly simple interest plus flat fee after a grace period, applied from the first flagged step onward, per-invoice overrides.
- `match`: bank / processor CSV matching by amount, date window, invoice id and client name; `--apply` closes invoices with a ledger backup.
- `report`: aging buckets, per-client totals, accrued fees, Markdown and CSV.
- `preview`, `init`, `--dry-run`, plain-text templates, strict ledger validation, exit codes 0/1/2/3.
