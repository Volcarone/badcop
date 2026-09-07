#!/usr/bin/env python3
"""Generate the BadCop marketing site into site/dist (static HTML, no dependencies)."""
from __future__ import annotations

import hashlib
import html
import shutil
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
REPO = "https://github.com/Volcarone/badcop"
SITE = "https://volcarone.github.io/badcop"
TODAY = date.today().isoformat()
CSS_HASH = hashlib.sha256((ROOT / "style.css").read_bytes()).hexdigest()[:8]  # cache-busting query for the stylesheet

# ----------------------------------------------------------------------------- content data
TEMPLATES = [
    {"slug": "courtesy-payment-reminder-before-due-date", "step": "courtesy", "offset": -3,
     "title": "Courtesy payment reminder email (3 days before the due date)",
     "h1": "Courtesy reminder: the email to send before an invoice is due",
     "when": "Three business days before the due date. It is not a chase; it is a heads-up that also confirms the invoice arrived and did not land in spam.",
     "why": "Most late payments are not malice, they are an invoice nobody opened. A pre-due reminder catches those at zero social cost, because there is nothing to apologise for yet.",
     "subject": "Invoice {invoice_id} is due on {due_date}",
     "body": "Hi {client_name},\n\nA quick heads-up that invoice {invoice_id} for {currency} {amount} is due on {due_date}.\nPay online: {pay_link}\n\nIf it is already on its way, thank you, and please ignore this note.\n\nKind regards,\n{sender_name}",
     "tips": ["Send it from an accounts@ address, not your personal one, so the later, firmer emails come from the same sender.",
              "Include the payment link even here. Friction is the second biggest reason for late payment after forgetting.",
              "Do not mention late fees yet. There is nothing late."]},
    {"slug": "friendly-invoice-reminder-email", "step": "friendly", "offset": 1,
     "title": "Friendly invoice reminder email (1 day overdue)",
     "h1": "Friendly reminder: the email to send the day after an invoice was due",
     "when": "The day after the due date, at the latest. Waiting a week 'to be polite' is how one-week-late becomes six-weeks-late.",
     "why": "The tone is still warm, but the facts are stated: the amount, the date it was due, and that it has not arrived. The escape hatch ('if it has already been sent') lets the client save face.",
     "subject": "Invoice {invoice_id} was due on {due_date}",
     "body": "Hi {client_name},\n\nOur records show invoice {invoice_id} for {currency} {amount} was due on {due_date} and has not been received yet.\nPay online: {pay_link}\n\nCould you let us know when we can expect payment? If it has already been sent, please disregard this message.\n\nKind regards,\n{sender_name}",
     "tips": ["Ask a question ('when can we expect payment?'). Questions get replies; statements get ignored.",
              "Keep it under 80 words. Long reminders read as anxious.",
              "Send it on a fixed schedule, not when you feel brave. Automate it if you can."]},
    {"slug": "firm-invoice-reminder-email", "step": "firm", "offset": 7,
     "title": "Firm invoice reminder email (7 days overdue)",
     "h1": "Firm reminder: the email to send when an invoice is a week overdue",
     "when": "Seven days after the due date, whether or not the friendly reminder got a reply.",
     "why": "Now you ask for a date and you mention the late-fee terms without applying them. This is the email conflict-avoidant people never send, and it is the one that gets most invoices paid.",
     "subject": "Overdue: invoice {invoice_id} ({days_overdue} days past due)",
     "body": "Hi {client_name},\n\nInvoice {invoice_id} for {currency} {amount} is now {days_overdue} days past its due date of {due_date}.\nPay online: {pay_link}\n\nPlease arrange payment within the next 5 business days, or reply with a date we can expect it. Per our agreed terms, late fees apply to overdue balances, and we would rather not have to add them.\n\nRegards,\n{sender_name}",
     "tips": ["'Regards' instead of 'Kind regards'. Small tone shifts are noticed.",
              "Give a concrete window (5 business days). Open-ended requests get open-ended responses.",
              "Only mention late fees if they are actually in your contract or invoice terms."]},
    {"slug": "final-notice-invoice-email", "step": "final", "offset": 14,
     "title": "Final notice invoice email with late fee (14 days overdue)",
     "h1": "Final notice: the email that applies the late fee",
     "when": "Fourteen days after the due date. Your contract's grace period has passed and the fee is now a line item, not a threat.",
     "why": "The balance goes up. That single fact moves more slow payers than any wording. It also creates the paper trail you need if this ends in a demand letter or small claims.",
     "subject": "Final notice: invoice {invoice_id}, {currency} {total_due} now due",
     "body": "Hi {client_name},\n\nThis is a final notice for invoice {invoice_id}, originally {currency} {amount}, due on {due_date} and now {days_overdue} days overdue. In line with our agreed terms a late fee of {currency} {late_fee} has been applied, bringing the balance to {currency} {total_due}.\nPay online: {pay_link}\n\nPlease settle the balance within 7 days. If there is a problem with this invoice, reply to this email and we will sort it out quickly.\n\nRegards,\n{sender_name}",
     "tips": ["State the original amount, the fee, and the new total separately. Ambiguity invites argument.",
              "Offer the dispute route ('if there is a problem, reply'). It is fair, and it flushes out the real reason for non-payment.",
              "Do not threaten collections or legal action here unless you will actually do it."]},
    {"slug": "invoice-30-days-overdue-email", "step": "escalate", "offset": 30,
     "title": "Invoice 30 days overdue: the escalation email",
     "h1": "30 days overdue: stop emailing the client and escalate",
     "when": "Thirty days past due, after the final notice went unanswered.",
     "why": "At this point another reminder is noise. The right move is a phone call, a payment plan, or a demand letter. This template is the note you (or your tool) send to yourself so that call actually happens.",
     "subject": "Invoice {invoice_id} needs a human: {days_overdue} days overdue",
     "body": "Invoice {invoice_id} for {client_name} ({currency} {amount}, due {due_date}) is {days_overdue} days overdue.\nReminders already sent: courtesy, friendly, firm, final.\n\nSuggested next steps: a phone call, a payment plan offer, or a demand letter / small-claims filing if the amount justifies it. Late fee accrued so far: {currency} {late_fee} (balance {currency} {total_due}).",
     "tips": ["Call before writing. A two-minute call resolves more 30-day invoices than any email.",
              "If you file in small claims, the timestamped reminder sequence is your exhibit A.",
              "Decide the threshold below which you write it off, in advance, so you are not deciding while angry."]},
    {"slug": "late-fee-applied-invoice-email", "step": "final", "offset": 14,
     "title": "Late fee applied email template",
     "h1": "How to tell a client a late fee has been applied",
     "when": "The first email after your grace period ends, usually the 14-day final notice.",
     "why": "Wording matters: 'in line with our agreed terms' frames the fee as something the client already signed up for, which it is. 'We are charging you' frames it as a decision you made today.",
     "subject": "Invoice {invoice_id}: late fee applied per our terms, {currency} {total_due} now due",
     "body": "Hi {client_name},\n\nAs invoice {invoice_id} ({currency} {amount}, due {due_date}) is now {days_overdue} days overdue, the late fee set out in our terms has been applied: {currency} {late_fee}. The balance due is {currency} {total_due}.\nPay online: {pay_link}\n\nIf payment was sent in the last few days, reply with the date and we will reverse the fee.\n\nRegards,\n{sender_name}",
     "tips": ["Offer to reverse the fee if payment crossed in the post. It costs nothing and removes the main objection.",
              "Show the calculation in your terms, not in the email. The email states the number.",
              "Never apply a fee your contract does not allow. It is unenforceable and it damages trust."]},
]

