"""
Posts the magazine to Instagram as carousel posts: The Weekly (one issue a week) and
The Daily (one short edition per market day).

A Weekly issue is ready when its slides exist as site/media/magazine/issue-NN/01.jpg ... and it
has an entry in social/magazine_queue.json. A Daily edition is ready when its slides exist as
site/media/daily/YYYY-MM-DD/01.jpg ... and it has an entry in social/daily_queue.json. The
slides are served from the website, which gives Instagram a public URL to fetch each image
from, so the site must have redeployed first (this script waits for that).

Each run posts every edition that is ready and not yet posted, oldest first. A Daily that is
more than three days old is skipped as stale instead of being posted late.

Secrets (the same ones social/publish.py uses):
  META_TOKEN   long-lived token with instagram_content_publish
  IG_USER_ID   Instagram Business/Creator account id
Variables:
  SITE_URL     defaults to https://financehubw-site.vercel.app
  DRY_RUN=1    print what would be posted, post nothing

Instagram allows up to 20 slides in a carousel. If the account or API version only accepts 10,
the script retries with the issue's "short" list (ten slide numbers that still tell the story).
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "social" / "magazine_queue.json"
DAILY_QUEUE = ROOT / "social" / "daily_queue.json"
POSTED = ROOT / "social" / "magazine_posted.json"
MEDIA = ROOT / "site" / "media"
DAILY_MAX_AGE_DAYS = 0   # a Daily is posted on its own day or not at all (no late, out-of-order editions)
SITE_URL = (os.environ.get("SITE_URL") or "https://financehubw-site.vercel.app").rstrip("/")
GRAPH = "https://graph.facebook.com/v21.0"
CAPTION_LIMIT = 2200          # Instagram's caption limit
WAIT_FOR_SITE_SECONDS = 900   # how long to wait for the website to redeploy with the slides


def load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def numbers_in(folder: str) -> list[int]:
    return sorted(int(p.stem) for p in (MEDIA / folder).glob("[0-9][0-9].jpg"))


def pending() -> list[dict]:
    """Every edition that has slides and is not posted yet, oldest first."""
    log = load(POSTED, {"posted": []})["posted"]
    done = {p.get("key") or f"weekly-{int(p['issue']):02d}" for p in log}
    items = []
    for d in load(DAILY_QUEUE, {"editions": []})["editions"]:
        day = datetime.date.fromisoformat(d["date"])
        if (datetime.date.today() - day).days > DAILY_MAX_AGE_DAYS:
            continue
        items.append({"key": f"daily-{d['date']}", "folder": f"daily/{d['date']}", "sort": d["date"] + "a",
                      "title": d["title"], "caption": d["caption"], "short": d.get("short", [])})
    for w in load(QUEUE, {"issues": []})["issues"]:
        n = int(w["issue"])
        items.append({"key": f"weekly-{n:02d}", "folder": f"magazine/issue-{n:02d}",
                      "sort": w.get("date", "0000-00-00") + "b", "title": w["title"],
                      "caption": w["caption"], "short": w.get("short", [])})
    return sorted((i for i in items if i["key"] not in done and numbers_in(i["folder"])),
                  key=lambda i: i["sort"])


def url_for(folder: str, n: int) -> str:
    return f"{SITE_URL}/media/{folder}/{n:02d}.jpg"


def wait_until_live(urls: list[str]) -> None:
    deadline = time.time() + WAIT_FOR_SITE_SECONDS
    pending = list(urls)
    while pending:
        still = []
        for u in pending:
            try:
                r = requests.head(u, timeout=30, allow_redirects=True)
                ok = r.ok and "image" in r.headers.get("content-type", "")
            except requests.RequestException:
                ok = False
            if not ok:
                still.append(u)
        pending = still
        if pending:
            if time.time() > deadline:
                sys.exit(f"{len(pending)} slide(s) are not reachable yet, e.g. {pending[0]} "
                         "(has the website redeployed?)")
            time.sleep(20)


def graph_post(path: str, data: dict) -> dict:
    r = requests.post(f"{GRAPH}/{path}", timeout=60, data=data).json()
    if "id" not in r:
        raise RuntimeError(str(r.get("error", r)))
    return r


def post_carousel(item: dict, numbers: list[int]) -> str:
    ig, tok = os.environ["IG_USER_ID"], os.environ["META_TOKEN"]
    children = {}
    for n in numbers:
        children[n] = graph_post(f"{ig}/media", {"image_url": url_for(item["folder"], n),
                                                 "is_carousel_item": "true", "access_token": tok})["id"]
        time.sleep(1)

    def publish(ns: list[int]) -> str:
        parent = graph_post(f"{ig}/media", {"media_type": "CAROUSEL",
                                            "children": ",".join(children[n] for n in ns),
                                            "caption": item["caption"][:CAPTION_LIMIT],
                                            "access_token": tok})["id"]
        for _ in range(30):
            st = requests.get(f"{GRAPH}/{parent}", timeout=30,
                              params={"fields": "status_code", "access_token": tok}).json()
            if st.get("status_code") in ("FINISHED", None):
                break
            if st.get("status_code") == "ERROR":
                raise RuntimeError("Instagram could not process the carousel")
            time.sleep(5)
        return graph_post(f"{ig}/media_publish", {"creation_id": parent, "access_token": tok})["id"]

    try:
        return publish(numbers)
    except RuntimeError as e:
        if len(numbers) <= 10:
            raise
        short = [n for n in item.get("short", []) if n in children][:10] or numbers[:9] + numbers[-1:]
        print(f"  full carousel refused ({e}); retrying with {len(short)} slides: {short}", file=sys.stderr)
        return publish(short)


def post_story(item: dict) -> str:
    """The Daily's cover as an Instagram Story (Instagram letterboxes the 4:5 slide)."""
    ig, tok = os.environ["IG_USER_ID"], os.environ["META_TOKEN"]
    c = graph_post(f"{ig}/media", {"media_type": "STORIES", "image_url": url_for(item["folder"], 1),
                                   "access_token": tok})["id"]
    for _ in range(20):
        st = requests.get(f"{GRAPH}/{c}", timeout=30, params={"fields": "status_code", "access_token": tok}).json()
        if st.get("status_code") in ("FINISHED", None):
            break
        time.sleep(3)
    return graph_post(f"{ig}/media_publish", {"creation_id": c, "access_token": tok})["id"]


