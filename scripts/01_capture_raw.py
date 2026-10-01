"""
ShuttleIQ - Step 1: RAW DATA CAPTURE (Extract layer)

Opens BWF pages in a real Chrome window (Selenium) and saves, UNTOUCHED:
  1. every JSON/XHR response the page loads in the background (the real data)
  2. the rendered HTML of each page (fallback source for parsing)
A manifest.jsonl records where every file came from (sourcing proof for TAE 1/2).

Scope: BWF World Championships - Paris 2025 (id 5261) and New Delhi 2026 (id 5601)

Usage (from the project root):
    pip install -r requirements.txt
    python scripts/01_capture_raw.py                # capture everything
    python scripts/01_capture_raw.py --only 5261    # one tournament only
    python scripts/01_capture_raw.py --summary      # show what was captured
"""
import argparse
import base64
import hashlib
import json
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
MANIFEST = RAW / "manifest.jsonl"

PAGE_WAIT = 7        # seconds to let a page finish its background calls
DELAY = 3            # polite pause between pages (avoids IP bans)
EVENTS = ["ms", "ws", "md", "wd", "xd"]

TOURNAMENTS = {
    5261: {"slug": "totalenergies-bwf-world-championships-2025",
           "start": "2025-08-25", "end": "2025-08-31"},
    5601: {"slug": "bwf-world-championships-2026",
           "start": "2026-08-17", "end": "2026-08-23"},
}

GLOBAL_PAGES = [
    ("rankings_fansite", "https://bwfbadminton.com/rankings/"),
    ("rankings_tour", "https://bwfworldtour.bwfbadminton.com/rankings/"),
]


def days(start, end):
    d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    return [(d0 + timedelta(n)).isoformat() for n in range((d1 - d0).days + 1)]


def pages_for(tid, t):
    slug = t["slug"]
    base = f"https://bwfbadminton.com/tournament/{tid}/{slug}"
    wc = f"https://bwfworldchampionships.bwfbadminton.com/results/{tid}/{slug}"
    out = [
        (f"{tid}_overview", f"{base}/"),
        (f"{tid}_players", f"{base}/players/"),
        (f"{tid}_draws", f"{base}/draws/"),
        (f"{tid}_results", f"{base}/results/"),
        (f"{tid}_matchcentre", f"https://match-centre.bwfbadminton.com/{tid}"),
    ]
    out += [(f"{tid}_results_{d}", f"{base}/results/{d}") for d in days(t["start"], t["end"])]
    out += [(f"{tid}_draw_{ev}", f"{wc}/draw/{ev}") for ev in EVENTS]
    return out


def make_driver(headless):
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1400,1000")
    opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    driver = webdriver.Chrome(options=opts)   # Selenium Manager fetches the driver
    driver.execute_cdp_cmd("Network.enable", {})
    return driver


def capture(driver, label, url, seen):
    driver.get_log("performance")            # flush old entries
    driver.get(url)
    time.sleep(PAGE_WAIT)
    for _ in range(4):                       # trigger lazy-loaded content
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1.5)

    stamp = datetime.now(timezone.utc).isoformat()
    (RAW / "html").mkdir(parents=True, exist_ok=True)
    (RAW / "html" / f"{label}.html").write_text(driver.page_source, encoding="utf-8")

    saved = 0
    (RAW / "json").mkdir(parents=True, exist_ok=True)
    for entry in driver.get_log("performance"):
        msg = json.loads(entry["message"])["message"]
        if msg.get("method") != "Network.responseReceived":
            continue
        p = msg["params"]
        resp = p["response"]
        if p.get("type") not in ("XHR", "Fetch"):
            continue
        req_url = resp["url"]
        if req_url in seen:
            continue
        try:
            body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": p["requestId"]})
        except Exception:
            continue                         # body not available (redirect/preflight)
        raw = body["body"]
        data = base64.b64decode(raw) if body.get("base64Encoded") else raw.encode("utf-8")
        seen.add(req_url)
        mime = resp.get("mimeType", "")
        ext = "json" if "json" in mime else "txt"
        fname = f"{label}__{hashlib.sha1(req_url.encode()).hexdigest()[:10]}.{ext}"
        (RAW / "json" / fname).write_bytes(data)
        with MANIFEST.open("a", encoding="utf-8") as m:   # request headers NOT stored (tokens)
            m.write(json.dumps({
                "captured_at_utc": stamp, "page_label": label, "page_url": url,
                "request_url": req_url, "status": resp.get("status"),
                "mime": mime, "bytes": len(data), "file": f"json/{fname}",
            }) + "\n")
        saved += 1
    return saved


def summary():
    if not MANIFEST.exists():
        print("No manifest yet - run the capture first.")
        return
    rows = [json.loads(l) for l in MANIFEST.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"{len(rows)} responses, {sum(r['bytes'] for r in rows)/1024:.0f} KB total\n")
    by_page = Counter(r["page_label"] for r in rows)
    for k, v in sorted(by_page.items()):
        print(f"  {k:<32} {v} responses")
    print("\nDistinct request URLs (query strings trimmed):")
    for u in sorted({r["request_url"].split("?")[0] for r in rows}):
        print("  ", u)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=int, help="tournament id, e.g. 5261")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()
    if args.summary:
        return summary()

    RAW.mkdir(parents=True, exist_ok=True)
    jobs = []
    for tid, t in TOURNAMENTS.items():
        if args.only and tid != args.only:
            continue
        jobs += pages_for(tid, t)
    if not args.only:
        jobs += GLOBAL_PAGES

    driver = make_driver(args.headless)
    seen, total = set(), 0
    try:
        for i, (label, url) in enumerate(jobs, 1):
            for attempt in (1, 2):
                try:
                    n = capture(driver, label, url, seen)
                    print(f"[{i}/{len(jobs)}] {label:<32} {n} JSON responses")
                    total += n
                    break
                except Exception as e:
                    print(f"[{i}/{len(jobs)}] {label} attempt {attempt} failed: {e}")
                    time.sleep(5)
            time.sleep(DELAY)
    finally:
        driver.quit()
    print(f"\nDone. {total} JSON responses saved under {RAW}")
    print("Next: python scripts/01_capture_raw.py --summary   (paste the output to Claude)")


if __name__ == "__main__":
    main()