SCHEDULES = [7, 14, 15, 30, 45, 60]

INTEGRATIONS = [
    ("wave", "Wave", "Wave's invoice list can be exported to CSV from the Invoices page, and transactions from Accounting. Free plan users are the exact people whose reminders are one flat template."),
    ("freshbooks", "FreshBooks", "FreshBooks exports invoices as CSV from Reports (Invoice Details) and has built-in reminders that use one template for every stage. Export, map, and let BadCop run the ladder."),
    ("quickbooks", "QuickBooks Online", "QuickBooks Online exports the Invoice List and Open Invoices reports to Excel/CSV. Reminders exist but are all-or-nothing per customer, with no escalation."),
    ("xero", "Xero", "Xero exports the Invoices list (Business > Invoices > Export) and the Receivable Invoice Summary. Its reminders send one template on fixed days without a late-fee step."),
    ("stripe", "Stripe Invoicing", "Stripe's Invoices page exports CSV with id, customer, amount, status and due date. Payouts and balance transactions export separately for matching."),
    ("paypal", "PayPal", "PayPal exports invoices from the Invoicing page and transactions from Activity > Statements. Payment matching works best on the transactions CSV."),
    ("zoho", "Zoho Invoice", "Zoho Invoice exports invoices to CSV or XLS from the Invoices module and supports export of payments received, which feeds BadCop's payment matching."),
    ("invoice-ninja", "Invoice Ninja", "Invoice Ninja (self-hosted or cloud) exports invoices and payments as CSV from Settings > Import/Export. A natural pairing for anyone already self-hosting."),
]

