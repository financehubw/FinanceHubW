"""Writes site/archive.json: everything FinanceHubW published, by day, for the website calendar.

Includes The Daily editions, The Weekly issues, Shorts (with their YouTube links) and the
Instagram Story cards made from X posts. X posts themselves come from site/tweets.json.
Every workflow runs this before it commits, so the calendar stays current on its own.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"


def load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def main() -> None:
    items = []
    for e in load(SITE / "daily.json", {"editions": []})["editions"]:
        items.append({"date": e["date"], "type": "daily", "title": e["title"], "text": e.get("summary", ""),
                      "thumb": f"media/daily/{e['date']}/01.jpg", "link": "#magazine"})
    dates = {i["issue"]: i.get("date") for i in load(ROOT / "social" / "magazine_queue.json", {"issues": []})["issues"]}
    for w in load(SITE / "magazine.json", {"issues": []}).get("issues", []):
        d = dates.get(w["issue"])
        if d:
            items.append({"date": d, "type": "weekly", "title": f"Issue {w['issue']}: {w['title']}",
                          "text": w.get("summary", ""), "thumb": f"media/magazine/issue-{int(w['issue']):02d}/01.jpg",
                          "link": "#magazine"})
    for s in load(ROOT / "social" / "posted.json", {"posted": []})["posted"]:
        r = s.get("results", {})
        items.append({"date": s["date"][:10], "type": "short", "title": s["title"], "text": "",
                      "link": r.get("YouTube") or r.get("Instagram") or "https://youtube.com/@FinanceHubW",
                      "video": f"media/shorts/{s['file']}"})
    tweets = {t["id"]: t for t in load(SITE / "tweets.json", {"posts": []})["posts"]}
    for sid in load(ROOT / "social" / "stories_posted.json", {"posted": []})["posted"]:
        t = tweets.get(sid)
        if t and (SITE / "media" / "stories" / f"{sid}.jpg").exists():
            items.append({"date": t["date"][:10], "type": "story", "title": t["text"].split("\n")[0][:90],
                          "text": "", "thumb": f"media/stories/{sid}.jpg", "link": "https://instagram.com/financehubw"})
    items.sort(key=lambda i: i["date"], reverse=True)
    (SITE / "archive.json").write_text(json.dumps({"items": items}, ensure_ascii=False, separators=(",", ":")),
                                       encoding="utf-8")
    print(f"archive: {len(items)} items")


if __name__ == "__main__":
    main()