def post_news_short(item: dict) -> str:
    """The Daily as a vertical news Short on YouTube."""
    sys.path.insert(0, str(ROOT / "social"))
    from daily_short import build
    from publish import post_youtube
    date = item["key"].removeprefix("daily-")
    path = build(date)
    first = item["caption"].split("\n")[0]
    return post_youtube({"title": f"The Daily, {item['title']}", "ai_voice": False,
                         "caption": first + "\n\nEvery slide from today's edition: Instagram @financehubw",
                         "tags": ["#finance", "#news", "#economy", "#markets", "#shorts"]}, path)


def main() -> None:
    items = pending()
    if not items:
        print("nothing to post: every queued edition is already posted, stale, or missing its slides")
        return
    failed = 0
    for item in items:
        numbers = numbers_in(item["folder"])[:20]
        urls = [url_for(item["folder"], n) for n in numbers]
        print(f"next: {item['key']} {item['title']} ({len(numbers)} slides)\n  first: {urls[0]}")
        print("--- caption\n" + item["caption"][:CAPTION_LIMIT])
        if len(item["caption"]) > CAPTION_LIMIT:
            print(f"note: caption is {len(item['caption'])} characters and will be cut at {CAPTION_LIMIT}")
        if os.environ.get("DRY_RUN"):
            print("DRY_RUN: nothing posted")
            continue
        if not (os.environ.get("IG_USER_ID") and os.environ.get("META_TOKEN")):
            print("IG_USER_ID / META_TOKEN secrets are not set yet, nothing to do")
            return
        wait_until_live(urls)
        try:
            media_id = post_carousel(item, numbers)
        except Exception as e:  # noqa: BLE001  one edition failing must not stop the next
            failed += 1
            print(f"  {item['key']}: FAILED - {e}", file=sys.stderr)
            continue
        print(f"  Instagram: posted {media_id}")
        entry = {"key": item["key"], "title": item["title"],
                 "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "instagram": media_id}
        if item["key"].startswith("daily-"):
            try:
                entry["story"] = post_story(item)
                print(f"  Story: posted {entry['story']}")
            except Exception as e:  # noqa: BLE001
                print(f"  Story: FAILED - {e}", file=sys.stderr)
            # YouTube carries only the hand-made Shorts (quality over volume). Set NEWS_SHORTS=1 to re-enable.
            if os.environ.get("NEWS_SHORTS") == "1" and os.environ.get("YT_TOKEN_JSON"):
                try:
                    entry["youtube"] = post_news_short(item)
                    print(f"  YouTube news Short: {entry['youtube']}")
                except Exception as e:  # noqa: BLE001
                    print(f"  YouTube news Short: FAILED - {e}", file=sys.stderr)
        log = load(POSTED, {"posted": []})
        log["posted"].append(entry)
        POSTED.write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
    if failed:
        sys.exit(f"{failed} edition(s) failed")


if __name__ == "__main__":
    main()
