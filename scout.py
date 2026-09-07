#!/usr/bin/env python3
"""
Weekly Reddit scout for BadCop.

Finds threads from the last week where someone is asking about late or unpaid invoices,
skips anything already seen, classifies each thread, and drafts an answer-first reply in
the style of MARKETING_PLAN.md. Nothing is posted: the output is a report for a human.

Usage: python3 scout.py [--days 7] [--out scout_report.md] [--seen scout_seen.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scraper  # noqa: E402  (reuses the rate-limited Atom feed client)

REPO = "https://github.com/Volcarone/badcop"
SITE = "https://volcarone.github.io/badcop"
SUBREDDITS = ["smallbusiness", "freelance", "Entrepreneur", "consulting", "webdev", "graphic_design", "Accounting"]
QUERY = 'invoice (late OR unpaid OR overdue OR chasing OR "hasn\'t paid" OR "not paid" OR "won\'t pay" OR reminder)'
RELEVANT = re.compile(r"\b(invoice|invoices|invoicing)\b", re.I)
PAIN = re.compile(r"\b(late|unpaid|overdue|chas\w+|hasn'?t paid|not paid|won'?t pay|ghost\w*|reminder\w*|net ?\d0|late fee|collections?|"
                  r"payment terms|cash ?flow|awkward|follow[- ]?up)\b", re.I)
PROMO = re.compile(r"\b(i built|we built|i made an?|i created an?|launched my|launching my|feedback on my|check out my|my (app|tool|saas|startup))\b", re.I)
ASKING = re.compile(r"\?|\b(how do|how does|anyone|any (tool|tips|advice)|recommend\w*|what do you|looking for|advice)\b", re.I)
OFFTOPIC = re.compile(r"\b(salary|underpaid|coworking|landlord|tenant|collections? agenc\w+|debt collector|hiring|job offer|refund)\b", re.I)


def relevance(title: str, body: str) -> int:
    """0 = skip. Higher = more clearly a late-invoice question we can help with."""
    text = f"{title}\n{body}"
    if PROMO.search(text) or OFFTOPIC.search(text) or not ASKING.search(text):
        return 0
    score = 0
    if RELEVANT.search(title):
        score += 3
    if PAIN.search(title):
        score += 2
    # pain words within ~150 characters of an invoice mention, anywhere in the post
    near = sum(1 for m in RELEVANT.finditer(text) if PAIN.search(text[max(0, m.start() - 150): m.end() + 150]))
    score += min(near, 4)
    return score if (RELEVANT.search(title) or near >= 2) else 0


def classify(text: str) -> str:
    t = text.lower()
    if re.search(r"late fee|interest|penalt|charge (them|extra)", t):
        return "fees"
    if re.search(r"\b(tool|software|app|automat\w+|zapier|quickbooks|freshbooks|wave|xero|system)\b", t):
        return "tools"
    if re.search(r"bank statement|reconcil|match(ing)? payments|bookkeep", t):
        return "reconcile"
    if re.search(r"awkward|rude|uncomfortable|don'?t want to (annoy|upset|nag)|pushy|relationship", t):
        return "awkward"
    return "general"


def money(text: str) -> str | None:
    m = re.search(r"[$€£]\s?\d[\d,]*(?:\.\d+)?k?|\b\d[\d,]*\s?(?:dollars|usd|eur|gbp)\b", text, re.I)
    return m.group(0) if m else None


def draft(post: dict, kind: str) -> str:
    amt = money(post["title"] + " " + post["body"])
    hook = f"On the {amt} you mentioned: " if amt else ""
    link = f"{REPO}?ref=reddit-{post['id']}"
    common_close = (f"\n\nI ended up writing a small open-source CLI that runs exactly this ladder from a CSV of invoices, sends from a "
                    f"separate accounts@ address, and marks invoices paid from a bank export so it stops chasing people who paid: {link}. "
                    f"Even if you don't use it, the default email templates are readable in the repo if you just want the wording.")
    if kind == "fees":
        body = (f"{hook}late fees work when three things are true: they're in the contract or on the invoice *before* the work starts, "
                "every reminder mentions the terms, and the final notice actually adds the fee to the balance. Most people do the first and "
                "skip the other two, then conclude fees don't work.\n\nA schedule that does all three: courtesy note 3 days before due, friendly "
                "nudge the day after, firm reminder at +7 that quotes the terms, final notice at +14 that applies the fee and shows the new "
                "total, then at +30 you stop emailing and call. Offer to reverse the fee if payment crossed in the post; it removes the main "
                "objection and costs nothing." + common_close)
    elif kind == "tools":
        body = ("Your invoicing tool's built-in reminders are usually one flat template on fixed days. The thing that changes behaviour is "
                "escalation: a courtesy note before due, a friendly nudge at +1, a firm one at +7 asking for a date, a final notice at +14 "
                "that applies the contractual late fee, and at +30 it stops and hands it back to you for a call.\n\nTwo details that matter "
                "more than the tool: send from an accounts@ address that isn't your name (clients treat it as 'the system', you stay the nice "
                "one when they reply), and never send a step twice." + common_close)
    elif kind == "reconcile":
        body = ("Keep the ledger as data, not PDFs: one CSV with invoice id, client, amount, dates, status. Then match against a bank CSV "
                "export (every bank does one) on amount + date window, and only look manually at lines where two invoices share an amount. "
                "Once that exists the screenshots-in-a-folder problem goes away, because you never need to read them again."
                + common_close.replace("I ended up writing", "The matching half of this is in a small open-source tool I wrote"))
    elif kind == "awkward":
        body = ("The fix for the awkwardness is to take yourself out of the loop. Reminders come from `accounts@yourdomain`, not from you, "
                "on a fixed schedule you decided once, calmly: 3 days before due, +1, +7, +14 with the late fee your terms allow, +30 to "
                "you for a phone call. On day 7 you are not deciding whether to send the firm email; it already went. You get to be "
                "friendly when they reply, because 'the system' was the one who nagged." + common_close)
    else:
        body = ("What worked for me was treating chasing as a policy instead of a conversation: a fixed ladder of reminders relative to "
                "the due date (courtesy at -3, friendly at +1, firm at +7, final notice with the contractual fee at +14, then a call at "
                "+30), sent from an accounts@ address rather than my own name, with each step sent exactly once. Slow payers are "
                "exploiting inconsistency; the ladder removes it." + common_close)
    return body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--out", default=str(Path(__file__).with_name("scout_report.md")))
    ap.add_argument("--seen", default=str(Path(__file__).with_name("scout_seen.json")))
    ap.add_argument("--subreddits", default=",".join(SUBREDDITS))
    ap.add_argument("--from-raw", action="store_true", help="re-filter the cached scout_raw.json instead of fetching (for tuning)")
    args = ap.parse_args()
    seen_path = Path(args.seen)
    seen = set(json.loads(seen_path.read_text())) if seen_path.exists() else set()
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)

    raw_path = Path(args.out).with_name("scout_raw.json")
    raw_entries: list[dict] = []
    found: list[dict] = []
    maybe: list[dict] = []

    def consider(entry: dict) -> None:
        text = f"{entry['title']}\n{entry['body']}"
        score = relevance(entry["title"], entry["body"])
        if entry["id"] in seen or len(entry["body"]) < 80:
            return
        if score >= 3:
            found.append({**entry, "kind": classify(text), "score": score})
        elif RELEVANT.search(text) and ASKING.search(text) and not PROMO.search(text) and not OFFTOPIC.search(text):
            maybe.append(entry)

    if args.from_raw:
        for entry in json.loads(raw_path.read_text(encoding="utf-8")):
            consider(entry)
        args.subreddits = "cached"
    for sub in ([] if args.from_raw else args.subreddits.split(",")):
        q = urllib.parse.urlencode({"q": QUERY, "restrict_sr": "1", "sort": "new", "t": "week" if args.days <= 7 else "month", "limit": 50})
        print(f"r/{sub} ...", end=" ", flush=True)
        try:
            root = scraper.get_atom(f"{scraper.BASE}/r/{sub}/search.rss?{q}")
        except Exception as e:  # noqa: BLE001
            print(f"failed: {e}")
            continue
        n = 0
        for e in root.findall("a:entry", scraper.ATOM):
            full_id = e.findtext("a:id", default="", namespaces=scraper.ATOM)
            if not full_id.startswith("t3_") or full_id[3:] in seen:
                continue
            title = scraper.html.unescape(e.findtext("a:title", default="", namespaces=scraper.ATOM)).strip()
            body = scraper.html_to_text(e.findtext("a:content", default="", namespaces=scraper.ATOM))
            published = e.findtext("a:published", default="", namespaces=scraper.ATOM)
            try:
                when = datetime.fromisoformat(published.replace("Z", "+00:00"))
            except ValueError:
                when = datetime.now(timezone.utc)
            text = f"{title}\n{body}"
            link = e.find("a:link", scraper.ATOM)
            entry = {"id": full_id[3:], "subreddit": sub, "title": title, "body": body, "published": when.date().isoformat(),
                     "url": link.get("href") if link is not None else ""}
            if when < cutoff:
                continue
            raw_entries.append(entry)
            before = len(found)
            consider(entry)
            n += len(found) - before
        print(f"{n} new relevant")

    if not args.from_raw:
        raw_path.write_text(json.dumps(raw_entries, ensure_ascii=False, indent=1), encoding="utf-8")
    found.sort(key=lambda p: (p["score"], p["published"]), reverse=True)
    lines = [f"# BadCop Reddit scout, {datetime.now().date().isoformat()}", "",
             f"{len(found)} new threads in the last {args.days} days across {args.subreddits}. Drafts are answer-first; the tool is one "
             f"sentence at the end with a tracked link. Read, personalise, and post from your own account; delete the last paragraph if a "
             f"subreddit's rules make you nervous.", ""]
    for p in found:
        lines += [f"## r/{p['subreddit']} · {p['published']} · {p['kind']} · relevance {p['score']}", f"**[{p['title']}]({p['url']})**", "",
                  "> " + p["body"][:500].replace("\n", " ") + ("…" if len(p["body"]) > 500 else ""), "", "**Draft reply:**", "",
                  draft(p, p["kind"]), "", "---", ""]
    if not found:
        lines.append("No clear late-invoice questions this week.")
    if maybe:
        lines += ["", "## Possibly relevant (no draft; read before deciding)", ""]
        lines += [f"- r/{p['subreddit']} · {p['published']} · [{p['title']}]({p['url']})" for p in maybe]
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    seen |= {p["id"] for p in found} | {p["id"] for p in maybe}
    seen_path.write_text(json.dumps(sorted(seen)), encoding="utf-8")
    print(f"\n{len(found)} threads -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
