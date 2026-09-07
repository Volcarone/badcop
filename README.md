# BadCop

**The polite-but-firm invoice chaser. You stay the good cop.**

Website, email templates and late-fee calculator: **https://volcarone.github.io/badcop/**

BadCop is a zero-dependency command-line tool that chases unpaid invoices for you. Point it at a CSV of your invoices and it sends an escalating ladder of reminders from a separate "accounts" identity, applies the late fee your contract already allows, marks invoices paid from a bank or Stripe export, and hands you a one-page aging report. It never takes money and never invents a fee; it just does the awkward part on schedule.

Built for solo freelancers, consultants and small agencies who lose real money because chasing clients feels rude. One r/smallbusiness poster tallied **$3,200** in late and unpaid invoices in a single year for exactly that reason.

```
$ badcop run --dry-run
DRY RUN INV-1001 -> ap@acme.example [firm, +7d]
  Subject: Overdue: invoice INV-1001 (7 days past due)
DRY RUN INV-1002 -> hello@bluefern.example [courtesy, -3d]
  Subject: Invoice INV-1002 is due on 2026-09-11
2 would be sent
```

## How it works

1. **You keep a ledger.** `invoices.csv`, one row per invoice. Export it from Wave, FreshBooks, Stripe, QuickBooks, or type it in.
2. **BadCop runs once a day** (cron, systemd timer, GitHub Actions, Docker; anything that can run a command).
3. **Each open invoice climbs a ladder** relative to its due date. Default: courtesy (3 days before), friendly (1 day after), firm (7), final with late fee (14), escalate to *you* (30). Each rung is sent exactly once. Nothing is sent twice, ever.
4. **When money lands**, `badcop match bank.csv --apply` closes the matching invoices, and the ladder stops.
5. **`badcop report`** tells you what is outstanding, how old it is, and what it is costing your clients.

## Install

Requires Python 3.11+ and nothing else.

```bash
pip install badcop       # or, from a clone: pip install .
badcop --version
```

Or use the setup script, which creates a virtualenv, installs BadCop, runs the test suite and writes a sample workspace:

```bash
./setup.sh
```

