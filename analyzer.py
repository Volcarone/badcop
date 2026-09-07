#!/usr/bin/env python3
"""
Stage 2: score Reddit pain points and select the top opportunity.

Reads pain_points.json (from scraper.py), scores every post 1-10 on three
criteria, groups posts into problem themes, ranks the themes, and writes
scored_opportunities.json plus a markdown ranking table.

Scoring is transparent and deterministic: each criterion starts from a base
and is moved by weighted keyword evidence found in the title + body.  The
lexicons below are the whole model, so the ranking can be audited and tuned.

Usage:
  python3 analyzer.py [--in pain_points.json] [--out scored_opportunities.json] [--top 15]
"""
from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from pathlib import Path

# --------------------------------------------------------------------------- lexicons
# (pattern, weight).  Weights are added to a base score of 5 then clamped to 1-10.

PAIN_SEVERITY = [
    (r"\b(billable|billing|invoice|invoices|invoicing)\b", 1.5),
    (r"\b(hours? (a|per|every) (day|week|month))\b", 2.0),
    (r"\b(\d+\+?\s*(hours|hrs))\b", 1.5),
    (r"\b(every (day|morning|week|month)|daily|weekly|monthly)\b", 1.0),
    (r"\b(costs? (me|us)|losing money|lost revenue|expensive|paying (someone|a va|an assistant))\b", 1.5),
    (r"\b(manual(ly)?|by hand|copy[- ]?past(e|ing)|tedious|repetitive|time[- ]consuming|waste of time|soul[- ]crushing)\b", 1.5),
    (r"\b(i would pay|i'd pay|would pay for|happily pay|shut up and take my money|willing to pay)\b", 2.5),
    (r"\b(hate|dread|nightmare|painful|frustrat\w+|drives me (crazy|insane))\b", 1.0),
    (r"\b(mistakes?|errors?|typos?|missed|forgot|late fees?|penalt\w+)\b", 1.0),
    (r"\b(clients?|customers?)\b", 0.5),
]

AUTONOMY_POTENTIAL = [
    # positive: deterministic data transformation, no human in the loop
    (r"\b(csv|spreadsheet|excel|sheets?|xlsx|export|import|pdf|json|xml)\b", 1.5),
    (r"\b(rename|renaming|convert|converting|merge|merging|dedup\w*|parse|parsing|extract\w*|format\w*|reformat\w*)\b", 1.5),
    (r"\b(sync|syncing|reconcil\w+|match(ing)?|track(ing)?|monitor(ing)?|report(s|ing)?|summar\w+)\b", 1.0),
    (r"\b(schedule[ds]?|reminders?|recurring|automatic(ally)?|cron|script|api|webhook)\b", 1.0),
    (r"\b(invoice|invoices|receipts?|timesheets?|time[- ]tracking|bookkeeping|expenses?)\b", 1.0),
    # negative: needs human judgment, relationships, physical work, or sales
    (r"\b(cold (call|email|outreach)|outreach|lead gen|prospecting|sales calls?|negotiat\w+)\b", -2.0),
    (r"\b(phone|calls?|voicemail|in[- ]person|on[- ]site|physical|warehouse|shipping labels?|packing)\b", -1.0),
    (r"\b(design|creative|branding|logo|content writing|copywriting|video editing)\b", -1.0),
    (r"\b(hire|hiring|employees?|staff|va\b|virtual assistant|freelancer to)\b", -1.0),
    (r"\b(customer (service|support)|support tickets?|chatbot|ai agent)\b", -1.0),
    (r"\b(social media|instagram|tiktok|posting|content calendar)\b", -0.5),
]

