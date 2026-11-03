"""Which kind of Short goes out next, so the channel keeps testing and leans into what works.

Every Short belongs to a category. The posting order follows category weights (more slots for categories whose
Shorts get more views), never the same category twice in a row. social/stats.py recomputes the weights daily from
YouTube view counts; new categories get an exploration bonus until there is enough data to judge them.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEIGHTS = ROOT / "social" / "format_weights.json"
DEFAULT = {"clip": 1.2, "micro": 1.2, "story": 1.0, "lesson": 1.0, "data": 0.6}


def category(item: dict) -> str:
    f, tag, title = item.get("file", ""), item.get("thumb_tag", ""), item.get("title", "")
    if item.get("format") == "clip" or f.startswith("clip_"):
        return "clip"
    if item.get("format") == "micro" or item.get("loop") or f.startswith("loop_"):
        return "micro"
    if f.startswith("news_"):
        return "news"
    if f.startswith(("whatif_", "monthly_", "vs_", "race_", "top5_")) or tag in (
            "WHAT IF", "VS", "RACE", "MONTHLY HABIT", "COUNTDOWN"):
        return "data"
    if "Money Stories" in title or tag in ("TRUE STORY", "SECRET MILLIONAIRE", "DOT-COM CRASH", "2008 CRASH"):
        return "story"
    return "lesson"


def weights() -> dict[str, float]:
    try:
        return {**DEFAULT, **json.loads(WEIGHTS.read_text(encoding="utf-8")).get("weights", {})}
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULT)


def pick(ready: list[dict], log: list[dict], queue: dict[str, dict]) -> dict | None:
    """First ready item of the category that is furthest behind its target share (last 6 posts)."""
    if not ready:
        return None
    w = weights()
    cats = {}
    for it in ready:
        cats.setdefault(category(it), []).append(it)
    recent = [category(queue.get(p["file"], {"file": p["file"], "title": p.get("title", "")})) for p in log[-6:]]
    last = recent[-1] if recent else None
    choices = [c for c in cats if c != last] or list(cats)
    total = sum(w.get(c, 1.0) for c in choices) or 1.0
    n = len(recent) + 1

    def deficit(c):
        return w.get(c, 1.0) / total * n - recent.count(c)
    best = max(choices, key=lambda c: (deficit(c), w.get(c, 1.0)))
    return cats[best][0]
