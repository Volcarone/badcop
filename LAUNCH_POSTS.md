# Launch posts (paste-ready drafts)

Post these yourself, from your own accounts. Each is written for its venue's norms. Replace `[…]` details.

---

## Show HN

**Title:** Show HN: BadCop – an open-source CLI that chases your unpaid invoices so you don't have to

**Text:**

I freelance on the side and I'm bad at chasing money. Not at the work, at the awkward email on day 10 that I should have sent on day 1. A post on r/smallbusiness from someone who lost $3,200 in a year for exactly that reason ("I need a bad cop") finally made me build the thing I kept meaning to build.

BadCop is a zero-dependency Python CLI. You keep a CSV of your invoices (or point it at a Google Sheet, or sync from Stripe). Once a day it:

- sends the next rung of an escalating reminder ladder for each open invoice (courtesy at T-3, friendly at +1, firm at +7, final notice with the contractual late fee at +14, and at +30 it stops emailing the client and emails *you*),
- sends from a separate accounts@ identity with Reply-To set to you, so clients treat it as "the system" and you stay the nice one,
- records every send so no step ever goes out twice,
- marks invoices paid from a bank CSV export (amount + date window + name/id matching), so it stops chasing people who paid,
- prints an aging report.

Design choices I'd defend: plain-text templates with a Subject line (no HTML, no tracking pixels), strict ledger validation that refuses to send anything if one row is bad, a dry-run that prints every email, and late fees computed only from numbers you typed in (it never invents a fee). Standard library only; the whole thing is ~1k lines with 111 tests.

There's a template repo that runs it daily on GitHub Actions if you don't want a server.

Repo: https://github.com/Volcarone/badcop
Templates and a late-fee calculator: https://volcarone.github.io/badcop/

Things I'm unsure about and would like opinions on: whether the +30 "hand it to a human" step should also send the client anything; and whether to add a `--catch-up` default for people importing an old ledger (currently it sends only the latest due step so you don't dump four emails on someone).

---

## Product Hunt

**Name:** BadCop
**Tagline:** The polite-but-firm invoice chaser. You stay the good cop.
**Topics:** Productivity, Developer Tools, Finance, Open Source

**Description:**

BadCop chases your unpaid invoices for you. Put your invoices in a CSV (or a Google Sheet, or sync from Stripe) and it sends an escalating ladder of reminders from a separate accounts@ address: a courtesy note before the due date, a friendly nudge the day after, a firm one at a week, a final notice that applies the late fee your contract already allows, and at 30 days it stops emailing the client and tells you it's time for a phone call.

Every reminder is sent exactly once. When money lands, one command matches your bank export to open invoices and the reminders stop. Free, open source, zero dependencies. A template repo runs it daily on GitHub Actions with nothing to host.

**First comment (maker):**

Hi PH. I built this after reading a small-business owner tally $3,200 in late and unpaid invoices in a year, purely because chasing felt rude. The "trick" is boring: reminders come from `accounts@`, not from you, on a fixed schedule you decided once, calmly. On day 7 you are not deciding whether to send the firm email; it already went.

It's a CLI, so it's for people comfortable with a terminal or a GitHub repo. If enough people want a hosted version I'll build one; there's a no-server template in the meantime. Happy to answer anything about the tone of the default emails, which I spent more time on than the code.

---

## Indie Hackers

**Title:** I turned a Reddit complaint into an open-source tool in a day. Here's the process and the numbers so far.

**Body:**

The process, in case it's useful to anyone doing "scrape pain points → build":

1. Pulled ~600 posts from r/smallbusiness, r/freelance, r/ecommerce and r/sysadmin matching phrases like "how do you automate", "I would pay for", "hate doing this manually". (Reddit's JSON API blocks unauthenticated requests now; the RSS feeds still work at about one request per 40 seconds, so it's slow.)
2. Scored each post on pain severity, whether software could solve it 100% without a human, and whether an MVP fits in a few hundred lines. Grouped into themes.
3. Invoice chasing won. The anchor thread was someone who lost $3,200 in a year because they were "too socially awkward to chase invoices" and wanted a "bad cop".
4. Built BadCop: a CLI that sends an escalating reminder ladder from a separate accounts@ address, applies contractual late fees, marks invoices paid from a bank export, and reports aging. Standard library only, 111 tests.
5. Wrote a static site with the reminder templates, a late-fee calculator, and schedule pages for net-7 through net-60, because "overdue invoice email template" is what people actually search for.
6. Replied (helpfully, tool mentioned in one line) in the original threads.

Numbers after [N] days: [stars] stars, [views] site visits, [replies] replies on the threads. Will update.

What I'd do differently: [fill in after a week].

Repo: https://github.com/Volcarone/badcop · Site: https://volcarone.github.io/badcop/

---

## r/smallbusiness weekly promotion thread (only in the designated thread)

I lost money last year by being too polite to chase invoices, so I wrote a free tool that does it for me: an escalating reminder ladder sent from an accounts@ address, late fee applied only if it's in your terms, stops when the bank export shows the payment. Open source, no signup: https://github.com/Volcarone/badcop. The email templates are readable on the site even if you never install anything: https://volcarone.github.io/badcop/templates/