BUILD_FEASIBILITY = [
    # positive: file / text / single-API problems
    (r"\b(csv|spreadsheet|excel|xlsx|sheets?|pdf|text file|files?|folder|filename)\b", 1.5),
    (r"\b(email|gmail|imap|inbox)\b", 0.5),
    (r"\b(rename|convert|merge|split|dedup\w*|parse|extract|format|template|generate)\b", 1.5),
    (r"\b(invoice|receipt|timesheet|quote|estimate|proposal|contract)\b", 1.0),
    (r"\b(reminder|follow[- ]?ups?|overdue|due date|deadline)\b", 1.0),
    (r"\b(stripe|paypal|quickbooks|xero|shopify|woocommerce|etsy|amazon|ebay)\b", 0.5),
    # negative: big integration surface, hardware, enterprise IT, ML
    (r"\b(active directory|ad\b|group policy|gpo|sccm|intune|azure ad|entra|ldap|kerberos)\b", -2.0),
    (r"\b(network|switch(es)?|router|firewall|vlan|vpn|dhcp|dns server|printers?|hardware|servers?)\b", -1.5),
    (r"\b(erp|netsuite|sap\b|salesforce|dynamics|epicor)\b", -1.5),
    (r"\b(ai|machine learning|ml\b|computer vision|llm|gpt|chatgpt)\b", -0.5),
    (r"\b(inventory|warehouse|3pl|fulfil+ment|multi[- ]channel|marketplaces?)\b", -1.0),
    (r"\b(mobile app|ios|android|app store)\b", -1.0),
    (r"\b(compliance|hipaa|soc ?2|gdpr|legal|tax(es)?)\b", -1.0),
]

# Problem themes: the first theme whose pattern matches title+body wins; a post
# can be tagged with several themes (all matching), which is what the theme
# ranking uses.
THEMES = {
    "invoicing_and_payment_followup": r"\b(invoice|invoices|invoicing|overdue|late pay\w*|unpaid|net ?30|payment reminder|chas(e|ing) (payments?|clients?)|get paid)\b",
    "bookkeeping_receipts_expenses": r"\b(bookkeeping|receipts?|expenses?|quickbooks|xero|reconcil\w+|bank (statement|feed)|categoriz\w+ transactions?)\b",
    "client_followup_and_reminders": r"\b(follow[- ]?ups?|reminders?|appointment|no[- ]shows?|scheduling|booking)\b",
    "proposals_quotes_contracts": r"\b(proposals?|quotes?|estimates?|contracts?|scope of work|sow\b)\b",
    "lead_gen_and_outreach": r"\b(lead gen\w*|leads?|outreach|cold (email|call)|prospect\w*|crm)\b",
    "ecommerce_listings_and_catalog": r"\b(listings?|product (data|feed|catalog|descriptions?)|skus?|variants?|shopify|etsy|amazon|ebay|woocommerce)\b",
    "orders_shipping_fulfillment": r"\b(orders?|shipping|fulfil+ment|tracking numbers?|labels?|returns?|3pl)\b",
    "inventory_and_stock": r"\b(inventory|stock levels?|reorder|out of stock|restock)\b",
    "reporting_and_dashboards": r"\b(reports?|reporting|dashboards?|kpis?|analytics|metrics)\b",
    "documents_files_and_data_entry": r"\b(data entry|spreadsheets?|csv|excel|pdfs?|files?|forms?|documents?|paperwork)\b",
    "social_media_and_content": r"\b(social media|instagram|tiktok|facebook|linkedin|posts?|content|newsletter|blog)\b",
    "customer_support_and_email": r"\b(customer (service|support)|support (tickets?|emails?)|inbox|helpdesk|faq)\b",
    "it_ops_user_and_device_mgmt": r"\b(onboarding|offboarding|user accounts?|active directory|entra|intune|patch\w*|updates?|devices?|laptops?|endpoints?|servers?)\b",
    "monitoring_alerts_and_logs": r"\b(monitor\w*|alerts?|alerting|logs?|uptime|backups?|certificates?|ssl|expir\w+)\b",
    "hr_payroll_and_timesheets": r"\b(payroll|timesheets?|time[- ]tracking|hours worked|pto|hiring|employees?)\b",
}

