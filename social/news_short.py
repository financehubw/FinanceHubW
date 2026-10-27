"""Same-day news Short: turns the day's strongest fact-checked story into a voiced Short and puts it
first in the posting queue, so it goes out at the next Short slot while people are searching for it.

Uses only what the news bot already verified (headline, key fact, figure, why it matters).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEED = ROOT / "site" / "tweets.json"
SCRIPTS = ROOT / "social" / "shorts_scripts"
QUEUE = ROOT / "social" / "queue.json"
sys.path.insert(0, str(ROOT / "social"))


def clean(s: str) -> str:
    return re.sub(r"^[^A-Za-z0-9$€£]+", "", s).replace("BREAKING:", "").strip()


def pick() -> dict | None:
    now = dt.datetime.utcnow()
    posts = [p for p in json.loads(FEED.read_text())["posts"]
             if "📍" in p["text"] and "India" not in p["text"]
             and now - dt.datetime.strptime(p["date"], "%Y-%m-%dT%H:%M:%SZ") < dt.timedelta(hours=14)]
    def score(p):
        t = p["text"]
        srcs = int(m.group(1)) if (m := re.search(r"✅ (\d+) sources", t)) else (1 if "Official" in t else 0)
        return ("BREAKING" in t) * 4 + min(srcs, 4) + ("📊" in t) * 2 + ("💡" in t)
    posts = [p for p in posts if score(p) >= 4]
    return max(posts, key=score) if posts else None


def script(p: dict) -> dict:
    lines = [l.strip() for l in p["text"].split("\n") if l.strip()]
    raw = clean(lines[0]).rstrip(".")
    KEEP = {"US", "UK", "EU", "IMF", "ECB", "AI", "IPO", "GDP", "UAE", "OPEC", "SEC", "FCA", "ETF", "CEO", "BOJ", "RBI", "S&P", "NATO", "G7", "G20"}
    if raw.isupper():
        ws = raw.split()
        head = " ".join(w if w in KEEP else (w.capitalize() if i == 0 else w.lower()) for i, w in enumerate(ws))
        head = re.sub(r"\b(fed|nvidia|apple|tesla|china|japan|europe|britain|germany|india|bitcoin|amazon|microsoft|google|meta|trump|powell|warsh)\b",
                      lambda m: m.group(1).capitalize(), head)
    else:
        head = raw
    fact = next((clean(l) for l in lines if l.startswith("📌")), head)
    stat = next((clean(l) for l in lines if l.startswith("📊")), "")
    why = next((clean(l) for l in lines if l.startswith("💡")), "")
    src = next((l for l in lines if l.startswith("📍")), "")
    import photos
    q = photos.query_for(p["text"]) if hasattr(photos, "query_for") else "stock market"
    day = dt.date.today()
    sid = f"news_{day:%Y%m%d}"
    scenes = [{"say": f"Today in money. {head}.", "chat": head + "."},
              {"say": fact, "photo": q, "clip": {"kicker": src.replace("📍", "").split("·")[0].strip() or "Markets",
                                                    "year": day.strftime("%-d %b"), "text": head[:60]}}]
    if stat and ":" in stat:
        label, val = stat.split(":", 1)
        scenes.append({"say": f"{label.strip()}: {val.strip()}.", "photo": q, "big": val.strip()[:14], "sub": label.strip()[:40]})
    if why:
        scenes.append({"say": f"Why it matters. {why}", "slide": [w for w in re.split(r"(?<=[,.]) ", why) if w][:3]})
    scenes.append({"say": "Follow for the day's money news in under a minute.", "photo": "newspaper",
                   "big": "Follow", "sub": "daily money news"})
    return {"id": sid, "title": f"{head} (today's money news)"[:88], "thumb": f"*TODAY:* {head[:40]}",
            "thumb_photo": q, "thumb_tag": "NEWS", "caption": "\n".join([fact, stat, why]).strip(),
            "comment": "Good news or bad news for your money? 👇",
            "tags": ["#news", "#finance", "#stockmarket", "#money", "#economy", "#breaking"],
            "sources": [re.sub(r"[📍📰✅🏛️]", "", src).replace(" ·", ",").strip(" ,") or "FinanceHubW news desk (multi-source check)"],
            "scenes": scenes}


def main() -> None:
    p = pick()
    if not p:
        print("news short: no strong story today"); return
    spec = script(p)
    path = SCRIPTS / f"{spec['id']}.json"
    if path.exists():
        print("news short: already made today"); return
    path.write_text(json.dumps(spec, indent=1, ensure_ascii=False), encoding="utf-8")
    print("news short:", spec["title"])
    subprocess.run([sys.executable, str(ROOT / "social" / "shorts_factory.py"), spec["id"]], check=True)
    q = json.loads(QUEUE.read_text(encoding="utf-8"))
    me = [i for i in q["items"] if i["file"] == f"{spec['id']}.mp4"]
    rest = [i for i in q["items"] if i["file"] != f"{spec['id']}.mp4"]
    posted = {x["file"] for x in json.loads((ROOT / "social" / "posted.json").read_text())["posted"]}
    k = next((n for n, i in enumerate(rest) if i["file"] not in posted), len(rest))
    q["items"] = rest[:k] + me + rest[k:]          # first among the Shorts still waiting
    QUEUE.write_text(json.dumps(q, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
