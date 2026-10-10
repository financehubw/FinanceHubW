"""
Posts the next weekly magazine issue to Instagram as one carousel post.

An issue is ready when its slides exist as site/media/magazine/issue-NN/01.jpg ... and it has
an entry in social/magazine_queue.json. The slides are served from the website, which gives
Instagram a public URL to fetch each image from, so the site must have redeployed first
(this script waits for that).

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

import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "social" / "magazine_queue.json"
POSTED = ROOT / "social" / "magazine_posted.json"
MEDIA = ROOT / "site" / "media" / "magazine"
SITE_URL = (os.environ.get("SITE_URL") or "https://financehubw-site.vercel.app").rstrip("/")
GRAPH = "https://graph.facebook.com/v21.0"
CAPTION_LIMIT = 2200          # Instagram's caption limit
WAIT_FOR_SITE_SECONDS = 900   # how long to wait for the website to redeploy with the slides


def load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def slide_numbers(item: dict) -> list[int]:
    folder = MEDIA / f"issue-{int(item['issue']):02d}"
    return sorted(int(p.stem) for p in folder.glob("[0-9][0-9].jpg"))


def next_item() -> dict | None:
    done = {p["issue"] for p in load(POSTED, {"posted": []})["posted"]}
    for item in sorted(load(QUEUE, {"issues": []})["issues"], key=lambda i: i["issue"]):
        if item["issue"] not in done and slide_numbers(item):
            return item
    return None


def url_for(issue: int, n: int) -> str:
    return f"{SITE_URL}/media/magazine/issue-{issue:02d}/{n:02d}.jpg"


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
    issue = int(item["issue"])
    children = {}
    for n in numbers:
        children[n] = graph_post(f"{ig}/media", {"image_url": url_for(issue, n),
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


def main() -> None:
    item = next_item()
    if not item:
        print("nothing to post: every queued issue is already posted, or its slides are missing")
        return
    issue = int(item["issue"])
    numbers = slide_numbers(item)[:20]
    urls = [url_for(issue, n) for n in numbers]
    print(f"next issue: #{issue} {item['title']} ({len(numbers)} slides)\n  first: {urls[0]}")
    print("--- caption\n" + item["caption"][:CAPTION_LIMIT])
    if len(item["caption"]) > CAPTION_LIMIT:
        print(f"note: caption is {len(item['caption'])} characters and will be cut at {CAPTION_LIMIT}")
    if os.environ.get("DRY_RUN"):
        print("DRY_RUN: nothing posted")
        return
    if not (os.environ.get("IG_USER_ID") and os.environ.get("META_TOKEN")):
        print("IG_USER_ID / META_TOKEN secrets are not set yet, nothing to do")
        return
    wait_until_live(urls)
    media_id = post_carousel(item, numbers)
    print(f"  Instagram: posted {media_id}")
    log = load(POSTED, {"posted": []})
    log["posted"].append({"issue": issue, "title": item["title"],
                          "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                          "instagram": media_id})
    POSTED.write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
