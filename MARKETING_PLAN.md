# MARKETING_PLAN — BadCop

Distribution plan for BadCop, the open-source invoice chaser specified in `PRODUCT_SPEC.md`. Three parts: (1) the exact Reddit threads where this problem was asked, with reply templates that help the original poster first and mention the tool second; (2) keyword targets for programmatic SEO and GitHub discoverability; (3) the payment gateway integration for the paid tiers.

All thread data comes from the Stage 1 scrape (`pain_points.json`, Reddit public feeds, one-year window, r/smallbusiness, r/freelance, r/ecommerce, r/sysadmin).

---

## 1. Reddit: where the problem was asked, and how to answer

### Rules of engagement (non-negotiable)

- **Answer first, tool last.** Every reply must be useful with the last line deleted. The tool gets one sentence, with a disclosure ("I built this") and a link to the GitHub repo, never to a pricing page.
- **One reply per thread, no DMs, no reposting the same text.** Reddit's spam filter and both subreddits' moderators catch copy-paste.
- **Respect subreddit rules.** r/smallbusiness prohibits self-promotion outside its weekly promotion thread; r/freelance prohibits advertising. Replies below are written so that removing the final sentence leaves a complete, on-topic answer. If a moderator objects, delete the link, not the answer.
- **Thread age.** Threads under six months old get a reply. Older threads (the January post-mortem, the December reconciliation thread) still rank in Google and Reddit search for the exact query, so a reply there is a search asset, not a conversation; write it as a standalone answer.
- **Account.** Use a real personal account with history, not a brand account. The "I lost money to this too" framing is only honest if it is true; adapt the personal details or cut them.
- **Track.** Append `?ref=reddit-<threadid>` to the GitHub link so replies can be attributed in the repo's traffic view.

### Priority threads