BASE = 5.0
# Recurring digests / megathreads mention every keyword and are not pain points.
NOISE_TITLE = r"(news recap|weekly (thread|recap|discussion)|megathread|monthly thread|daily thread|\bama\b|newsletter)"
MIN_POSTS_FRACTION = 0.03   # demand floor: a theme must cover >= 3% of the scored corpus...
MIN_EXACT = 2               # ...and have at least this many exact-phrase posts


# --------------------------------------------------------------------------- scoring
def clamp(x: float) -> int:
    return max(1, min(10, int(round(x))))


def evidence(text: str, lexicon: list[tuple[str, float]]) -> tuple[float, list[str]]:
    """Sum of weights for lexicon entries present in the text, plus the matched terms."""
    total, hits = 0.0, []
    for pattern, weight in lexicon:
        m = re.search(pattern, text, flags=re.I)
        if m:
            total += weight
            hits.append(m.group(0).lower())
    return total, hits


def engagement_bonus(post: dict) -> float:
    """0-2 point bonus from comments / score, log-scaled so viral posts don't dominate."""
    comments = post.get("num_comments") or 0
    score = post.get("score") or 0
    return min(2.0, 0.6 * math.log1p(comments) + 0.3 * math.log1p(max(score, 0)))


def score_post(post: dict) -> dict:
    text = f"{post.get('title', '')}\n{post.get('body', '')}"
    sev, sev_hits = evidence(text, PAIN_SEVERITY)
    aut, aut_hits = evidence(text, AUTONOMY_POTENTIAL)
    fea, fea_hits = evidence(text, BUILD_FEASIBILITY)

    exact = post.get("match_type") == "exact"
    # An exact "I would pay for" / "hate doing this manually" is direct evidence of pain.
    pain = clamp(BASE + sev * 0.8 + engagement_bonus(post) + (1.0 if exact else 0.0))
    autonomy = clamp(BASE + aut)
    feasibility = clamp(BASE + fea)
    # Geometric mean: a problem must be decent on all three axes to rank.
    composite = round((pain * autonomy * feasibility) ** (1 / 3), 2)

    # A theme applies when its terms appear in the title, or at least twice in the body: one
    # passing mention of "invoice" in a long post is not evidence the post is about invoicing.
    title = post.get("title", "")
    themes = [name for name, pat in THEMES.items()
              if re.search(pat, title, flags=re.I) or len(re.findall(pat, text, flags=re.I)) >= 2] or ["uncategorized"]
    return {
        "id": post["id"], "subreddit": post["subreddit"], "title": post["title"], "url": post["url"],
        "num_comments": post.get("num_comments"), "score": post.get("score"),
        "upvote_ratio": post.get("upvote_ratio"), "matched_phrases": post.get("matched_phrases", []),
        "match_type": post.get("match_type", "keyword"), "themes": themes,
        "scores": {"pain_severity": pain, "autonomy_potential": autonomy,
                   "build_feasibility": feasibility, "composite": composite},
        "evidence": {"pain": sev_hits, "autonomy": aut_hits, "feasibility": fea_hits},
        "body_excerpt": (post.get("body") or "")[:400],
    }


