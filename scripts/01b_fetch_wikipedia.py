"""
ShuttleIQ - Step 1b: RAW DATA EXTRACT from Wikipedia (MediaWiki API)

Why: bwfbadminton.com sits behind Cloudflare and blocks automated browsers.
Wikipedia's per-event pages (draw brackets, seeds, set scores) are freely
available through its official API.

For every page we save, UNTOUCHED:
  data/raw/wikipedia/wikitext/<page>.wikitext   raw page source (bracket templates etc.)
  data/raw/wikipedia/html/<page>.html           rendered HTML (fallback)
  data/raw/manifest_wikipedia.jsonl             URL, revision id, timestamp, size (sourcing proof)

Usage (from the project root):
    python scripts/01b_fetch_wikipedia.py
    python scripts/01b_fetch_wikipedia.py --summary
"""
import argparse
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
WIKI = RAW / "wikipedia"
MANIFEST = RAW / "manifest_wikipedia.jsonl"

API = "https://en.wikipedia.org/w/api.php"
# Wikipedia asks bots to identify themselves. Put YOUR email below.
CONTACT = "payalkakad2113@gmail.com"
HEADERS = {"User-Agent": f"ShuttleIQ-BI-Project/1.0 (student project; github.com/payalkakad01/shuttleIQ; {CONTACT})"}
DELAY = 2   # seconds between calls (be polite)

YEARS = [2025, 2026]
EVENTS = ["Men's singles", "Women's singles", "Men's doubles", "Women's doubles", "Mixed doubles"]


def page_titles():
    for y in YEARS:
        yield f"{y} BWF World Championships"                       # overview, medals, nations
        for ev in EVENTS:
            yield f"{y} BWF World Championships \u2013 {ev}"        # en dash, as on Wikipedia


def safe_name(title):
    return re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_")


def call(title, prop):
    r = requests.get(API, headers=HEADERS, timeout=30, params={
        "action": "parse", "page": title, "prop": prop,
        "redirects": 1, "format": "json", "formatversion": 2})
    r.raise_for_status()
    return r.json()


def fetch_all():
    (WIKI / "wikitext").mkdir(parents=True, exist_ok=True)
    (WIKI / "html").mkdir(parents=True, exist_ok=True)
    ok = missing = 0
    for title in page_titles():
        name = safe_name(title)
        try:
            wt = call(title, "wikitext|revid")
            if "error" in wt:
                print(f"MISSING  {title}  ({wt['error'].get('info')})")
                missing += 1
                time.sleep(DELAY)
                continue
            text = wt["parse"]["wikitext"]
            revid = wt["parse"].get("revid")
            time.sleep(DELAY)
            html = call(title, "text")["parse"]["text"]
            (WIKI / "wikitext" / f"{name}.wikitext").write_text(text, encoding="utf-8")
            (WIKI / "html" / f"{name}.html").write_text(html, encoding="utf-8")
            with MANIFEST.open("a", encoding="utf-8") as m:
                m.write(json.dumps({
                    "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                    "title": title, "revision_id": revid,
                    "url": "https://en.wikipedia.org/wiki/" + title.replace(" ", "_"),
                    "wikitext_file": f"wikipedia/wikitext/{name}.wikitext",
                    "html_file": f"wikipedia/html/{name}.html",
                    "wikitext_bytes": len(text.encode("utf-8")),
                }) + "\n")
            print(f"OK       {title}  ({len(text):,} chars, rev {revid})")
            ok += 1
        except Exception as e:
            print(f"ERROR    {title}: {e}")
        time.sleep(DELAY)
    print(f"\nDone: {ok} saved, {missing} missing. Files in {WIKI}")
    print("Next: python scripts/01b_fetch_wikipedia.py --summary   (paste the output to Claude)")


def summary():
    files = sorted((WIKI / "wikitext").glob("*.wikitext"))
    if not files:
        print("Nothing fetched yet.")
        return
    for f in files:
        t = f.read_text(encoding="utf-8")
        tpl = Counter(m.strip() for m in re.findall(r"\{\{\s*([^|{}\n]+)", t))
        top = ", ".join(f"{k} x{v}" for k, v in tpl.most_common(6))
        print(f"{f.name:<75} {len(t):>8,} chars | RD1-team lines: {t.count('RD1-team')} | {top}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    summary() if a.summary else fetch_all()
