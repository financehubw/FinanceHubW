"""
Source health check: fetches every feed in sources.py and reports which ones
work, how many recent items each returned, and which are dead.
Run from the Actions tab ("Check news sources") or locally: python check_feeds.py
"""
import socket
import time
from concurrent.futures import ThreadPoolExecutor

import feedparser

from sources import FEEDS

socket.setdefaulttimeout(15)


def check(feed_def):
    url, region, category, _ = feed_def
    start = time.time()
    try:
        f = feedparser.parse(url, agent="Mozilla/5.0 (FinanceHubW news bot)")
        status = getattr(f, "status", "?")
        n = len(f.entries)
        err = "" if n else (str(f.get("bozo_exception", ""))[:80] or f"HTTP {status}")
    except Exception as e:  # noqa: BLE001
        n, err = 0, type(e).__name__
    return url, region, category, n, err, time.time() - start


def main():
    with ThreadPoolExecutor(max_workers=16) as pool:
        rows = list(pool.map(check, FEEDS))
    ok = [r for r in rows if r[3]]
    dead = [r for r in rows if not r[3]]

    lines = [f"# Source health: {len(ok)}/{len(rows)} working", "",
             "| Status | Region | Items | Source |", "|---|---|---|---|"]
    for url, region, cat, n, err, _ in sorted(rows, key=lambda r: (not r[3], r[1])):
        short = url.split("://", 1)[1][:90]
        lines.append(f"| {'✅' if n else '❌ ' + err.replace('|', '/')} | {region} | {n} | {short} |")
    report = "\n".join(lines)
    print(report)

    import os
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as fh:
            fh.write(report + "\n")
    print(f"\n{len(ok)} working, {len(dead)} dead")


if __name__ == "__main__":
    main()