| # | Thread | Sub | Posted | Signal | Fit |
|---|--------|-----|--------|--------|-----|
| A | [I just finished my 2025 "Post-Mortem." I realized I lost over $3k because I'm too socially awkward to chase invoices.](https://www.reddit.com/r/smallbusiness/comments/1q1w9eq/i_just_finished_my_2025_postmortem_i_realized_i/) | r/smallbusiness | 2026-01-02 | 51 comments, exact match on "how do you automate" | **Perfect.** OP asks for a "Bad Cop" and considers writing the exact script. |
| B | [How do you actually handle clients who pay invoices late?](https://www.reddit.com/r/smallbusiness/comments/1s22yzq/how_do_you_actually_handle_clients_who_pay/) | r/smallbusiness | 2026-03-24 | asks about automated reminders, late fees, tools | **Perfect.** Four explicit questions the product answers. |
| C | [Invoice Tracking](https://www.reddit.com/r/smallbusiness/comments/1r38k2w/invoice_tracking/) | r/smallbusiness | 2026-02-12 | "do you send and follow up manually per each client or use any product?" | Strong. |
| D | [How did you reduce admin time as a solo business owner? I'm drowning in repetitive tasks.](https://www.reddit.com/r/smallbusiness/comments/1r307db/how_did_you_reduce_admin_time_as_a_solo_business/) | r/smallbusiness | 2026-02-12 | "Invoicing and follow-ups: 3 hours weekly" | Strong; answer only the invoicing item. |
| E | [How do you guys handle the "Invoice vs. Bank Statement" matching game without going crazy?](https://www.reddit.com/r/smallbusiness/comments/1pn8ppm/how_do_you_guys_handle_the_invoice_vs_bank/) | r/smallbusiness | 2025-12-15 | 3 hours/month reconciling | Good for the `match` command; be clear it works on CSV exports, not PDFs. |
| F | [Filed a small claims lawsuit for the first time, actually got paid.](https://www.reddit.com/r/smallbusiness/comments/1ueyck9/filed_a_small_claims_lawsuit_for_the_first_time/) | r/smallbusiness | 2026-06-25 | 1%/month contract late fee covered the filing fees | Good; the escalation step ends exactly here. |
| G | [How do you keep your freelance finances in order? Here's what's been working for me so far.](https://www.reddit.com/r/freelance/comments/1osnpex/how_do_you_keep_your_freelance_finances_in_order/) | r/freelance | 2025-11-09 | habit list; late payments named as a pain | Moderate; contribute a sixth habit. |
| H | [Solo backflow tech – struggling with annual client retention & scheduling](https://www.reddit.com/r/smallbusiness/comments/1vksmq9/solo_backflow_tech_struggling_with_annual_client/) | r/smallbusiness | 2026-08-10 | exact match, 7 comments, annual reminders | Adjacent (reminders, not invoices). Reply only with generic advice; do not pitch. |
| I | [Best website to send invoices for payment to my customers, using a batch file](https://www.reddit.com/r/smallbusiness/comments/1t5hlo3/best_website_to_send_invoices_for_payment_to_my/) | r/smallbusiness | 2026-05-06 | 30–40 invoices/day, wants batch upload | **Not a fit.** BadCop does not send invoices. Goodwill reply pointing at Stripe Invoicing's CSV import; no pitch. |

### Reply templates

Each template is written for its thread. `[brackets]` mark details to personalise or cut.

**A. The $3k post-mortem (r/smallbusiness)**

> The "Good Cop to a fault" thing is more common than you'd think, and the fix you're already circling is the right one: take yourself out of the loop.
>
> Three things that worked for me [or: that I've seen work]:
>
> 1. **The reminders come from a different sender.** `accounts@yourdomain` with your name nowhere in it, Reply-To set to you. Clients treat it as "the system", not as you being pushy. You get to stay the nice one when they reply.
> 2. **Fixed ladder, fixed dates, no judgment calls.** Something like: 3 days before due (heads-up), day 1 after (friendly), day 7 (firm), day 14 (final notice, late fee applied per contract), day 30 (it lands in *your* inbox, and now it's a phone call or small claims). The point is that on day 7 you are not deciding whether to send the firm email. It already went.
> 3. **The late fee is in the contract, so the email just states it.** "Per our terms, 1.5%/month applies from the 15th day" is not a threat, it's a line item. The people who never enforce it (me, previously) are leaving that money on the table every year.
>
> On the "separate accounting email address" script you mentioned: I ended up writing exactly that and open-sourced it, it's a small Python CLI that reads a CSV of invoices and runs the ladder above over SMTP, with a dry-run mode so you can read every email before it sends. Free, no signup: [github link]. Even if you don't use it, the default email templates might be a useful starting point for the "firm but not a jerk" tone.

**B. "How do you actually handle clients who pay invoices late?" (r/smallbusiness)**

> Taking your four questions in order, from someone who lost real money before sorting this out:
>
> **Automated reminders or personal calls?** Automated for the first 30 days, from an `accounts@` address that isn't your name. Personal call after that. Automated reminders are consistent; you are not, and that inconsistency is what slow payers exploit.
>
> **Late fees, and do people pay them?** Yes, if (a) they're in the contract, (b) every reminder mentions them, and (c) you actually add them to the balance in the final notice. Most clients pay the principal within a day of seeing a balance that went up. Some negotiate the fee away; that's fine, it still moved them.
>
> **Accept it and plan around it?** Partly. Chronic 60-day payers get shorter terms, deposits, or a price that reflects the financing you're providing them.
>
> **Tools?** Your invoicing software's reminders are usually on/off with one template; the ladder above needs escalating tone and a stop when the money lands. I ended up writing a small open-source CLI for it, it runs off a CSV, sends the ladder over SMTP, and marks invoices paid from a bank export so it stops chasing people who paid: [github link]. Happy to answer questions on the setup, and the email templates are readable in the repo if you just want the wording.

**C. "Invoice Tracking" (r/smallbusiness)**

> For agency-style variable invoices the thing that matters isn't the sending (any tool does that), it's the *tracking and follow-up*, which is where everyone falls back to a spreadsheet and memory.
>
> What works: one ledger (CSV or sheet) with invoice id, client, amount, issued date, due date, status. A daily job reads it, sends whatever reminder is due for each open invoice on a fixed schedule (before due, +1, +7, +14 with late fee, +30 to you), records what it sent so nothing goes twice, and flips the status to paid when the bank export shows the money.
>
> I open-sourced my version of that daily job if it helps: [github link]. Zero dependencies, dry-run mode, plain-text templates. The ledger format is documented in the README so you can export from whatever you invoice with.

**D. "How did you reduce admin time as a solo business owner?" (r/smallbusiness)**

> Only tackling item 3 (invoicing and follow-ups, 3 hrs/week), since that's the one with a clean fix.
>
> Split "creating invoices" from "chasing invoices". Creating is 10 minutes in FreshBooks and there's not much to gain. Chasing is where the 3 hours go, and it's entirely automatable because it's a schedule, not a judgment: a reminder before the due date, one the day after, a firm one at a week, a final notice with the contractual late fee at two weeks, then it escalates to you.
>
> FreshBooks' built-in reminders are one flat template; the escalation and the "stop when paid" logic are what make it actually hands-off. I wrote a small open-source CLI that does the ladder from a CSV export, if you want to try it: [github link]. Set it to run daily, and item 3 becomes zero.

**E. "Invoice vs. Bank Statement matching game" (r/smallbusiness)**

> The PDF-and-screenshots folder is the real problem; everything after that is hard because of it. Two changes:
>
> 1. **Keep a ledger of what you sent, as data.** One CSV: invoice id, client, amount, date. Every invoicing tool exports this; if you invoice from Word, it's a 20-second habit per invoice.
> 2. **Match against a bank CSV, not the PDF statement.** Export the month from your bank (every bank does CSV), match on amount + date window, and only look manually at the lines where two invoices share an amount.
>
> I built the matching part into an open-source invoice tool I use, `badcop match bank.csv` prints a matched / ambiguous / unmatched table and marks the matched ones paid: [github link]. Plain CSV in, plain CSV out, so your accountant gets a clean list instead of a folder. It won't read the phone screenshots, nothing free will, but once the ledger exists the screenshots stop mattering.

**F. "Filed a small claims lawsuit for the first time, actually got paid" (r/smallbusiness)**

> The detail people should notice: the 1%/month clause in your contract roughly paid the filing fees. That clause does nothing on its own; it works because you (eventually) invoked it.
>
> The gap for most of us is the 30 days *before* small claims: reminders go out inconsistently, the late fee is never actually stated, and by the time it's a lawsuit there's no paper trail of escalation. A fixed reminder ladder that states the fee from day 14 and logs every email with a timestamp makes the small-claims filing a formality, and usually makes it unnecessary.
>
> [Optional: I open-sourced the tool I use for that ladder, it keeps the send log you'd want as an exhibit: github link.]

**G. "How do you keep your freelance finances in order?" (r/freelance)**

> Good list. I'd add a sixth:
>
> **6. Don't be the one who chases late payments.** Have a fixed schedule of reminders that goes out from `accounts@yourdomain`, escalates in tone, states your late-fee terms, and stops the moment the money lands. Your Friday check-in then becomes "mark what got paid" instead of "write awkward emails". The awkwardness is why most of us send the nudge on day 10 instead of day 1, and that's where the 30–60 day payments come from.
>
> [If asked or if rules allow: it's a CSV-driven script, open source, link.]

**H and I (adjacent / not a fit)**: reply with genuine advice only. For I, point to Stripe Invoicing (CSV import and API) or Wave's bulk invoice import; do not mention BadCop, it does not send invoices and saying so builds the credibility the other replies spend.

### Where to post, beyond replies

- **r/smallbusiness weekly promotion thread**: "I lost $X to late invoices, so I wrote an open-source chaser" with a screenshot of the dry-run output.
- **r/SideProject, r/opensource, r/selfhosted, r/Python (Showcase)**: launch posts; lead with the "separate identity + ladder + stops when paid" idea, not the feature list.
- **Show HN**: "Show HN: BadCop – an open-source CLI that chases your unpaid invoices so you don't have to". HN likes zero-dependency, plain-text-template, CSV-in tools.
- **Indie Hackers / Product Hunt**: after the Cloud tier exists; the free CLI alone will not convert there.

---

## 2. Keywords: programmatic SEO and GitHub discoverability

Volumes are deliberately not invented here. Validate each cluster with Ahrefs or Google Keyword Planner before building pages; the intent tiers below are what matter for prioritisation.

### Tier 1: transactional intent (build pages first)

| Keyword cluster | Page |
|-----------------|------|
| invoice reminder software, automated invoice reminders, payment reminder software for freelancers | Home / landing |
| overdue invoice email template, late payment reminder email, invoice follow up email, final notice invoice email, payment reminder email sequence | `/templates/` hub plus one page per tone (see pSEO below) |
| late fee calculator, invoice late fee calculator, interest on overdue invoices calculator | `/late-fee-calculator` (free tool; a natural lead magnet for the Cloud tier) |
| how to chase unpaid invoices, client hasn't paid invoice, what to do when a client doesn't pay | `/guides/how-to-chase-unpaid-invoices` |
| accounts receivable automation small business, dunning software for freelancers | Landing page variant |

### Tier 2: programmatic pages (one template, many pages)

- **Reminder templates by stage and tone**: `/templates/{friendly|firm|final-notice}-invoice-reminder-email`, `/templates/invoice-{7|14|30|60}-days-overdue-email`, `/templates/late-fee-applied-invoice-email`. Each page: the email, when to send it, what to change, "generate the whole sequence with BadCop".
- **Schedules by payment terms**: `/reminder-schedule/net-{7|14|15|30|45|60}` with a concrete ladder and a downloadable `badcop.toml`.
- **Export guides by invoicing tool**: `/integrations/{wave|freshbooks|quickbooks|stripe|paypal|zoho|xero|invoice-ninja}-invoice-reminders`. Each: how to export the invoice CSV, column mapping to the BadCop ledger, how to export the payments CSV for `match`. These rank for "{tool} automatic reminders" queries where the built-in feature disappoints.
- **Late fee rules by jurisdiction**: `/late-fees/{us-state|uk|eu|canada|australia}`. Informational only, sourced, with a disclaimer; do not give legal advice. (UK has statutory interest on late commercial payments; the EU Late Payment Directive; US varies by state.) High-intent, low-competition, and exactly what the "can I charge a late fee?" reply traffic wants.
- **Alternatives / comparisons**: `/alternatives/{chaser|upflow|invoiced|freshbooks-reminders|quickbooks-reminders}`. Honest tables; BadCop wins on price and control, loses on dashboards.

### Tier 3: informational long tail (blog, one post each)

"how many reminders before charging a late fee", "how to word a late fee on an invoice", "should I call or email a client who hasn't paid", "client paid late should I charge interest", "net 30 vs net 15 for freelancers", "how to write a final notice before collections", "small claims for unpaid invoice what to prepare" (link to the send log feature).

### GitHub / PyPI discoverability

- **Repo name**: `badcop`. **Description**: "Chase unpaid invoices with an escalating reminder ladder from a separate accounts@ identity. CSV in, email out, zero dependencies. You stay the good cop."
- **Topics**: `invoice`, `invoicing`, `invoice-reminder`, `accounts-receivable`, `dunning`, `late-payment`, `payment-reminder`, `freelance`, `small-business`, `cli`, `python`, `smtp`, `self-hosted`, `automation`.
- **README first screen** already carries the keywords ("invoice reminder", "late fee", "aging report", "freelancers", "small agencies") and a real terminal transcript; GitHub search indexes README text.
- **Listings**: awesome-selfhosted (Money, Budgeting & Management), awesome-python (Finance / CLI), awesome-cli-apps, PyPI with the `keywords` field already set in `pyproject.toml`, AlternativeTo (as an alternative to Chaser, Upflow, Invoiced), SaaSHub, and the self-hosted directories (selfh.st, Awesome-Sysadmin's finance section).
- **Release hygiene**: tagged releases with changelogs, a `CHANGELOG.md`, a `CONTRIBUTING.md`, and issue templates. Stars follow "this looks maintained".

---

## 3. Payment gateway integration

### Recommendation: Lemon Squeezy as merchant of record, Stripe Checkout as the fallback

| | Lemon Squeezy | Stripe Checkout |
|---|---|---|
| Sales tax / VAT | Handled: LS is the merchant of record and files worldwide | Your problem: register in each jurisdiction, or add Stripe Tax and still file |
| Fees | Higher per transaction (roughly 5% + 50¢) | Lower (roughly 2.9% + 30¢) plus Stripe Tax |
| License keys | Built in, with validate / activate / deactivate API | Build your own |
| Subscriptions, trials, customer portal | Built in | Built in (Billing + Customer Portal) |
| Effort for a solo founder | Hours | Days, plus ongoing tax admin |

At the Cloud tier's $9/month and $79/year and the $99 lifetime price, the fee difference is a few dollars per customer per year; the tax administration difference is the whole reason to prefer a merchant of record until revenue justifies otherwise. Switch to Stripe only if usage-based billing or multi-seat plans arrive.

### Products and prices

| Product | LS product / variant | Billing |
|---------|----------------------|---------|
| BadCop Cloud Monthly | `badcop-cloud`, variant `monthly` | $9/month, 14-day free trial, card required |
| BadCop Cloud Yearly | `badcop-cloud`, variant `yearly` | $79/year, 14-day free trial |
| BadCop Lifetime | `badcop-lifetime` | $99 one-time, license key generated |

The open-source CLI stays free with no license check; the Cloud tier is a separate hosted service.

### Integration flow (Lemon Squeezy)

1. **Landing page**: Lemon.js overlay checkout on the pricing buttons (`<a href="https://<store>.lemonsqueezy.com/checkout/buy/<variant>?embed=1&checkout[custom][workspace_id]=…" class="lemonsqueezy-button">`). Pass `checkout[email]` when the user is already signed in so the webhook can be matched to a workspace.
2. **Webhook endpoint** (`POST /webhooks/lemonsqueezy`, verify the `X-Signature` HMAC with the signing secret, reject replays by `meta.event_name` + `data.id` idempotency):
   - `order_created` → create the customer record; for the lifetime product, store the license key from `license_key_created`.
   - `subscription_created`, `subscription_updated`, `subscription_resumed` → set the workspace plan and `renews_at`; enable daily runs.
   - `subscription_paused`, `subscription_cancelled`, `subscription_expired`, `subscription_payment_failed` → keep the workspace readable, disable sending after the grace period, email the owner (BadCop chasing BadCop customers is a nice dogfooding moment; use the ladder).
   - `license_key_updated` → sync activation counts.
3. **License key validation** (lifetime tier and any future desktop build): `POST https://api.lemonsqueezy.com/v1/licenses/validate` with `license_key` and `instance_id`; `activate` on first use, `deactivate` from the dashboard. One workspace per key.
4. **Self-service**: link the customer portal (`urls.customer_portal` from the subscription object) in the dashboard for card updates, plan changes and cancellation. Never build those screens.
5. **Reconciliation**: nightly job pulls `GET /v1/subscriptions?filter[store_id]=…` and reconciles against local state, so a missed webhook cannot leave a paying customer disabled.

### Integration flow (Stripe fallback)

Checkout Session with `mode=subscription` (monthly/yearly prices, `subscription_data.trial_period_days=14`) or `mode=payment` (lifetime); webhooks `checkout.session.completed`, `invoice.paid`, `invoice.payment_failed`, `customer.subscription.updated`, `customer.subscription.deleted`; Customer Portal for self-service; Stripe Tax enabled with `automatic_tax[enabled]=true`. Same reconciliation job against `GET /v1/subscriptions`.

### Conversion path from the free CLI

The CLI never nags. The conversion hooks are: the README's Deployment section ("or let BadCop Cloud run it for you"), the `badcop init` footer line pointing at the hosted option, and the late-fee calculator and template pages capturing email for the "reminder ladder" guide. Measure: repo clones → landing visits (UTM from README) → trial starts → paid.

---

## 4. Sequence and metrics

| Week | Action | Metric |
|------|--------|--------|
| 1 | Publish repo, PyPI release, README, five priority replies (A–E) | Stars, clicks per `ref=` tag |
| 2 | Show HN, r/SideProject, r/opensource, awesome-list PRs | Stars, issues opened, PyPI downloads |
| 3–4 | Landing page with late-fee calculator and template pages; Lemon Squeezy store live with Cloud trial | Trial starts, template page impressions in Search Console |
| 5–8 | Integration guides (Wave, FreshBooks, Stripe, QuickBooks), jurisdiction late-fee pages | Organic clicks, trial → paid |

Kill criteria: fewer than 100 stars and zero trial starts after eight weeks means the free CLI is the product and the Cloud tier should be shelved, not marketed harder.
