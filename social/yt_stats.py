"""Per-Short YouTube numbers -> docs/yt_stats.json.

Public stats (views, likes, comments) plus YouTube Analytics (how much of each Short people watch,
and how many subscribers each one brought in). Those two decide which formats grow the channel.
"""
import datetime as dt
import json
import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parent.parent
log = json.loads((ROOT / "social/posted.json").read_text())["posted"]
ids = {e["results"]["YouTube"].rsplit("/", 1)[-1]: e for e in log if "YouTube" in e.get("results", {})}
creds = Credentials.from_authorized_user_info(json.loads(os.environ["YT_TOKEN_JSON"]))
yt = build("youtube", "v3", cache_discovery=False, credentials=creds)

out = {}
keys = list(ids)
for i in range(0, len(keys), 50):                     # the API takes at most 50 ids per call
    try:
        r = yt.videos().list(part="statistics,contentDetails,snippet", id=",".join(keys[i:i + 50])).execute()
    except Exception as e:  # noqa: BLE001
        (ROOT / "docs/yt_stats.json").write_text(json.dumps({"error": str(e)[:400]}))
        raise SystemExit(0)
    for v in r.get("items", []):
        s = v["statistics"]
        out[v["id"]] = {"id": v["id"], "file": ids[v["id"]]["file"], "posted": ids[v["id"]]["date"],
                        "title": v["snippet"]["title"], "duration": v["contentDetails"]["duration"],
                        "views": int(s.get("viewCount", 0)), "likes": int(s.get("likeCount", 0)),
                        "comments": int(s.get("commentCount", 0))}

analytics_note = "ok"
try:   # needs the yt-analytics.readonly permission granted when the YouTube token was made
    ya = build("youtubeAnalytics", "v2", cache_discovery=False, credentials=creds)
    end = dt.date.today().isoformat()
    rep = ya.reports().query(ids="channel==MINE", startDate="2026-10-01", endDate=end,
                             metrics="views,averageViewDuration,averageViewPercentage,subscribersGained,shares",
                             dimensions="video", sort="-views", maxResults=200).execute()
    cols = [c["name"] for c in rep.get("columnHeaders", [])]
    for row in rep.get("rows", []):
        d = dict(zip(cols, row))
        if d["video"] in out:
            out[d["video"]].update({"avg_view_pct": round(d["averageViewPercentage"], 1),
                                    "avg_view_sec": d["averageViewDuration"],
                                    "subs_gained": d["subscribersGained"], "shares": d["shares"]})
    src = ya.reports().query(ids="channel==MINE", startDate="2026-10-01", endDate=end,
                             metrics="views", dimensions="insightTrafficSourceType", sort="-views").execute()
    traffic = {r[0]: r[1] for r in src.get("rows", [])}
except Exception as e:  # noqa: BLE001
    detail = getattr(e, "content", b"")
    analytics_note, traffic = (detail.decode("utf-8", "ignore") if isinstance(detail, bytes) else str(e))[:600], {}

try:
    ch = yt.channels().list(part="statistics", mine=True).execute()["items"][0]["statistics"]
except Exception as e:  # noqa: BLE001
    ch = {"error": str(e)[:150]}
(ROOT / "docs/yt_stats.json").write_text(json.dumps(
    {"channel": ch, "analytics": analytics_note, "traffic_sources": traffic,
     "videos": sorted(out.values(), key=lambda x: x["posted"])}, indent=1))
print(json.dumps({"channel": ch, "analytics": analytics_note, "traffic": traffic}, indent=1))

# ---- what works: median views per kind of Short -> posting weights for social/mix.py
try:
    import statistics
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "social"))
    import mix
    queue = {i["file"]: i for i in json.loads((ROOT / "social/queue.json").read_text())["items"]}
    cutoff = (dt.datetime.utcnow() - dt.timedelta(days=2)).strftime("%Y-%m-%d")
    by, watch = {}, {}
    for v in out.values():
        if v["posted"][:10] <= cutoff:
            it = queue.get(v["file"], {"file": v["file"], "title": v["title"]})
            by.setdefault(mix.category(it), []).append(v["views"])
            if v.get("avg_view_pct") is not None and v["views"] >= 10:
                watch.setdefault(mix.category(it), []).append(min(150.0, v["avg_view_pct"]))
    allv = [x for xs in by.values() for x in xs]
    base = statistics.median(allv) if allv else 1
    allw = [x for xs in watch.values() for x in xs]
    wbase = statistics.median(allw) if allw else None
    table, w = {}, {}
    for c in set(mix.DEFAULT) | set(by):
        xs = by.get(c, [])
        med = statistics.median(xs) if xs else None
        wm = statistics.median(watch[c]) if watch.get(c) else None
        table[c] = {"shorts": len(xs), "median_views": med, "mean_views": round(sum(xs) / len(xs), 1) if xs else None,
                    "median_watch_pct": wm}
        if len(xs) < 4:          # not enough data yet: keep testing it
            w[c] = mix.DEFAULT.get(c, 1.0)
        else:                    # mostly the median; the mean counts a little, capped, so one viral hit can't take over
            score = (0.7 * med + 0.3 * min(sum(xs) / len(xs), 2 * med)) / max(1, base)
            if wm and wbase:     # Shorts people watch to the end get pushed further by YouTube
                score *= (wm / wbase) ** 0.5
            w[c] = round(min(2.5, max(0.4, score)), 2)
    (ROOT / "social/format_weights.json").write_text(json.dumps(
        {"updated": dt.date.today().isoformat(), "weights": w, "table": table}, indent=1))
    print("format weights:", w)
except Exception as e:  # noqa: BLE001
    print("format weights skipped:", e)
