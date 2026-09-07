#!/usr/bin/env python3
"""
Stage 1: Reddit pain-point extraction.

Searches a set of subreddits for posts containing automation / willingness-to-pay
phrases and writes structured results to pain_points.json.

Strategy (standard library only):
  1. Reddit public JSON endpoints (search URL + ".json").  This gives title, body,
     num_comments, score and upvote_ratio directly.
  2. If Reddit's anti-bot layer answers 403 to unauthenticated JSON requests
     (common from datacenter / VPN IPs), fall back to the public Atom feeds
     (search URL + ".rss") for discovery and the per-post ".rss" feed to count
     comments.  Atom feeds do not carry score / upvote_ratio, so those fields
     are null and `metrics_source` records where numbers came from.

Usage:
  python3 scraper.py [--max-metrics N] [--no-metrics] [--out pain_points.json]
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

SUBREDDITS = ["smallbusiness", "freelance", "ecommerce", "sysadmin"]
PHRASES = [
    "how do you automate",
    "I would pay for",
    "any tool that can",
    "hate doing this manually",
]

BASE = "https://www.reddit.com"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36 pain-point-research/0.2"
)
LIMIT = 100
TIME_WINDOW = "year"
REQUEST_DELAY = 3.0      # floor between calls; real pacing comes from Reddit's x-ratelimit-* headers
DEFAULT_WINDOW = 40.0    # observed: unauthenticated feeds allow ~1 request per 40s window
MAX_RETRIES = 5
ATOM = {"a": "http://www.w3.org/2005/Atom"}


class Blocked(Exception):
    """Reddit returned its anti-bot 403 page."""


# --------------------------------------------------------------------------- HTTP
_next_allowed = 0.0


def _throttle() -> None:
    wait = _next_allowed - time.monotonic()
    if wait > 0:
        time.sleep(wait)


def _note_headers(headers) -> None:
    """Schedule the next call from Reddit's x-ratelimit-remaining / x-ratelimit-reset headers."""
    global _next_allowed
    try:
        remaining = float(headers.get("x-ratelimit-remaining", "1"))
        reset = float(headers.get("x-ratelimit-reset", DEFAULT_WINDOW))
    except ValueError:
        remaining, reset = 0.0, DEFAULT_WINDOW
    delay = REQUEST_DELAY if remaining >= 1 else reset + 1.0
    _next_allowed = time.monotonic() + delay


