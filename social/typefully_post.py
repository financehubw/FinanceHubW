"""Posts the day's top story to X through Typefully (official X partner, free plan = 10 posts/month).

Runs every 3rd day. Skips if the month's quota is used up or the story was already posted.
Needs TYPEFULLY_API_KEY (and optionally TYPEFULLY_SOCIAL_SET, default 347703).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
FEED = ROOT / "site" / "tweets.json"
LOG = ROOT / "social" / "typefully_posted.json"
API = "https://api.typefully.com/v2"
SET = os.environ.get("TYPEFULLY_SOCIAL_SET") or "347703"


def xlen(s: str) -> int:
    return sum(2 if ord(c) > 0x10FF else 1 for c in s)


def fit(text: str) -> str:
    lines = [l for l in text.split("\n") if not re.match(r"\s*https?://", l)]
    t = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    t = re.sub(r"\s*\([^)]{20,}\)", "", t)
    while xlen(t) > 275:
        t = t[:-2].rstrip() + "…" if not t.endswith("…") else t[:-3].rstrip() + "…"
    return t


def main() -> None:
    key = os.environ.get("TYPEFULLY_API_KEY")
    if not key:
        sys.exit("TYPEFULLY_API_KEY not set")
    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    info = requests.get(f"{API}/social-sets/{SET}", headers=h, timeout=30).json()
    left = (info.get("publishing_quota") or {}).get("remaining")
    if left is not None and left <= 0:
        print("Typefully: monthly quota used up"); return
    log = json.loads(LOG.read_text()) if LOG.exists() else {"posted": []}
    done = {e["id"] for e in log["posted"]}
    now = dt.datetime.utcnow()
    posts = [p for p in json.loads(FEED.read_text())["posts"]
             if "📍" in p["text"] and p["id"] not in done
             and now - dt.datetime.strptime(p["date"], "%Y-%m-%dT%H:%M:%SZ") < dt.timedelta(hours=24)]
    score = lambda p: ("BREAKING" in p["text"]) * 3 + ("✅" in p["text"]) * 2 + ("Official" in p["text"])
    if not posts:
        print("Typefully: no fresh story"); return
    best = max(posts, key=score)
    text = fit(best["text"])
    if os.environ.get("DRY_RUN"):
        print("would post:\n" + text); return
    r = requests.post(f"{API}/social-sets/{SET}/drafts", headers=h, timeout=60, json={
        "platforms": {"x": {"enabled": True, "posts": [{"text": text}]}}, "publish_at": "now"}).json()
    print("Typefully:", {k: r.get(k) for k in ("id", "status", "publish_state")} if isinstance(r, dict) else r)
    if isinstance(r, dict) and r.get("id"):
        log["posted"].append({"id": best["id"], "draft": r["id"], "t": now.isoformat()})
        LOG.write_text(json.dumps(log, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
