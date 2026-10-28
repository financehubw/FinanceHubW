"""Deletes a Short's video from the repo once it is safely posted everywhere.

Instagram, Facebook and YouTube keep their own copies; the site only shows the thumbnail. Keeping
every 10 MB video in the repo made it grow ~200 MB a week. A video is removed when it was posted
4+ days ago with no platform left to retry (backfill retries for 3 days), or 10+ days ago regardless.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHORTS = ROOT / "site" / "media" / "shorts"


def main() -> None:
    posted = json.loads((ROOT / "social" / "posted.json").read_text())["posted"]
    queue = json.loads((ROOT / "social" / "queue.json").read_text())["items"]
    done = {p["file"] for p in posted}
    waiting = {i["file"] for i in queue if i["file"] not in done}
    now = dt.datetime.utcnow()
    freed = 0
    for p in posted:
        f = SHORTS / p["file"]
        if not f.exists() or p["file"] in waiting:
            continue
        age = (now - dt.datetime.strptime(p["date"], "%Y-%m-%dT%H:%M:%SZ")).days
        if (age >= 4 and not p.get("failed")) or age >= 10:
            freed += f.stat().st_size
            f.unlink()
            print("removed", p["file"], f"({age} days after posting)")
    print(f"freed {freed / 1e6:.0f} MB")


if __name__ == "__main__":
    main()