def rank_themes(scored: list[dict]) -> list[dict]:
    min_posts = max(5, math.ceil(MIN_POSTS_FRACTION * len(scored)))
    groups: dict[str, list[dict]] = defaultdict(list)
    for s in scored:
        for t in s["themes"]:
            groups[t].append(s)
    out = []
    for theme, posts in groups.items():
        n = len(posts)
        avg = lambda k: round(sum(p["scores"][k] for p in posts) / n, 2)  # noqa: E731
        comments = sum(p["num_comments"] or 0 for p in posts)
        exact_n = sum(1 for p in posts if p["match_type"] == "exact")
        # Demand-weighted composite: average composite * log-scaled frequency, with extra weight
        # for exact-phrase posts and for discussion volume.
        demand = math.log1p(n) + 0.5 * math.log1p(exact_n) + 0.25 * math.log1p(comments)
        out.append({
            "theme": theme, "posts": n, "exact_posts": exact_n, "total_comments": comments,
            "avg_pain_severity": avg("pain_severity"), "avg_autonomy_potential": avg("autonomy_potential"),
            "avg_build_feasibility": avg("build_feasibility"), "avg_composite": avg("composite"),
            "opportunity_score": round(avg("composite") * demand, 2),
            "example_posts": [{"title": p["title"], "url": p["url"], "subreddit": p["subreddit"],
                               "num_comments": p["num_comments"], "match_type": p["match_type"],
                               "composite": p["scores"]["composite"]}
                              for p in sorted(posts, key=lambda p: (p["match_type"] == "exact", p["scores"]["composite"]),
                                              reverse=True)[:6]],
        })
    # Rank by the rubric (average composite of the three 1-10 criteria).  Themes below the demand
    # floor are kept in the table but cannot win: a single high-scoring post is not a market.
    for t in out:
        t["eligible"] = (t["theme"] != "uncategorized" and t["posts"] >= min_posts and t["exact_posts"] >= MIN_EXACT)
        t["min_posts"] = min_posts
    return sorted(out, key=lambda t: (t["eligible"], t["avg_composite"], t["opportunity_score"]), reverse=True)


def select_opportunity(themes: list[dict], scored: list[dict]) -> dict:
    """The #1 theme plus the posts that best evidence it (exact matches first, then composite)."""
    top = next(t for t in themes if t["eligible"])
    posts = [p for p in scored if top["theme"] in p["themes"]]
    posts.sort(key=lambda p: (p["match_type"] == "exact", p["scores"]["composite"], p["num_comments"] or 0), reverse=True)
    return {"theme": top["theme"], "scores": {k: top[k] for k in ("avg_pain_severity", "avg_autonomy_potential",
                                                                   "avg_build_feasibility", "avg_composite")},
            "posts": top["posts"], "exact_posts": top["exact_posts"], "total_comments": top["total_comments"],
            "evidence_posts": posts[:12]}


def render_spec(selection: dict, template_path: Path) -> str:
    """Fill the product spec template with the data-driven evidence for the selected theme."""
    tpl = template_path.read_text(encoding="utf-8")
    ev = selection["evidence_posts"]
    rows = ["| Sub | Thread | Match | Comments | Pain | Auto | Feas |", "|-----|--------|-------|---------:|-----:|-----:|-----:|"]
    for p in ev:
        s_ = p["scores"]
        rows.append(f"| r/{p['subreddit']} | [{p['title'][:80]}]({p['url']}) | {p['match_type']} | {p['num_comments'] or 0} | "
                    f"{s_['pain_severity']} | {s_['autonomy_potential']} | {s_['build_feasibility']} |")
    quotes = []
    for p in ev[:6]:
        excerpt = re.sub(r"\s+", " ", p["body_excerpt"]).strip()
        if excerpt:
            quotes.append(f"> **r/{p['subreddit']} — {p['title'][:70]}**\n> {excerpt[:330]}…")
    sc = selection["scores"]
    return (tpl.replace("{{THEME}}", selection["theme"])
               .replace("{{PAIN}}", str(sc["avg_pain_severity"])).replace("{{AUTONOMY}}", str(sc["avg_autonomy_potential"]))
               .replace("{{FEASIBILITY}}", str(sc["avg_build_feasibility"])).replace("{{COMPOSITE}}", str(sc["avg_composite"]))
               .replace("{{POSTS}}", str(selection["posts"])).replace("{{EXACT}}", str(selection["exact_posts"]))
               .replace("{{COMMENTS}}", str(selection["total_comments"]))
               .replace("{{EVIDENCE_TABLE}}", "\n".join(rows)).replace("{{QUOTES}}", "\n\n".join(quotes)))


