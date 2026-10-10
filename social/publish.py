"""
Posts the next Short from social/queue.json to YouTube Shorts, Instagram Reels and the
Facebook Page. Each platform is skipped if its secrets are missing, so you can switch
them on one at a time.

The video is served from the website (site/media/shorts/...), which gives Instagram and
Facebook a public URL to fetch it from. YouTube gets the file uploaded directly.

Secrets (GitHub → Settings → Secrets and variables → Actions):
  YT_TOKEN_JSON   from get_youtube_token.py (run once on your PC)
  META_TOKEN      long-lived token with instagram_content_publish
  IG_USER_ID      Instagram Business/Creator account id
  FB_PAGE_ID, FB_PAGE_TOKEN   optional, to also post to the Facebook Page
Variables:
  SITE_URL        defaults to https://financehubw-site.vercel.app
  DRY_RUN=1       print what would be posted, post nothing
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "social" / "queue.json"
POSTED = ROOT / "social" / "posted.json"
SHORTS = ROOT / "site" / "media" / "shorts"
SITE_URL = (os.environ.get("SITE_URL") or "https://financehubw-site.vercel.app").rstrip("/")
GRAPH = "https://graph.facebook.com/v21.0"
FOOTER = "\n\nFull breakdowns on YouTube: @FinanceHubW\nEducational content, not financial advice."
AI_NOTE = "\nNarration is AI-generated."


def load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def next_item() -> dict | None:
    done = {p["file"] for p in load(POSTED, {"posted": []})["posted"]}
    for item in load(QUEUE, {"items": []})["items"]:
        if item["file"] not in done and (SHORTS / item["file"]).exists():
            return item
    return None


def caption_for(item: dict) -> str:
    note = AI_NOTE if item.get("ai_voice", True) else ""
    return item["caption"] + FOOTER + note + "\n\n" + " ".join(item.get("tags", []))


# ---------------------------------------------------------------- YouTube
def post_youtube(item: dict, path: Path) -> str:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    creds = Credentials.from_authorized_user_info(json.loads(os.environ["YT_TOKEN_JSON"]))
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    title = item["title"][:90] + " #Shorts"
    body = {
        "snippet": {"title": title, "description": caption_for(item),
                    "tags": [t.lstrip("#") for t in item.get("tags", [])], "categoryId": "27"},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False,
                   # YouTube's altered/synthetic content disclosure (realistic AI voice)
                   "containsSyntheticMedia": bool(item.get("ai_voice", True))},
    }
    r = yt.videos().insert(part="snippet,status", body=body,
                           media_body=MediaFileUpload(str(path), resumable=True)).execute()
    return f"https://youtube.com/shorts/{r['id']}"


# ---------------------------------------------------------------- Instagram
def post_instagram(item: dict, url: str) -> str:
    ig, tok = os.environ["IG_USER_ID"], os.environ["META_TOKEN"]
    c = requests.post(f"{GRAPH}/{ig}/media", timeout=60, data={
        "media_type": "REELS", "video_url": url, "caption": caption_for(item),
        "share_to_feed": "true", "access_token": tok}).json()
    if "id" not in c:
        raise RuntimeError(f"container not created: {c.get('error', c)}")
    cid = c["id"]
    for _ in range(40):                       # Instagram processes the video first (up to ~7 min)
        st = requests.get(f"{GRAPH}/{cid}", timeout=30,
                          params={"fields": "status_code,status", "access_token": tok}).json()
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram could not process the video: {st.get('status')}")
        time.sleep(10)
    else:
        raise RuntimeError("Instagram took too long to process the video")
    r = requests.post(f"{GRAPH}/{ig}/media_publish", timeout=60,
                      data={"creation_id": cid, "access_token": tok}).json()
    if "id" not in r:
        raise RuntimeError(f"publish failed: {r.get('error', r)}")
    return r["id"]


# ---------------------------------------------------------------- Facebook Page
def post_facebook(item: dict, url: str) -> str:
    page, tok = os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"]
    r = requests.post(f"{GRAPH}/{page}/videos", timeout=120, data={
        "file_url": url, "title": item["title"], "description": caption_for(item),
        "access_token": tok}).json()
    if "id" not in r:
        raise RuntimeError(f"{r.get('error', r)}")
    return r["id"]


def video_is_live(url: str) -> bool:
    try:
        r = requests.head(url, timeout=30, allow_redirects=True)
        return r.ok and "video" in r.headers.get("content-type", "")
    except requests.RequestException:
        return False


def main() -> None:
    item = next_item()
    if not item:
        print("queue empty: add a video to site/media/shorts/ and an entry to social/queue.json")
        return
    path = SHORTS / item["file"]
    url = f"{SITE_URL}/media/shorts/{item['file']}"
    print(f"next Short: {item['title']}\n  file: {path.name} ({path.stat().st_size // 1024} KB)\n  url:  {url}")
    print("--- caption\n" + caption_for(item))

    jobs = [
        ("YouTube", "YT_TOKEN_JSON", lambda: post_youtube(item, path)),
        ("Instagram", "IG_USER_ID", lambda: post_instagram(item, url)),
        ("Facebook", "FB_PAGE_ID", lambda: post_facebook(item, url)),
    ]
    active = [(n, f) for n, env, f in jobs if os.environ.get(env)]
    print("platforms with secrets set:", ", ".join(n for n, _ in active) or "none")
    if os.environ.get("DRY_RUN"):
        print("DRY_RUN: nothing posted")
        return
    if not active:
        print("no platform secrets set yet, nothing to do")
        return
    if any(n != "YouTube" for n, _ in active) and not video_is_live(url):
        sys.exit(f"the video is not reachable at {url} yet (has the website redeployed?)")

    results, failed = {}, []
    for name, fn in active:
        try:
            results[name] = fn()
            print(f"  {name}: posted {results[name]}")
        except Exception as e:  # noqa: BLE001  one platform failing must not stop the others
            failed.append(name)
            print(f"  {name}: FAILED - {e}", file=sys.stderr)

    if results:   # mark as done only if at least one platform got it, so a total failure retries
        log = load(POSTED, {"posted": []})
        log["posted"].append({"file": item["file"], "title": item["title"],
                              "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                              "results": results, "failed": failed})
        POSTED.write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
    if failed and not results:
        sys.exit("every platform failed")


if __name__ == "__main__":
    main()