FAQ = [
    ("Will this annoy my clients?", "The default copy is courteous through the firm step and factual in the final notice. Nothing threatens; the last step goes to you, not to the client. You can preview and rewrite every email before anything is sent."),
    ("Can I charge late fees?", "Only if your contract or invoice terms say so. BadCop applies whatever percentage and grace period you enter and nothing else. Set it to zero if you have no such terms."),
    ("Does it send invoices?", "No. It chases the ones you already sent, from whatever tool you use. Keep invoicing the way you do."),
    ("Does it need my bank login?", "No. Payment matching reads a CSV you export from your bank or payment processor."),
    ("What does it cost?", "The command-line tool is free and open source (MIT). A hosted version that runs it for you is planned; the CLI will stay free."),
]


# ----------------------------------------------------------------------------- helpers
def e(s: str) -> str:
    return html.escape(s, quote=False)


def layout(title: str, description: str, body: str, path: str, depth: int) -> str:
    rel = "../" * depth
    canonical = f"{SITE}/{path}".rstrip("/") + ("/" if path else "")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(description)}">
<link rel="canonical" href="{canonical}"><link rel="stylesheet" href="{rel}style.css?v={CSS_HASH}">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(description)}"><meta property="og:type" content="website">
</head><body>
<header class="top"><div class="wrap"><a class="brand" href="{rel}">Bad<span>Cop</span></a><nav><a href="{rel}templates/">Templates</a><a href="{rel}late-fee-calculator/">Late-fee calculator</a><a href="{rel}reminder-schedule/">Schedules</a><a href="{rel}integrations/">Integrations</a><a href="{REPO}">GitHub</a></nav></div></header>
<main class="wrap">
{body}
</main>
<footer><div class="wrap">BadCop is free, open-source software (MIT). <a href="{REPO}">Source on GitHub</a> · <a href="{rel}guides/how-to-chase-unpaid-invoices/">How to chase unpaid invoices</a> · Not legal advice; late-fee rules vary by jurisdiction and by contract.</div></footer>
<script>document.querySelectorAll('button.copy').forEach(b=>b.addEventListener('click',()=>{{const t=b.parentElement.innerText.replace(/^Copy\\n?/,'');navigator.clipboard.writeText(t).then(()=>{{b.textContent='Copied';setTimeout(()=>b.textContent='Copy',1500)}})}}))</script>
</body></html>
"""


def write(path: str, html_text: str) -> None:
    target = DIST / path / "index.html" if path else DIST / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html_text, encoding="utf-8")
    PAGES.append(path)


PAGES: list[str] = []


def email_block(subject: str, body: str) -> str:
    return f'<div class="email"><button class="copy" type="button">Copy</button><span class="subj">Subject: {e(subject)}</span>{e(body)}</div>'


def ladder_html(net_days: int | None = None) -> str:
    steps = [(-3, "Courtesy", "Heads-up that the invoice is due soon, with the pay link."),
             (1, "Friendly", "It was due yesterday; when can we expect it?"),
             (7, "Firm", "A week overdue; asks for a date and mentions the fee terms."),
             (14, "Final notice", "Applies the contractual late fee; balance goes up."),
             (30, "Escalate", "Goes to you, not the client: call, payment plan, or small claims.")]
    items = "".join(f'<li><span class="when">{"T" if d < 0 else "T+"}{d}d</span><span><b>{n}.</b> {t}</span></li>' for d, n, t in steps)
    return f'<ul class="ladder">{items}</ul>'


# ----------------------------------------------------------------------------- pages
def page_home() -> None:
    faq = "".join(f"<h3>{e(q)}</h3><p>{e(a)}</p>" for q, a in FAQ)
    tpl_cards = "".join(f'<a class="card" href="templates/{t["slug"]}/"><b>{e(t["title"])}</b><span>{"Before due" if t["offset"] < 0 else f"{t['offset']} days overdue"}</span></a>' for t in TEMPLATES)
    body = f"""
