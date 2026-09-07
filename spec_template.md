# PRODUCT_SPEC — BadCop

> *"I need a Bad Cop."* — the r/smallbusiness poster who lost $3,200 last year because they were too polite to chase invoices.

**One-liner:** BadCop is a zero-dependency command-line tool that chases unpaid invoices for you. It sends an escalating, tone-controlled reminder sequence from a separate "accounts" identity, applies the late fee your contract already allows, marks invoices paid automatically from a bank or processor CSV, and gives you a one-page aging report. You stay the good cop.

**Selected opportunity theme:** `{{THEME}}`

## 1. Why this problem (evidence from Stage 1 and 2)

The theme was the top-ranked *eligible* theme by the three-criterion rubric (average of per-post 1-10 scores across the theme's posts):

| Criterion | Score | Reasoning |
|-----------|------:|-----------|
| Pain severity | **{{PAIN}}** | Direct cash loss (one poster quantified $3.2k in late and unpaid invoices), 3 hrs/week of follow-up admin for a solo consultant, 30% of invoices paid 15+ days late. |
| Autonomy potential | **{{AUTONOMY}}** | The whole loop is software: read a ledger, decide which reminder is due, send it, record it, close the invoice when the money lands. No human service delivery. |
| Build feasibility | **{{FEASIBILITY}}** | CSV in, email out. Scheduling logic, templates, SMTP and a CSV matcher all fit comfortably in a few hundred lines of standard-library Python. |
| Composite (geometric mean) | **{{COMPOSITE}}** | |

Demand signal: **{{POSTS}} posts** tagged with this theme across the four subreddits, **{{EXACT}}** of them exact-phrase matches for the target intent phrases, with **{{COMMENTS}} comments** on the subset whose comment counts were fetched.

### Evidence threads

{{EVIDENCE_TABLE}}

### In their words

{{QUOTES}}

### Why not the other high-scoring problems

| Candidate | Why it lost |
|-----------|-------------|
| Invoice vs. bank-statement matching (r/smallbusiness) | Highest single-post score, but the raw inputs are PDFs and phone screenshots. Robust OCR is not a <500-line MVP. The *matching* half is absorbed into BadCop's `match` command on CSV exports. |
| Batch invoice sending from a delimited file (Authorize.net user) | Real and quantified (30–60 min/day) but tied to one processor's missing feature; Stripe Invoicing already solves it. |
| Order-export reformatting for suppliers (r/ecommerce) | Fully automatable and easy, but no willingness-to-pay signal; Power Query and templates cover it for free. |
| Certificate automation (r/sysadmin, 200 comments) | Huge engagement but a saturated market (ACME clients, expiry monitors). |
| SaaS renewal "drop zone" (r/sysadmin) | Attractive, but needs reliable PDF contract parsing; feasibility too low for the MVP bar. |

## 2. Target user

**Primary:** solo freelancers, consultants and 1–10 person agencies who invoice per project or per milestone, are paid by bank transfer / Stripe / PayPal / Wave / FreshBooks, and have no bookkeeper or AR person. They are conflict-averse by their own admission and lose money because of it.

**Secondary:** small service businesses (trades, studios, tutors) with recurring clients and net-14/net-30 terms.

**Not for:** companies with an AR department, ERP users, anyone needing payment *collection* (BadCop sends reminders; it does not take money).

**Job to be done:** "When an invoice goes overdue, make sure the client is reminded firmly and on schedule, without me having to write the awkward email or remember to send it."

## 3. Core feature set (MVP)

1. **Escalating reminder sequence.** A configurable ladder of steps relative to the due date (default: T-3 courtesy, T+1 friendly, T+7 firm, T+14 final with late fee, T+30 escalate to owner). Each step has a tone and a plain-text template. A step is sent at most once per invoice (idempotent), and by default only the *latest* due step is sent so a first run on an old invoice does not dump four emails on a client.
2. **Separate identity.** Emails go out from a configurable sender ("Accounts, Jane Doe Studio <accounts@…>") with `Reply-To` set to the owner. This is the "Bad Cop" the poster asked for.
3. **Late-fee math.** Monthly percentage and/or flat fee, with grace days, applied from the step that is flagged `apply_late_fee`. Amount, fee and total appear in the email and the report. Fees are only ever computed from values the user entered, mirroring their own contract.
4. **Payment matching (`match`).** Reads a bank / processor CSV export, matches lines to open invoices by amount, date window and client-name / invoice-id tokens, marks confident matches paid, and writes a report of ambiguous and unmatched lines. This directly addresses the "invoice vs bank statement" thread.
5. **Aging report (`report`).** Outstanding total, buckets (current, 1–7, 8–14, 15–30, 31+ days), accrued late fees, per-client totals. Markdown and CSV.
6. **Dry run and preview.** `--dry-run` prints what would be sent; `preview` renders any step for any invoice so the user can tune the tone before anything leaves the building.

**Non-goals for MVP:** creating invoices, taking payments, OCR of PDFs, a web UI, multi-user accounts.

## 4. Input / output data contract

### `invoices.csv` (input, the ledger)

| Column | Type | Required | Notes |
|--------|------|:--------:|-------|
| `invoice_id` | string | yes | Unique. Appears in subject lines and is used for payment matching. |
| `client_name` | string | yes | |
| `client_email` | email | yes | Recipient of reminders. |
| `amount` | decimal > 0 | yes | Invoice principal, excluding late fees. |
| `currency` | ISO-4217 | no | Defaults to `[terms].currency` in config. |
| `issued_date` | `YYYY-MM-DD` | yes | |
| `due_date` | `YYYY-MM-DD` | no | Defaults to `issued_date + [terms].net_days`. |
| `status` | `open` \| `paid` \| `void` | no | Defaults to `open`. Only `open` invoices get reminders. |
| `paid_date` | `YYYY-MM-DD` | no | Set by `match --apply` or by hand. |
| `late_fee_pct` | decimal | no | Per-invoice override of the monthly percentage. |
| `grace_days` | integer | no | Per-invoice override. |
| `pay_link` | URL | no | Inserted into templates when present. |
| `notes` | string | no | Free text; never sent. |

Validation is strict: unknown status, unparsable dates or non-positive amounts abort the run with a line-numbered error (exit code 2). Nothing is sent from a ledger that failed validation.

### `badcop.toml` (input, configuration)

```toml
[sender]
name        = "Accounts, Jane Doe Studio"
email       = "accounts@janedoe.studio"
reply_to    = "jane@janedoe.studio"
owner_email = "jane@janedoe.studio"          # receives escalation notices

[smtp]
host = "smtp.postmarkapp.com"
port = 587
username = "apikey"
password_env = "BADCOP_SMTP_PASSWORD"        # never store the secret in the file
starttls = true

[terms]
currency     = "USD"
net_days     = 14
grace_days   = 3
late_fee_pct = 1.5            # per month, simple interest on the overdue principal
late_fee_flat = 0

[behaviour]
catch_up = false              # true: send every missed step; false: only the latest due step
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
```

### `templates/<step>.txt` (input, editable)

First line `Subject: …`, blank line, then the body. Placeholders: `{client_name} {invoice_id} {amount} {currency} {issued_date} {due_date} {days_overdue} {late_fee} {total_due} {pay_link} {sender_name} {owner_name}`.

### `payments.csv` (input to `match`)

Any CSV with a date column, an amount column and a free-text description column. Column names are auto-detected from common bank/processor exports (`Date/Posted`, `Amount/Credit`, `Description/Memo/Payee`) and can be forced with `--date-col --amount-col --desc-col`.

### Outputs

| Artifact | Produced by | Contents |
|----------|-------------|----------|
| Emails (SMTP) | `run` | One message per due step per open invoice. `Message-ID`, `List-Unsubscribe` not set (transactional mail). |
| `state.json` | `run` | Per invoice: steps sent (`step`, `sent_at`, `message_id`), last error. Guarantees idempotency across runs. |
| `invoices.csv` (rewritten) + `.bak` | `match --apply` | Matched invoices set to `paid` with `paid_date`. |
| `match_report.md` | `match` | Matched / ambiguous / unmatched payment lines with the reasoning. |
| `aging_report.md`, `aging_report.csv` | `report` | Outstanding, buckets, fees, per-client. |
| stdout / exit code | all | `0` ok, `1` config or usage error, `2` ledger validation error, `3` one or more sends failed. |

### CLI surface

```
badcop init                          # write sample badcop.toml, invoices.csv, templates/
badcop run [--dry-run] [--today YYYY-MM-DD]
badcop preview INVOICE_ID [--step NAME] [--today YYYY-MM-DD]
badcop match payments.csv [--apply] [--tolerance 0.01] [--window-days 120]
badcop report [--format md|csv]
```

## 5. Pricing model

| Tier | Price | What you get | Why |
|------|-------|--------------|-----|
| **Open-source CLI** | Free (MIT) | Everything in this spec, self-hosted, unlimited invoices. | GitHub discoverability and Reddit credibility. Freelancers trust code they can read; the "is this reinventing the wheel?" crowd becomes contributors. |
| **BadCop Cloud** | **$9 / month** or $79 / year | Hosted daily runs, upload or sync the ledger (CSV, Stripe, Wave), sending via a verified domain, dashboard of the aging report, email delivery logs. | The value is set-and-forget. $9 is under 0.3% of the $3.2k one poster lost; the ROI story writes itself. Monthly keeps the entry decision trivial for people who invoice irregularly. |
| **Lifetime** | $99 one-time | Cloud tier forever, one workspace. | Freelancers on Reddit consistently prefer one-time purchases; Lemon Squeezy as merchant of record handles VAT/sales tax so a solo founder can sell worldwide. |

Payment flow: Lemon Squeezy Checkout overlay on the landing page, license key emailed, key entered in the Cloud dashboard. Stripe Checkout is the fallback if the product later needs usage-based billing (see MARKETING_PLAN.md).

## 6. Success metrics for the MVP

- Days-to-paid for overdue invoices before vs after enabling BadCop (target: 30% reduction).
- Share of reminders that result in payment within 7 days.
- Late-fee revenue actually collected (the "free money" the poster was leaving on the table).
- Time: zero minutes spent writing reminder emails.

## 7. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Tone damages a client relationship | Templates are plain text, editable, previewable; default copy is firm but courteous and never threatening. Escalation step goes to the *owner*, not to the client's boss. |
| Late fee not enforceable | Fee is computed only from user-entered terms; documentation tells users to mirror their contract. `apply_late_fee` is off on every step until the user's "final" step. |
| Wrong "paid" match | `match` only auto-applies when the amount is unique among open invoices or the description carries the invoice id / client name; everything else is reported as ambiguous. A `.bak` of the ledger is always written. |
| Deliverability | Recommend a transactional provider (Postmark, SES) and a real accounts@ mailbox. Reminders are transactional mail, not marketing. |