Or Docker (see [Deployment](#deployment)):

```bash
docker build -t badcop .
docker run --rm -v "$PWD/workspace:/data" badcop run --dry-run
```

## Quick start

```bash
mkdir my-invoices && cd my-invoices
badcop init                     # writes badcop.toml, invoices.csv, templates/
$EDITOR badcop.toml             # sender identity, SMTP, your payment terms
$EDITOR invoices.csv            # your real invoices
export BADCOP_SMTP_PASSWORD='...'
badcop run --dry-run --verbose  # read every email that would go out
badcop run                      # send for real
```

## Configuration: `badcop.toml`

```toml
[sender]
name        = "Accounts, Jane Doe Studio"   # the "bad cop"
email       = "accounts@janedoe.studio"
reply_to    = "jane@janedoe.studio"          # replies come back to you, the good cop
owner_email = "jane@janedoe.studio"          # receives the escalation step
owner_name  = "Jane"

[smtp]
host = "smtp.postmarkapp.com"
port = 587
username = "apikey"
password_env = "BADCOP_SMTP_PASSWORD"        # the secret lives in the environment, never in this file
starttls = true

[terms]
currency      = "USD"
net_days      = 14      # due_date defaults to issued_date + net_days
grace_days    = 3       # no late fee until this many days past due
late_fee_pct  = 1.5     # per month, simple interest on the principal; mirror YOUR contract
late_fee_flat = 0       # optional flat fee added once the grace period passes

[behaviour]
catch_up = false        # false: only the latest due step is sent on first run; true: send every missed step
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
apply_late_fee = true   # the fee is applied from this step onward

[[steps]]
offset_days = 30
name = "escalate"
notify_owner = true     # this step goes to owner_email, not the client
```

Any number of steps, any offsets, any names. Each step needs a template of the same name (the five defaults ship with `badcop init`).

**Late fees.** BadCop computes fees only from the numbers you enter. Set `late_fee_pct` and `grace_days` to what your contract or invoice terms actually say; if your terms say nothing, leave it at 0 and the "final" email simply omits the fee.

## The ledger: `invoices.csv`

| Column | Required | Notes |
|--------|:--------:|-------|
| `invoice_id` | yes | Unique. Used in subjects and for payment matching. |
| `client_name` | yes | |
| `client_email` | yes | |
| `amount` | yes | Principal, excluding fees. |
| `currency` | | Defaults to `[terms].currency`. |
| `issued_date` | yes | `YYYY-MM-DD` |
| `due_date` | | Defaults to `issued_date + net_days`. |
| `status` | | `open` (default), `paid`, or `void`. Only `open` invoices are chased. |
| `paid_date` | | Set by `match --apply` or by hand. |
| `late_fee_pct`, `grace_days` | | Per-invoice overrides. |
| `pay_link` | | Inserted into the emails when present. |
| `notes` | | Free text, never sent. |

Validation is strict and line-numbered. A ledger with a bad row sends nothing (exit code 2).

## Commands

| Command | What it does |
|---------|--------------|
| `badcop init [--dir D] [--force]` | Write a sample config, ledger and the five default templates. |
| `badcop run [--dry-run] [-v] [--today YYYY-MM-DD]` | Send every reminder that is due. `--dry-run` prints instead and writes no state. |
| `badcop preview INVOICE_ID [--step NAME]` | Render one email to stdout so you can tune the tone. |
| `badcop match payments.csv [--apply]` | Match a bank / Stripe / PayPal export to open invoices. Without `--apply` it only reports. |
| `badcop report [--format md\|csv]` | Aging report: outstanding, buckets, fees, per client. Writes `aging_report.md` and `.csv`. |

| `badcop sync stripe [--dry-run]` | Pull open and paid invoices from Stripe Invoicing into the ledger (adds new ones, updates paid status). Needs `STRIPE_API_KEY` set to a restricted key with *Invoices: Read*. |

Global options: `--config badcop.toml --ledger invoices.csv --state state.json`.

### Google Sheets as the ledger

Keep your invoices in a sheet with the columns above, then *File › Share › Publish to web*, choose the sheet and **CSV**, and pass the link:

```bash
badcop --ledger "https://docs.google.com/spreadsheets/d/e/…/pub?output=csv" run --dry-run
```

`run`, `preview` and `report` work from a URL ledger. `match --apply` and `sync` need a local file, because they write to it.

### Payment matching

```bash
badcop match chase-export.csv            # dry run: prints a match report
badcop match chase-export.csv --apply    # mark high-confidence matches paid; writes invoices.csv.bak first
```

Column names are auto-detected from common exports (`Date`/`Posted`, `Amount`/`Credit`, `Description`/`Memo`/`Payee`); force them with `--date-col`, `--amount-col`, `--desc-col`. Outgoing (negative) lines are ignored.

A line is matched with high confidence only when its amount equals exactly one open invoice within the date window, or when several invoices share the amount and the description carries the invoice id or the client's name. Everything else is listed as *ambiguous* or *unmatched* for you to handle by hand. Each invoice is closed at most once.

### Templates

Plain text files in `templates/<step>.txt`: a `Subject:` line, a blank line, then the body.

```
Subject: Overdue: invoice {invoice_id} ({days_overdue} days past due)

Hi {client_name},

Invoice {invoice_id} for {currency} {amount} is now {days_overdue} days past its due date of {due_date}.
{pay_link}
...
```

Placeholders: `{client_name} {invoice_id} {amount} {currency} {issued_date} {due_date} {days_overdue} {late_fee} {total_due} {pay_link} {sender_name} {owner_name} {steps_sent}`. An unknown placeholder is an error, not a blank.

### State and idempotency

`state.json` records every step sent per invoice, with timestamp and `Message-ID`. Running `badcop run` ten times a day sends each step once. Delete an invoice's entry to resend; delete the file to start over.

### Exit codes

| Code | Meaning |
|-----:|---------|
| 0 | OK, including "nothing due" |
| 1 | Config or usage error |
| 2 | Ledger, payments file or template validation error (nothing sent) |
| 3 | One or more sends failed (the rest were sent and recorded) |

## Deployment

BadCop is a one-shot command; schedule it.

**cron** (daily at 08:00):

```
0 8 * * * cd /home/jane/invoices && BADCOP_SMTP_PASSWORD=... /usr/local/bin/badcop run >> badcop.log 2>&1
```

**systemd timer**: a `badcop.service` with `ExecStart=/usr/local/bin/badcop run`, `WorkingDirectory=/home/jane/invoices`, `EnvironmentFile=/home/jane/invoices/.env`, and a `badcop.timer` with `OnCalendar=daily`.

**Docker**: the image runs `badcop run --dry-run` by default; mount your workspace at `/data` and pass the real command.

```bash
docker build -t badcop .
docker run --rm -v "$PWD/workspace:/data" -e BADCOP_SMTP_PASSWORD badcop run
docker run --rm -v "$PWD/workspace:/data" badcop report
```

Files written into the mount (`state.json`, reports, `invoices.csv.bak`) are owned by root unless you add `--user "$(id -u):$(id -g)"`.

**GitHub Actions, the easy way:** use the [badcop-template](https://github.com/Volcarone/badcop-template) repository. Click *Use this template*, make it private, add your invoices and one secret, and it runs the ladder every morning on GitHub's free minutes. Dry-run by default until you flip a variable.

**GitHub Actions, by hand** (ledger in a private repo, secret in repository settings):

```yaml
on:
  schedule: [{cron: "0 8 * * *"}]
jobs:
  chase:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - run: pip install badcop
      - run: badcop run
        env: {BADCOP_SMTP_PASSWORD: "${{ secrets.SMTP_PASSWORD }}"}
      - run: git config user.name badcop && git config user.email badcop@users.noreply.github.com && git add state.json && git commit -m "badcop state" || true && git push
```

**Email provider.** Use a transactional SMTP service (Postmark, Amazon SES, Mailgun, Resend) with a real `accounts@` mailbox on your domain so replies and bounces reach you. Reminders are transactional mail about an existing business relationship, not marketing.

## Development

```bash
python -m unittest discover -s tests        # 99 tests, standard library only
python -m badcop --help                     # run from the source tree with PYTHONPATH=src
```

Layout: `src/badcop/` (config, ledger, schedule, templates, state, mailer, matcher, report, cli), `tests/`, `Dockerfile`, `setup.sh`.

## FAQ

**Will this make my clients angry?** The default copy is courteous through "firm", states facts in "final", and the last rung goes to *you*, not to your client's boss. Preview every step with `badcop preview` and rewrite anything you would not say yourself.

**Can I charge late fees?** Only if your contract or invoice terms say so. BadCop applies whatever percentage and grace period you enter and nothing else. Set it to 0 if you have no such terms.

**Does it create or send invoices?** No. It chases the ones you already sent. Keep using whatever you invoice with.

**Does it need my bank login?** No. `match` reads a CSV you export yourself.

## License

MIT.