<section class="hero">
<h1>The polite-but-firm invoice chaser.<br>You stay the good cop.</h1>
<p class="lead">BadCop sends an escalating ladder of payment reminders from a separate accounts@ address, applies the late fee your contract already allows, and stops the moment the money lands. Free, open source, zero dependencies.</p>
<a class="cta" href="{REPO}">Get it on GitHub</a> <a class="cta secondary" href="templates/">Just want the email templates?</a>
</section>
<pre><code>$ badcop run --dry-run
DRY RUN INV-1001 -&gt; ap@acme.example [firm, +7d]
  Subject: Overdue: invoice INV-1001 (7 days past due)
DRY RUN INV-1002 -&gt; hello@bluefern.example [courtesy, -3d]
  Subject: Invoice INV-1002 is due on 2026-09-11
2 would be sent</code></pre>

<h2>Why it exists</h2>
<p>A freelancer on r/smallbusiness added up their year and found <b>$3,200</b> in late and unpaid invoices. Not because clients were crooks, but because sending the firm email felt rude, so it went out on day 10 instead of day 1, and the late fee in the contract was never enforced. They asked for a "bad cop". This is it.</p>

<h2>The ladder</h2>
{ladder_html()}
<p>Every step is sent exactly once per invoice. If the client pays after the friendly reminder, nothing else goes out. If they don't, the tone escalates on a fixed schedule so you never have to decide whether today is the day.</p>

<h2>How it works</h2>
<ol>
<li><b>Keep a CSV of your invoices.</b> Export it from <a href="integrations/">Wave, FreshBooks, QuickBooks, Stripe or whatever you use</a>, or type it in.</li>
<li><b>Run <code>badcop run</code> once a day</b> with cron, a systemd timer or Docker. Or skip the server entirely: the <a href="https://github.com/Volcarone/badcop-template">template repository</a> runs it every morning on GitHub Actions for free.</li>
<li><b>Export a bank CSV when money comes in.</b> <code>badcop match bank.csv --apply</code> closes the matching invoices.</li>
<li><b><code>badcop report</code></b> tells you what is outstanding, how old it is, and what it is costing your clients.</li>
</ol>

<h2>Install</h2>
<pre><code>pip install git+{REPO}.git
badcop init          # sample config, ledger and templates
badcop run --dry-run # read every email before anything is sent</code></pre>
<p>Python 3.11 or newer. Nothing else. <a href="{REPO}#readme">Full documentation on GitHub.</a> Don't want to run anything? <a href="https://github.com/Volcarone/badcop-template">Use the template</a>: a private repo that runs the ladder daily on GitHub Actions, with your invoices in a CSV or a Google Sheet.</p>

<h2>Free resources</h2>
<div class="grid">{tpl_cards}
<a class="card" href="late-fee-calculator/"><b>Late-fee calculator</b><span>What an overdue invoice is costing, by day</span></a>
<a class="card" href="reminder-schedule/"><b>Reminder schedules</b><span>Ladders for net 7 to net 60 terms</span></a>
<a class="card" href="guides/how-to-chase-unpaid-invoices/"><b>How to chase unpaid invoices</b><span>The full playbook, no tool required</span></a>
</div>

<h2>Questions</h2>
{faq}
"""
    write("", layout("BadCop: the polite-but-firm invoice chaser, free and open source",
                     "Automated, escalating payment reminders for freelancers and small agencies. Sends from a separate accounts@ address, applies contractual late fees, stops when paid. Free CLI.", body, "", 0))


def page_templates_index() -> None:
    cards = "".join(f'<a class="card" href="{t["slug"]}/"><b>{e(t["title"])}</b><span>{e(t["when"][:90])}…</span></a>' for t in TEMPLATES)
    body = f"""<p class="crumbs"><a href="../">BadCop</a> › Templates</p>