def get(url: str, accept: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    for attempt in range(1, MAX_RETRIES + 1):
        _throttle()
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
                _note_headers(resp.headers)
                return body
        except urllib.error.HTTPError as e:
            if e.code == 403:
                raise Blocked(url) from e
            if e.code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                _note_headers(e.headers)
                if e.code == 429:
                    wait = _next_allowed - time.monotonic() + 2.0
                else:
                    wait = 20.0 * attempt
                print(f"    HTTP {e.code}; waiting {wait:.0f}s (attempt {attempt}/{MAX_RETRIES})", file=sys.stderr)
                time.sleep(max(wait, 1.0))
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < MAX_RETRIES:
                print(f"    network error: {e}; retrying", file=sys.stderr)
                time.sleep(10 * attempt)
                continue
            raise
    raise RuntimeError("unreachable")


def get_json(url: str) -> dict:
    return json.loads(get(url, "application/json").decode("utf-8"))


def get_atom(url: str) -> ET.Element:
    return ET.fromstring(get(url, "application/atom+xml, application/xml"))


# --------------------------------------------------------------------------- parsing
class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("p", "br", "li", "div", "h1", "h2", "h3", "blockquote"):
            self.parts.append("\n")


def html_to_text(fragment: str) -> str:
    p = _Text()
    p.feed(html.unescape(fragment or ""))
    text = "".join(p.parts)
    text = re.sub(r"\[link\]\s*\[comments\]\s*$", "", text.strip())
    text = re.sub(r"submitted by\s+/u/\S+.*$", "", text, flags=re.S).strip()
    return re.sub(r"\n{3,}", "\n\n", text)


def ts(epoch: float | None) -> str | None:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat() if epoch else None


# --------------------------------------------------------------------------- search
def search_json(sub: str, phrase: str) -> list[dict]:
    q = urllib.parse.urlencode({"q": f'"{phrase}"', "restrict_sr": "1", "sort": "relevance",
                                "t": TIME_WINDOW, "limit": LIMIT, "raw_json": "1"})
    data = get_json(f"{BASE}/r/{sub}/search.json?{q}")
    out = []
    for child in data.get("data", {}).get("children", []):
        p = child.get("data", {})
        if child.get("kind") != "t3" or not p.get("is_self"):
            continue
        out.append({
            "id": p["id"], "subreddit": p.get("subreddit", sub),
            "title": p.get("title", "").strip(), "body": (p.get("selftext") or "").strip(),
            "author": p.get("author"), "url": f"{BASE}{p.get('permalink', '')}",
            "created_utc": ts(p.get("created_utc")),
            "num_comments": int(p.get("num_comments") or 0), "score": int(p.get("score") or 0),
            "upvote_ratio": float(p["upvote_ratio"]) if p.get("upvote_ratio") is not None else None,
            "metrics_source": "json",
        })
    return out


PHRASE_VARIANTS = {
    "I would pay for": [r"\bi(?:'d| would) (?:gladly |happily )?pay for\b", r"\bwould pay for\b"],
    "any tool that can": [r"\b(?:any|a) tool that (?:can|could|does)\b", r"\bis there a tool\b"],
    "hate doing this manually": [r"\bhate doing (?:this|it|that|these) manually\b", r"\bhate doing .{0,40} manually\b",
                                 r"\bdoing (?:this|it) manually\b"],
    "how do you automate": [r"\bhow (?:do|would|did|can) (?:you|i|we) automate\b", r"\bhow to automate\b"],
}


# Key term that must appear for a loose-search result to count as a "keyword" match.
PHRASE_KEYTERM = {
    "I would pay for": r"\b(?:pay(?:ing)? for|worth paying|subscription|per month|/mo\b)",
    "any tool that can": r"\b(?:tools?|software|app|saas|script|plugin|extension)\b",
    "hate doing this manually": r"\b(?:manual(?:ly)?|by hand|tedious|repetitive|time[- ]consuming)\b",
    "how do you automate": r"\b(?:automat\w+|script\w*|workflow|zapier|make\.com|n8n)\b",
}


def match_type(phrase: str, text: str) -> str | None:
    """'exact' if the phrase (or a close variant) is present, 'keyword' if only its key term is, else None."""
    if any(re.search(p, text, flags=re.I) for p in PHRASE_VARIANTS.get(phrase, [re.escape(phrase)])):
        return "exact"
    if re.search(PHRASE_KEYTERM.get(phrase, re.escape(phrase)), text, flags=re.I):
        return "keyword"
    return None


def search_rss(sub: str, phrase: str, exact: bool = True) -> list[dict]:
    q = urllib.parse.urlencode({"q": f'"{phrase}"' if exact else phrase, "restrict_sr": "1", "sort": "relevance",
                                "t": TIME_WINDOW, "limit": LIMIT})
    root = get_atom(f"{BASE}/r/{sub}/search.rss?{q}")
    out = []
    for e in root.findall("a:entry", ATOM):
        full_id = e.findtext("a:id", default="", namespaces=ATOM)
        if not full_id.startswith("t3_"):
            continue
        link = e.find("a:link", ATOM)
        author = e.find("a:author/a:name", ATOM)
        out.append({
            "id": full_id[3:], "subreddit": sub,
            "title": html.unescape(e.findtext("a:title", default="", namespaces=ATOM)).strip(),
            "body": html_to_text(e.findtext("a:content", default="", namespaces=ATOM)),
            "author": (author.text or "").replace("/u/", "") if author is not None else None,
            "url": link.get("href") if link is not None else None,
            "created_utc": e.findtext("a:published", default=None, namespaces=ATOM),
            "num_comments": None, "score": None, "upvote_ratio": None,
            "metrics_source": "rss",
        })
    return out


# --------------------------------------------------------------------------- metrics
def metrics_json(rec: dict) -> None:
    data = get_json(rec["url"].rstrip("/") + ".json?limit=1&raw_json=1")
    p = data[0]["data"]["children"][0]["data"]
    rec.update(num_comments=int(p.get("num_comments") or 0), score=int(p.get("score") or 0),
               upvote_ratio=float(p["upvote_ratio"]) if p.get("upvote_ratio") is not None else None,
               metrics_source="json")


def metrics_rss(rec: dict) -> None:
    root = get_atom(rec["url"].rstrip("/") + "/.rss?limit=500")
    entries = root.findall("a:entry", ATOM)
    comments = sum(1 for e in entries if e.findtext("a:id", default="", namespaces=ATOM).startswith("t1_"))
    rec.update(num_comments=comments, metrics_source="rss-comment-count")


# --------------------------------------------------------------------------- output
def write_output(path: str, records: list[dict], stats: dict, json_blocked: bool, partial: bool) -> None:
    records = sorted(records, key=lambda r: (r.get("match_type") == "exact", (r["num_comments"] or 0),
                                             (r["score"] or 0), len(r["matched_phrases"])), reverse=True)
    out = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "partial": partial,
        "source": "reddit public JSON endpoints with RSS fallback",
        "subreddits": SUBREDDITS, "phrases": PHRASES, "time_window": TIME_WINDOW,
        "notes": ("upvote_ratio/score are null when Reddit blocked the JSON endpoints and the "
                  "Atom feeds were used instead; num_comments then comes from the post's comment feed. "
                  "match_type is 'exact' when the phrase (or a close variant) appears in the post, "
                  "'keyword' when only the phrase's key term does."),
        "stats": {**stats, "json_blocked": json_blocked, "unique_posts": len(records)},
        "posts": records,
    }
    tmp = Path(path).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


