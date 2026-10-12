"""Learn the posting times that get FinanceHubW the most views, from its own Instagram numbers.

Weekly: reads the reach of every recent post (Reels, briefings, The Daily) and the hour it went out,
then picks the best hour for each kind. A time only changes once there is enough data
(>= MIN_POSTS posts of that kind spread over >= 3 different hours) and the winner beats the
current time by >= 15%, so one lucky post cannot move the schedule. Result: social/best_times.json,
read by the Short (social.yml) and the briefings (x_story.py). Needs instagram_manage_insights.
"""
from __future__ import annotations
import datetime as dt, json, os, statistics, sys
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "social" / "best_times.json"
GRAPH = "https://graph.facebook.com/v21.0"
MIN_POSTS = 10
DEFAULTS = {"short": "15:00", "briefing_morning": "01:30", "briefing_evening": "12:30"}   # UTC
WINDOWS = {"short": (11, 18), "briefing_morning": (0, 5), "briefing_evening": (10, 15)}     # allowed UTC hours


def kind(m: dict) -> str | None:
    cap = (m.get("caption") or "").lower()
    if m.get("media_type") == "VIDEO":
        return "short"
    if "morning briefing" in cap:
        return "briefing_morning"
    if "evening briefing" in cap:
        return "briefing_evening"
    return None


def main() -> None:
    ig, tok = os.environ.get("IG_USER_ID"), os.environ.get("META_TOKEN")
    cur = json.loads(OUT.read_text()) if OUT.exists() else {"times": dict(DEFAULTS), "notes": {}}
    cur.setdefault("times", dict(DEFAULTS)); cur.setdefault("notes", {})
    if not (ig and tok):
        sys.exit("Instagram secrets missing")
    media = requests.get(f"{GRAPH}/{ig}/media", timeout=30, params={
        "fields": "id,media_type,timestamp,caption", "limit": 100, "access_token": tok}).json().get("data", [])
    by = {}
    for m in media:
        k = kind(m)
        if not k:
            continue
        r = requests.get(f"{GRAPH}/{m['id']}/insights", timeout=30,
                         params={"metric": "reach", "access_token": tok}).json()
        if "error" in r:
            cur["notes"]["status"] = f"no insights permission yet: {r['error'].get('message', '')[:120]}"
            OUT.write_text(json.dumps(cur, indent=1)); print(cur["notes"]["status"]); return
        reach = r["data"][0]["values"][0]["value"]
        hour = dt.datetime.strptime(m["timestamp"][:19], "%Y-%m-%dT%H:%M:%S").hour
        by.setdefault(k, []).append((hour, reach))
    for k, rows in by.items():
        hours = {}
        for h, r in rows:
            hours.setdefault(h, []).append(r)
        note = f"{len(rows)} posts over {len(hours)} hours"
        lo, hi = WINDOWS[k]
        cand = {h: statistics.median(v) for h, v in hours.items() if lo <= h <= hi and len(v) >= 2}
        if len(rows) >= MIN_POSTS and len(cand) >= 3:
            best = max(cand, key=cand.get)
            now_h = int(cur["times"][k][:2])
            if best != now_h and cand[best] >= 1.15 * cand.get(now_h, 0):
                cur["times"][k] = f"{best:02d}:{cur['times'][k][3:]}"
                note += f"; moved to {best:02d}h UTC (median reach {cand[best]:.0f})"
        cur["notes"][k] = note
    cur["notes"]["status"] = "ok"
    cur["updated"] = dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ")
    OUT.write_text(json.dumps(cur, indent=1)); print(json.dumps(cur, indent=1))


if __name__ == "__main__":
    main()