<h1>Invoice reminder email templates</h1>
<p class="lead">Copy-ready payment reminder emails for every stage, from a courtesy note before the due date to the final notice that applies a late fee. These are the exact defaults BadCop ships with; use them by hand or let it send them on schedule.</p>
<div class="grid">{cards}</div>
<h2>How to use a sequence, not a single email</h2>
<p>One reminder is a request. A sequence is a policy. The difference for slow payers is enormous, because a policy is not personal and cannot be worn down. Send the courtesy note before the due date, the friendly one the day after, the firm one a week later, and the final notice with the fee at two weeks. Then stop emailing and pick up the phone. <a href="../reminder-schedule/">Schedules by payment terms</a> cover net 7 through net 60.</p>
"""
    write("templates", layout("Invoice reminder email templates: friendly, firm, final notice, late fee",
                              "Six copy-ready payment reminder email templates by stage: before due, 1 day, 7 days, 14 days with late fee, 30 days escalation.", body, "templates", 1))


def page_template(t: dict) -> None:
    tips = "".join(f"<li>{e(x)}</li>" for x in t["tips"])
    others = "".join(f'<li><a href="../{o["slug"]}/">{e(o["title"])}</a></li>' for o in TEMPLATES if o is not t)
    body = f"""<p class="crumbs"><a href="../../">BadCop</a> › <a href="../">Templates</a> › {e(t["title"])}</p>
<h1>{e(t["h1"])}</h1>
<h2>When to send it</h2><p>{e(t["when"])}</p>
<h2>The email</h2>
{email_block(t["subject"], t["body"])}
<p class="note">Placeholders in braces are filled in per invoice. Replace them by hand, or run <code>badcop preview INV-1 --step {t["step"]}</code> to render this template for a real invoice.</p>
<h2>Why it works</h2><p>{e(t["why"])}</p>
<h2>Tips</h2><ul>{tips}</ul>
<h2>Automate it</h2>
<p>This is the <code>{t["step"]}</code> step in BadCop's default ladder, sent at T{t["offset"]:+d} days from the due date. Put your invoices in a CSV, run one command a day, and every open invoice gets the right email at the right time, once.</p>
<pre><code>pip install git+{REPO}.git
badcop init &amp;&amp; badcop run --dry-run</code></pre>
<h2>Other stages</h2><ul>{others}</ul>
"""
    write(f"templates/{t['slug']}", layout(f"{t['title']} | BadCop", f"{t['when']} Copy-ready template with subject line and tips.", body, f"templates/{t['slug']}", 2))


def page_calculator() -> None:
    body = f"""<p class="crumbs"><a href="../">BadCop</a> › Late-fee calculator</p>
<h1>Invoice late-fee calculator</h1>
<p class="lead">Work out the late fee on an overdue invoice using simple monthly interest, the way most freelance and small-business contracts phrase it ("1.5% per month on overdue balances"). Enter your own terms; this page does not tell you what you are allowed to charge.</p>
<form id="calc" onsubmit="return false">
<label for="amount">Invoice amount</label><input id="amount" type="number" step="0.01" min="0" value="1250">
<label for="pct">Late fee, % per month</label><input id="pct" type="number" step="0.1" min="0" value="1.5">
<label for="days">Days overdue</label><input id="days" type="number" step="1" min="0" value="30">
<label for="grace">Grace days (no fee until this many days past due)</label><input id="grace" type="number" step="1" min="0" value="3">
<label for="flat">Flat fee added after grace (optional)</label><input id="flat" type="number" step="0.01" min="0" value="0">
</form>
<div class="result" id="fee">18.75 <small>late fee</small></div>
<div id="total" style="color:var(--muted)">Balance due: 1,268.75</div>
<h2>What it costs by day</h2>
<table><thead><tr><th>Days overdue</th><th class="num">Late fee</th><th class="num">Balance due</th></tr></thead><tbody id="tbl"></tbody></table>
<p class="note">Formula: amount × (rate ÷ 100) × (days overdue ÷ 30) + flat fee, applied once the grace period has passed. This is what BadCop uses. If your contract says "per month or part thereof", round the months up instead.</p>
<h2>Before you charge a fee</h2>
<ul>
<li><b>It has to be in your terms.</b> A late fee that was never agreed is unenforceable and will cost you the client. Put it in the contract and on the invoice.</li>
<li><b>Know your jurisdiction.</b> Some places cap interest on commercial debt; some (the UK, the EU) set a statutory rate you can claim even without a clause. This page is not legal advice.</li>
<li><b>State it before you apply it.</b> Mention the terms in the <a href="../templates/firm-invoice-reminder-email/">firm reminder</a>, apply it in the <a href="../templates/final-notice-invoice-email/">final notice</a>.</li>
</ul>
<p>BadCop applies exactly this calculation from your final-notice step onward, using the rate and grace period you configure. <a href="{REPO}">Get it on GitHub.</a></p>
<script>
(function(){{const $=id=>document.getElementById(id);const fmt=n=>n.toLocaleString(undefined,{{minimumFractionDigits:2,maximumFractionDigits:2}});
function fee(a,p,d,g,f){{if(d<=g)return 0;return Math.round((a*p/100*d/30+f)*100)/100}}
function upd(){{const a=+$('amount').value||0,p=+$('pct').value||0,d=+$('days').value||0,g=+$('grace').value||0,f=+$('flat').value||0;const x=fee(a,p,d,g,f);$('fee').innerHTML=fmt(x)+' <small>late fee</small>';$('total').textContent='Balance due: '+fmt(a+x);
$('tbl').innerHTML=[7,14,30,45,60,90].map(n=>{{const y=fee(a,p,n,g,f);return '<tr><td>'+n+'</td><td class="num">'+fmt(y)+'</td><td class="num">'+fmt(a+y)+'</td></tr>'}}).join('')}}
document.querySelectorAll('#calc input').forEach(i=>i.addEventListener('input',upd));upd()}})();
</script>
"""
    write("late-fee-calculator", layout("Invoice late-fee calculator (monthly interest on overdue invoices)",
                                        "Calculate the late fee on an overdue invoice: amount, monthly rate, days overdue, grace period. See the cost by day and the wording to use.", body, "late-fee-calculator", 1))


def page_schedules_index() -> None:
    cards = "".join(f'<a class="card" href="net-{n}/"><b>Net {n} reminder schedule</b><span>Ladder for invoices due {n} days after issue</span></a>' for n in SCHEDULES)
    body = f"""<p class="crumbs"><a href="../">BadCop</a> › Reminder schedules</p>
