"""One Instagram feed post at most every 2 hours, whatever is waiting.

Asks Instagram itself when the last feed post (Reel, carousel, photo) went out, so the rule holds
across every workflow. Stories are not counted. Used by Reels, briefings, Learn carousels and The Daily.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import requests

GAP_HOURS = float(os.environ.get("IG_MIN_GAP_HOURS") or 2)


def _last_logged() -> dt.datetime | None:
    """Our own record of the last Reel, which also covers trial Reels (Instagram doesn't list those)."""
    try:
        log = json.loads((Path(__file__).resolve().parent / "posted.json").read_text(encoding="utf-8"))["posted"]
        ts = [e["date"] for e in log if "Instagram" in e.get("results", {})]
        return dt.datetime.strptime(max(ts), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc) if ts else None
    except Exception:  # noqa: BLE001
        return None


def wait_needed(ig: str, tok: str) -> float:
    """Minutes still to wait before the next feed post (0 = go ahead)."""
    times = [t for t in [_last_logged()] if t]
    try:
        d = requests.get(f"https://graph.facebook.com/v21.0/{ig}/media", timeout=30,
                         params={"fields": "timestamp", "limit": 1, "access_token": tok}).json().get("data", [])
        if d:
            times.append(dt.datetime.strptime(d[0]["timestamp"], "%Y-%m-%dT%H:%M:%S%z"))
    except requests.RequestException:
        pass
    if not times:
        return 0.0
    left = GAP_HOURS * 60 - (dt.datetime.now(dt.timezone.utc) - max(times)).total_seconds() / 60
    return max(0.0, left)


class TooSoon(RuntimeError):
    pass


def check(ig: str, tok: str) -> None:
    m = wait_needed(ig, tok)
    if m > 0:
        raise TooSoon(f"Instagram: last feed post was under {GAP_HOURS:g}h ago, waiting {m:.0f} more minutes")