# --------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-metrics", type=int, default=80, help="fetch per-post metrics for at most N posts")
    ap.add_argument("--no-metrics", action="store_true")
    ap.add_argument("--out", default=str(Path(__file__).with_name("pain_points.json")))
    args = ap.parse_args()

    json_blocked = False
    seen: dict[str, dict] = {}
    stats = {"queries": 0, "failed_queries": 0, "json_blocked": False, "metrics_fetched": 0}

    for sub in SUBREDDITS:
        for phrase in PHRASES:
            print(f"r/{sub:<14} \"{phrase}\"", end=" ... ", flush=True)
            posts: list[dict] = []
            try:
                if not json_blocked:
                    try:
                        posts = search_json(sub, phrase)
                    except Blocked:
                        json_blocked = stats["json_blocked"] = True
                        print("JSON blocked (403) -> RSS fallback", end=" ... ", flush=True)
                if json_blocked:
                    posts = search_rss(sub, phrase, exact=True)
                    for p in posts:
                        p["match_type"] = "exact"
                    # Reddit's exact-phrase search is title-heavy and sparse; widen to a loose query
                    # and keep posts that contain the phrase (exact) or its key term (keyword).
                    loose = search_rss(sub, phrase, exact=False)
                    ids = {p["id"] for p in posts}
                    extra = []
                    for p in loose:
                        if p["id"] in ids:
                            continue
                        mt = match_type(phrase, p["title"] + "\n" + p["body"])
                        if mt:
                            p["match_type"] = mt
                            extra.append(p)
                    n_exact = sum(1 for p in extra if p["match_type"] == "exact")
                    print(f"exact={len(posts)}+{n_exact} keyword={len(extra) - n_exact} (loose={len(loose)})", end=" ... ", flush=True)
                    posts += extra
                    stats["queries"] += 1
                stats["queries"] += 1
            except Exception as e:  # noqa: BLE001
                stats["failed_queries"] += 1
                print(f"FAILED: {e}")
                continue
            new = 0
            for rec in posts:
                if rec["id"] in seen:
                    prev = seen[rec["id"]]
                    prev["matched_phrases"].append(phrase)
                    if rec["match_type"] == "exact":
                        prev["match_type"] = "exact"
                else:
                    rec["matched_phrases"] = [phrase]
                    seen[rec["id"]] = rec
                    new += 1
            print(f"{len(posts)} results, {new} new")
            write_output(args.out, list(seen.values()), stats, json_blocked, partial=True)

    records = list(seen.values())

    if not args.no_metrics:
        # Exact-phrase posts first: they are the ones the analyzer and marketing plan lean on.
        records.sort(key=lambda r: (r.get("match_type") == "exact", len(r["matched_phrases"])), reverse=True)
        need = [r for r in records if r["num_comments"] is None][: args.max_metrics]
        print(f"\nFetching metrics for {len(need)} posts ...", flush=True)
        for i, rec in enumerate(need, 1):
            try:
                if not json_blocked:
                    try:
                        metrics_json(rec)
                    except Blocked:
                        json_blocked = stats["json_blocked"] = True
                if json_blocked:
                    metrics_rss(rec)
                stats["metrics_fetched"] += 1
                print(f"  [{i}/{len(need)}] {rec['num_comments']:>3} comments  {rec['title'][:70]}", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"  [{i}/{len(need)}] FAILED {rec['id']}: {e}", flush=True)
            write_output(args.out, records, stats, json_blocked, partial=True)

    write_output(args.out, records, stats, json_blocked, partial=False)
    print(f"\nWrote {len(records)} unique posts to {args.out}  (json_blocked={json_blocked})")
    return 0 if records else 1


if __name__ == "__main__":
    sys.exit(main())