def markdown_report(scored: list[dict], themes: list[dict], top: int) -> str:
    lines = ["# Opportunity ranking", "",
             f"{len(scored)} posts scored. Composite = geometric mean of pain, autonomy, feasibility (1-10).",
             "", "## Themes", "",
             f"Themes ranked by average composite; a theme needs >= {themes[0]['min_posts']} posts "
             f"({int(MIN_POSTS_FRACTION * 100)}% of the corpus) and >= {MIN_EXACT} exact-phrase posts to be eligible.",
             "", "| # | Theme | Eligible | Posts | Exact | Comments | Pain | Autonomy | Feasibility | **Composite** | Demand-weighted |",
             "|---|-------|:--------:|------:|------:|---------:|-----:|---------:|------------:|--------------:|----------------:|"]
    for i, t in enumerate(themes, 1):
        lines.append(f"| {i} | {t['theme']} | {'yes' if t['eligible'] else 'no'} | {t['posts']} | {t['exact_posts']} | {t['total_comments']} | "
                     f"{t['avg_pain_severity']} | {t['avg_autonomy_potential']} | {t['avg_build_feasibility']} | "
                     f"**{t['avg_composite']}** | {t['opportunity_score']} |")
    lines += ["", f"## Top {top} posts", "",
              "| # | Sub | Title | Match | Comments | Pain | Auto | Feas | Composite |",
              "|---|-----|-------|-------|---------:|-----:|-----:|-----:|----------:|"]
    for i, p in enumerate(scored[:top], 1):
        s = p["scores"]
        lines.append(f"| {i} | r/{p['subreddit']} | [{p['title'][:70]}]({p['url']}) | {p['match_type']} | {p['num_comments'] or 0} | "
                     f"{s['pain_severity']} | {s['autonomy_potential']} | {s['build_feasibility']} | {s['composite']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=str(Path(__file__).with_name("pain_points.json")))
    ap.add_argument("--out", default=str(Path(__file__).with_name("scored_opportunities.json")))
    ap.add_argument("--report", default=str(Path(__file__).with_name("OPPORTUNITY_RANKING.md")))
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--spec-template", default=str(Path(__file__).with_name("spec_template.md")))
    ap.add_argument("--spec", default=str(Path(__file__).with_name("PRODUCT_SPEC.md")))
    args = ap.parse_args()

    data = json.loads(Path(args.inp).read_text(encoding="utf-8"))
    posts = [p for p in data["posts"] if not re.search(NOISE_TITLE, p.get("title", ""), flags=re.I)]
    print(f"Dropped {len(data['posts']) - len(posts)} recurring digest / megathread posts")
    scored = sorted((score_post(p) for p in posts), key=lambda s: s["scores"]["composite"], reverse=True)
    themes = rank_themes(scored)

    selection = select_opportunity(themes, scored)
    Path(args.out).write_text(json.dumps({"selected": selection, "themes": themes, "posts": scored}, indent=2,
                                         ensure_ascii=False), encoding="utf-8")
    Path(args.report).write_text(markdown_report(scored, themes, args.top), encoding="utf-8")
    tpl = Path(args.spec_template)
    if tpl.exists():
        Path(args.spec).write_text(render_spec(selection, tpl), encoding="utf-8")
        print(f"Wrote product spec -> {args.spec}")

    print(f"Scored {len(scored)} posts -> {args.out}")
    print(f"\nSELECTED: {selection['theme']}  composite={selection['scores']['avg_composite']} "
          f"posts={selection['posts']} exact={selection['exact_posts']} comments={selection['total_comments']}")
    print("\nTop themes (by composite; * = eligible):")
    for t in themes[:10]:
        print(f"  {'*' if t['eligible'] else ' '} {t['avg_composite']:>5}  {t['theme']:<36} posts={t['posts']:<3} exact={t['exact_posts']:<2} "
              f"comments={t['total_comments']:<4} P{t['avg_pain_severity']} A{t['avg_autonomy_potential']} F{t['avg_build_feasibility']}")
    print("\nTop posts:")
    for p in scored[:args.top]:
        s = p["scores"]
        print(f"  {s['composite']:>5}  [{s['pain_severity']}/{s['autonomy_potential']}/{s['build_feasibility']}] "
              f"r/{p['subreddit']:<13} {p['num_comments'] or 0:>3}c  {p['title'][:75]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