<h1>Payment reminder schedules by invoice terms</h1>
<p class="lead">The reminder ladder is always relative to the due date, so the schedule is the same shape whatever your terms. What changes is when the due date falls and how patient the escalation should be. Pick your terms.</p>
<div class="grid">{cards}</div>
<h2>The default ladder</h2>{ladder_html()}
"""
    write("reminder-schedule", layout("Invoice reminder schedules for net 7, 14, 15, 30, 45 and 60 terms",
                                      "When to send each payment reminder for your invoice terms, with a ready-made BadCop configuration for each.", body, "reminder-schedule", 1))


def page_schedule(n: int) -> None:
    # Longer terms get a slightly more patient ladder; short terms move faster.
    if n <= 14:
        steps = [(-2, "courtesy"), (1, "friendly"), (5, "firm"), (10, "final"), (21, "escalate")]
        note = "Short terms mean the client agreed to pay quickly; the ladder moves quickly too. Ten days late on a net-7 invoice is already more than double the agreed time."
    elif n <= 30:
        steps = [(-3, "courtesy"), (1, "friendly"), (7, "firm"), (14, "final"), (30, "escalate")]
        note = "The default ladder. Two weeks of grace before the fee is standard for net 15 to net 30 and matches most contract wording."
    else:
        steps = [(-5, "courtesy"), (1, "friendly"), (10, "firm"), (21, "final"), (45, "escalate")]
        note = "Long terms usually mean a larger client with an accounts-payable process. Give the courtesy note more lead time (their approval cycle is slow) and the firm step more room, but do not skip the fee."
    rows = "".join(f'<tr><td>Day {n + d} after issue</td><td>T{d:+d}</td><td>{s}</td><td><a href="../../templates/{[t for t in TEMPLATES if t["step"] == s][0]["slug"]}/">template</a></td></tr>' for d, s in steps)
    toml = "\n\n".join(f'[[steps]]\noffset_days = {d}\nname = "{s}"' + ("\napply_late_fee = true" if s == "final" else "") + ("\nnotify_owner = true" if s == "escalate" else "") for d, s in steps)
    body = f"""<p class="crumbs"><a href="../../">BadCop</a> › <a href="../">Reminder schedules</a> › Net {n}</p>
