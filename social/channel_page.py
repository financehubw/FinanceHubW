"""Keeps the YouTube channel page working for new visitors (runs nightly, changes only what differs).

  - description and keywords that say what the channel is and help search
  - the trailer shown to non-subscribers: the best-performing video of the last 30 days
  - shelves on the home page for the series playlists, best series first
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parent.parent
DESCRIPTION = """Money, explained in under a minute.

• Real footage of the moments that shaped money: presidents, Fed chairs and history's biggest money decisions, in their own words.
• Fed Watch: the key answers from every Federal Reserve press conference.
• Money rules, true money stories and the math behind wealth, with real numbers.

New Shorts every day. Every figure is sourced and every clip is credited.
Educational content, not financial advice.

Website: https://financehubw-site.vercel.app"""
KEYWORDS = ('finance money investing "personal finance" inflation "interest rates" "federal reserve" "stock market" '
            '"money history" economics "compound interest" budgeting "financial literacy" "fed chair" "real footage"')
SHELVES = ["Money History, in Real Footage", "Fed Watch", "Money Stories", "Money Basics", "Compound Interest, Explained"]


def main() -> None:
    yt = build("youtube", "v3", cache_discovery=False,
               credentials=Credentials.from_authorized_user_info(json.loads(os.environ["YT_TOKEN_JSON"])))
    ch = yt.channels().list(part="brandingSettings,snippet", mine=True).execute()["items"][0]
    cid, bs = ch["id"], ch.get("brandingSettings", {})
    chan = dict(bs.get("channel", {}))
    stats = json.loads((ROOT / "social" / "yt_stats.json").read_text()) if (ROOT / "social" / "yt_stats.json").exists() else {}
    since = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    recent = [v for v in stats.get("videos", []) if v.get("posted", "")[:10] >= since] or stats.get("videos", [])
    best = max(recent, key=lambda v: v.get("views", 0), default=None)
    want = {"description": DESCRIPTION, "keywords": KEYWORDS, "defaultLanguage": "en"}
    if best:
        want["unsubscribedTrailer"] = best["id"]
    if any(chan.get(k) != v for k, v in want.items()):
        chan.update(want)
        try:
            yt.channels().update(part="brandingSettings", body={"id": cid, "brandingSettings": {**bs, "channel": chan}}).execute()
            print("channel page updated:", ", ".join(k for k in want), "| trailer:", best["title"] if best else "-")
        except Exception as e:  # noqa: BLE001
            print("channel update skipped:", str(e)[:300])
    else:
        print("channel page already up to date")
    # home-page shelves for the series playlists
    playlists = json.loads((ROOT / "social" / "yt_playlists.json").read_text())
    try:
        have = yt.channelSections().list(part="snippet,contentDetails", mine=True).execute().get("items", [])
        shown = {p for s in have for p in s.get("contentDetails", {}).get("playlists", [])}
        pos = len(have)
        for name in SHELVES:
            pid = playlists.get(name)
            if not pid or pid in shown:
                continue
            yt.channelSections().insert(part="snippet,contentDetails", body={
                "snippet": {"type": "singlePlaylist", "position": pos},
                "contentDetails": {"playlists": [pid]}}).execute()
            print("home shelf added:", name); pos += 1
    except Exception as e:  # noqa: BLE001
        print("home shelves skipped:", str(e)[:300])


if __name__ == "__main__":
    main()
