# BadCop Reddit scout, 2026-09-07

1 new threads in the last 7 days across smallbusiness,freelance,Entrepreneur,consulting,webdev,graphic_design,Accounting. Drafts are answer-first; the tool is one sentence at the end with a tracked link. Read, personalise, and post from your own account; delete the last paragraph if a subreddit's rules make you nervous.

## r/Accounting · 2026-09-02 · tools · relevance 8
**[Hot take on unpaid invoices... anyone using Reevol to actually cut DSO?](https://www.reddit.com/r/Accounting/comments/1w5mmae/hot_take_on_unpaid_invoices_anyone_using_reevol/)**

> Ok so we are a small b2b wholesale shop and our unpaid invoices are starting to get kinda out of hand. AR team is literally 2 people and they live in spreadsheets and our old crm, chasing people on email and WhatsApp like all day.  Been looking at stuff like Reevol and similar tools that say they automate collections and help with DSO and buyer risk and all that. Im not trying to turn this into some giant project, just want fewer invoices sitting at 60 and 90 days. Would love any tips from folks…

**Draft reply:**

Your invoicing tool's built-in reminders are usually one flat template on fixed days. The thing that changes behaviour is escalation: a courtesy note before due, a friendly nudge at +1, a firm one at +7 asking for a date, a final notice at +14 that applies the contractual late fee, and at +30 it stops and hands it back to you for a call.

Two details that matter more than the tool: send from an accounts@ address that isn't your name (clients treat it as 'the system', you stay the nice one when they reply), and never send a step twice.

I ended up writing a small open-source CLI that runs exactly this ladder from a CSV of invoices, sends from a separate accounts@ address, and marks invoices paid from a bank export so it stops chasing people who paid: https://github.com/Volcarone/badcop?ref=reddit-1w5mmae. Even if you don't use it, the default email templates are readable in the repo if you just want the wording.

---