<h1>Payment reminder schedule for net {n} invoices</h1>
<p class="lead">Net {n} means the invoice is due {n} days after it is issued. Here is when each reminder should go out, counted from the issue date and from the due date.</p>
<table><thead><tr><th>When</th><th>Relative to due</th><th>Step</th><th></th></tr></thead><tbody>{rows}</tbody></table>
<p class="note">{e(note)}</p>
<h2>BadCop configuration</h2>
<p>Drop this into <code>badcop.toml</code>. With <code>net_days = {n}</code>, invoices without an explicit due date get one automatically.</p>
<pre><code>[terms]
net_days = {n}
grace_days = 3
late_fee_pct = 1.5   # your contract's rate, or 0

{toml}</code></pre>
<p><a href="{REPO}">Install BadCop</a> and run <code>badcop run --dry-run</code> to see the schedule applied to your real ledger.</p>
"""
    write(f"reminder-schedule/net-{n}", layout(f"Net {n} invoice reminder schedule: when to send each payment reminder",
                                              f"A day-by-day payment reminder schedule for net {n} invoice terms, with copy-ready templates and a BadCop configuration.", body, f"reminder-schedule/net-{n}", 2))


def page_integrations_index() -> None:
    cards = "".join(f'<a class="card" href="{slug}/"><b>{e(name)}</b><span>Export invoices and payments to BadCop</span></a>' for slug, name, _ in INTEGRATIONS)
    body = f"""<p class="crumbs"><a href="../">BadCop</a> › Integrations</p>
<h1>Automatic invoice reminders for your invoicing tool</h1>
<p class="lead">BadCop does not replace your invoicing software. It reads a CSV export of your invoices and runs the reminder ladder your tool's built-in reminders do not. Export guides and column mappings:</p>
<div class="grid">{cards}</div>
<h2>The ledger format</h2>
<p>Whatever you export from, the target is the same CSV. Required columns: <code>invoice_id, client_name, client_email, amount, issued_date</code>. Optional: <code>currency, due_date, status, paid_date, late_fee_pct, grace_days, pay_link, notes</code>. Dates are <code>YYYY-MM-DD</code>.</p>
"""
    write("integrations", layout("Automatic invoice reminders for Wave, FreshBooks, QuickBooks, Xero, Stripe and more",
                                 "How to export invoices and payments from your invoicing tool into BadCop's ledger for escalating, automated payment reminders.", body, "integrations", 1))


def page_integration(slug: str, name: str, blurb: str) -> None:
    body = f"""<p class="crumbs"><a href="../../">BadCop</a> › <a href="../">Integrations</a> › {e(name)}</p>
<h1>Automatic, escalating invoice reminders for {e(name)}</h1>
<p class="lead">{e(blurb)}</p>
<h2>1. Export your invoices</h2>
<p>In {e(name)}, find the invoice list or the invoice report and export it as CSV (menu names move between versions; look for <i>Export</i> or <i>Download</i>). You need, at minimum, the invoice number, the customer name and email, the amount, and the issue date. Include the due date and status if the export offers them.</p>
<h2>2. Map the columns</h2>
<table><thead><tr><th>BadCop column</th><th>From the {e(name)} export</th></tr></thead><tbody>
<tr><td><code>invoice_id</code></td><td>Invoice number / ID</td></tr>
<tr><td><code>client_name</code></td><td>Customer / Client name</td></tr>
<tr><td><code>client_email</code></td><td>Customer email (add a column if the export lacks it)</td></tr>
<tr><td><code>amount</code></td><td>Total or Amount due, excluding any fees</td></tr>
<tr><td><code>issued_date</code></td><td>Invoice date, as YYYY-MM-DD</td></tr>
<tr><td><code>due_date</code></td><td>Due date, or leave blank to use your net terms</td></tr>
<tr><td><code>status</code></td><td><code>open</code> for unpaid / sent / overdue, <code>paid</code> for paid, <code>void</code> for cancelled</td></tr>
</tbody></table>
<p>Rename the headers in a spreadsheet and save as <code>invoices.csv</code>. BadCop validates every row and tells you the line number of anything it cannot read.</p>
<h2>3. Run the ladder</h2>
<pre><code>badcop init
# replace invoices.csv with your export, edit badcop.toml
badcop run --dry-run --verbose   # read every email first
badcop run                       # schedule this daily</code></pre>
<h2>4. Close invoices when the money lands</h2>
<p>Export payments or bank transactions (from {e(name)} or from your bank) and run <code>badcop match payments.csv --apply</code>. Amounts are matched to open invoices; the matched ones are marked paid and their reminders stop. Ambiguous lines are listed for you.</p>
<p class="note">{e(name)} is a trademark of its owner. BadCop is an independent open-source project and is not affiliated with it.</p>
<p><a href="{REPO}">BadCop on GitHub</a> · <a href="../../templates/">The reminder templates</a></p>
"""
    write(f"integrations/{slug}", layout(f"{name} invoice reminders: escalating, automatic, with late fees | BadCop",
                                         f"Export invoices from {name} into BadCop for an escalating reminder ladder with contractual late fees and payment matching.", body, f"integrations/{slug}", 2))


def page_guide() -> None:
    body = f"""<p class="crumbs"><a href="../../">BadCop</a> › Guides › How to chase unpaid invoices</p>
