"""Writes site/library.json: every edition the website can show, newest first.

  briefing  one Daily briefing per day (site/media/digests, posted ones only)
  daily     The Daily (site/media/daily/<date>)
  weekly    The Weekly (site/media/magazine/issue-NN)
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"


def load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def nice(d: str) -> str:
    return dt.date.fromisoformat(d).strftime("%a %-d %b %Y")


def main() -> None:
    items = []
    log = load(ROOT / "social" / "digests_posted.json", {"posted": []})["posted"]
    posted = {e["key"]: e for e in log if e.get("ig")}
    by_day: dict[str, dict] = {}
    rank = {"daily": 3, "evening": 2, "morning": 1}
    for m in sorted(SITE.glob("media/digests/*/manifest.json")):
        j = load(m, {})
        key = j.get("key", "")
        if key not in posted:
            continue
        day, kind = key[:10], key[11:]
        if day not in by_day or rank.get(kind, 0) >= rank.get(by_day[day]["kind"], 0):
            by_day[day] = {"kind": kind, "dir": j.get("dir", m.parent.name), "slides": j.get("slides", 0),
                           "n": len(j.get("ids", []))}
    for day, b in by_day.items():
        items.append({"type": "briefing", "date": day, "label": nice(day),
                      "title": f"Daily briefing · {b['n']} stories", "base": f"media/digests/{b['dir']}/",
                      "first": 0, "slides": b["slides"]})
    daily = {e["date"]: e for e in load(SITE / "daily.json", {"editions": []}).get("editions", [])}
    for d in sorted(SITE.glob("media/daily/*")):
        n = len(list(d.glob("*.jpg")))
        if not n:
            continue
        if d.name not in daily:      # draft that was never published
            continue
        e = daily[d.name]
        items.append({"type": "daily", "date": d.name, "label": nice(d.name), "title": e.get("title", "The Daily"),
                      "summary": e.get("summary", ""), "base": f"media/daily/{d.name}/", "first": 1, "slides": n})
    weekly = {int(i["issue"]): i for i in load(SITE / "magazine.json", {"issues": []}).get("issues", [])}
    for d in sorted(SITE.glob("media/magazine/issue-*")):
        n = len(list(d.glob("*.jpg")))
        k = int(d.name.split("-")[1])
        if k not in weekly:          # not published yet (still a draft)
            continue
        i = weekly[k]
        import re
        m = re.search(r"(\d{1,2}) (\w+) (\d{4})\s*$", i.get("week", ""))
        date = dt.datetime.strptime(" ".join(m.groups()), "%d %B %Y").date().isoformat() if m else "2000-01-01"
        items.append({"type": "weekly", "date": i.get("date", date), "label": i.get("week", f"Issue {k}"),
                      "title": f"Issue {k}: " + i.get("title", "The Weekly"), "summary": i.get("summary", ""),
                      "base": f"media/magazine/{d.name}/", "first": 1, "slides": n})
    items.sort(key=lambda x: x["date"], reverse=True)
    (SITE / "library.json").write_text(json.dumps({"items": items}, indent=1, ensure_ascii=False), encoding="utf-8")
    print("library:", len(items), "editions")


if __name__ == "__main__":
    main()
