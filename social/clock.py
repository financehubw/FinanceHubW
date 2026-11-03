"""Reliable clock for the Shorts slots.

GitHub drops many scheduled runs (on 3 Nov the hourly posting cron fired only 3 times in 24 hours), so the
4-a-day schedule slipped. This waits for the next slot in social/best_times.json, starts "Post Short" (which
still checks that a post is due and that 3 hours have passed), then starts the next Clock run. A 6-hourly
cron restarts the chain if it ever stops. Free: public-repo runner time costs nothing.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
REPO = os.environ.get("GITHUB_REPOSITORY", "financehubw/FinanceHubW")
API = f"https://api.github.com/repos/{REPO}/actions/workflows"
H = {"Authorization": f"Bearer {os.environ.get('GH_TOKEN', '')}", "Accept": "application/vnd.github+json"}
MAX_WAIT = 5 * 3600 + 20 * 60          # a job may run 6 hours; leave room to hand over


def slots() -> list[str]:
    try:
        t = json.loads((ROOT / "social" / "best_times.json").read_text())["times"]
    except Exception:  # noqa: BLE001
        t = {}
    return sorted({t.get("short_midday", "06:30"), t.get("short", "15:00"), t.get("short_us", "18:30"),
                   t.get("short_night", "22:30")})


def next_slot(now: dt.datetime) -> dt.datetime:
    cands = []
    for day in (0, 1):
        for s in slots():
            t = (now + dt.timedelta(days=day)).replace(hour=int(s[:2]), minute=int(s[3:]), second=0, microsecond=0)
            if t > now + dt.timedelta(minutes=3):
                cands.append(t)
    return min(cands)


def dispatch(workflow: str, inputs: dict | None = None) -> None:
    r = requests.post(f"{API}/{workflow}/dispatches", headers=H, timeout=30,
                      json={"ref": "main", **({"inputs": inputs} if inputs else {})})
    print(f"dispatch {workflow}: HTTP {r.status_code} {r.text[:200]}")


def main() -> None:
    now = dt.datetime.now(dt.timezone.utc)
    target = next_slot(now)
    fire_at = target - dt.timedelta(minutes=2)
    wait = (fire_at - now).total_seconds()
    if wait > MAX_WAIT:
        print(f"next slot {target:%H:%M} UTC is {wait / 3600:.1f} h away; handing over to a new Clock run")
        time.sleep(MAX_WAIT)
        dispatch("clock.yml")
        return
    print(f"next Short slot {target:%Y-%m-%d %H:%M} UTC; waiting {max(0, wait) / 60:.0f} min")
    time.sleep(max(0.0, wait))
    dispatch("social.yml", {"from_clock": "true"})
    time.sleep(240)                   # let that slot pass before the next Clock run looks for a slot
    dispatch("clock.yml")


if __name__ == "__main__":
    main()