<h1>How to chase unpaid invoices without losing the client</h1>
<p class="lead">The playbook, whether or not you use software. It is built on one idea: chasing is a policy, not a conversation.</p>
<h2>1. Fix the terms before the next invoice goes out</h2>
<p>Put three things on every invoice and in every contract: the due date as a date (not "net 30"), the late-fee rate and grace period, and the payment link. Most late payments happen because one of those was missing.</p>
<h2>2. Separate the sender from yourself</h2>
<p>Create <code>accounts@yourdomain</code>. All reminders come from it, with replies going to you. Clients treat it as the company's process rather than you personally asking for money, and you are free to be friendly when they reply.</p>
<h2>3. Run a fixed ladder</h2>
{ladder_html()}
<p>Send each step on its day whether or not you feel like it. The <a href="../../templates/">templates</a> are ready to paste. The order matters: ask first, state the facts, ask for a date, apply the fee, then stop emailing.</p>
<h2>4. Apply the fee you agreed</h2>
<p>If it is in your terms, apply it at the final-notice step and show the new balance. Offer to reverse it if payment crossed in the post. If it is not in your terms, do not invent one; fix the terms for next time. <a href="../../late-fee-calculator/">Calculator</a>.</p>
<h2>5. At 30 days, talk</h2>
<p>Phone, not email. Most 30-day-overdue invoices are a cash-flow problem on the client's side, and a payment plan you propose beats one they invent. If there is no answer, a demand letter with your timestamped reminder sequence attached, then small claims if the amount justifies the filing fee.</p>
<h2>6. Decide the write-off line in advance</h2>
<p>Pick an amount below which you stop, and a client behaviour after which you require deposits. Deciding these while angry produces bad decisions.</p>
<h2>Automating all of it</h2>
<p>Steps 2 through 5 are exactly what <a href="{REPO}">BadCop</a> does from a CSV of your invoices: it sends the ladder from your accounts@ address, applies your fee, marks invoices paid from a bank export, and escalates to you at day 30. Free and open source.</p>
"""
    write("guides/how-to-chase-unpaid-invoices", layout("How to chase unpaid invoices without losing the client",
                                                      "A six-step playbook for late invoices: terms, a separate sender, a fixed reminder ladder, the late fee, the 30-day call, and the write-off line.", body, "guides/how-to-chase-unpaid-invoices", 2))


def extras() -> None:
    urls = "".join(f"<url><loc>{SITE}/{p}{'/' if p else ''}</loc><lastmod>{TODAY}</lastmod></url>" for p in PAGES)
    (DIST / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>', encoding="utf-8")
    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n", encoding="utf-8")
    (DIST / "404.html").write_text(layout("Not found | BadCop", "Page not found.", "<h1>Not found</h1><p>That page does not exist. <a href='/badcop/'>Back to BadCop.</a></p>", "404", 0), encoding="utf-8")
    (DIST / ".nojekyll").write_text("", encoding="utf-8")


def main() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    shutil.copy(ROOT / "style.css", DIST / "style.css")
    for f in (ROOT / "static").glob("*"):  # verification files and other root-level statics
        shutil.copy(f, DIST / f.name)
    page_home()
    page_templates_index()
    for t in TEMPLATES:
        page_template(t)
    page_calculator()
    page_schedules_index()
    for n in SCHEDULES:
        page_schedule(n)
    page_integrations_index()
    for slug, name, blurb in INTEGRATIONS:
        page_integration(slug, name, blurb)
    page_guide()
    extras()
    print(f"Built {len(PAGES)} pages into {DIST}")


if __name__ == "__main__":
    main()
