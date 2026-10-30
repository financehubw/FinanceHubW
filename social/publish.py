"""
Posts the next Short from social/queue.json to YouTube Shorts, Instagram Reels and the
Facebook Page. Each platform is skipped if its secrets are missing, so you can switch
them on one at a time.

The video is served from the website (site/media/shorts/...), which gives Instagram and
Facebook a public URL to fetch it from. YouTube gets the file uploaded directly.

Secrets (GitHub → Settings → Secrets and variables → Actions):
  YT_TOKEN_JSON   Google OAuth token for the channel (renew: see the handbook runbook "Reconnect YouTube")
  META_TOKEN      long-lived token with instagram_content_publish
  IG_USER_ID      Instagram Business/Creator account id
  FB_PAGE_ID, FB_PAGE_TOKEN   optional, to also post to the Facebook Page
Variables:
  SITE_URL        defaults to https://financehubw-site.vercel.app
  DRY_RUN=1       print what would be posted, post nothing
"""
from __future__ import annotations

import calendar
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
AI_NOTE = "\nNarration is AI-generated."


def load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def next_item() -> dict | None:
    """First unposted Short, but not the same format twice in a row (variety keeps viewers)."""
    log = load(POSTED, {"posted": []})["posted"]
    done = {p["file"] for p in log}
    items = load(QUEUE, {"items": []})["items"]
    tags = {i["file"]: i.get("thumb_tag", "") for i in items}
    last = tags.get(log[-1]["file"], "") if log else ""
    ready = [i for i in items if i["file"] not in done and (SHORTS / i["file"]).exists()]
    if not ready:
        return None
    import datetime as _dt
    today = f"news_{_dt.datetime.utcnow():%Y%m%d}.mp4"
    news = [i for i in ready if i["file"] == today]
    if news:                       # today's news Short always goes out at the next slot, while it's fresh
        return news[0]
    ready = [i for i in ready if not i["file"].startswith("news_")]   # never post a stale news Short
    if not ready:
        return None
    for item in ready[:6]:
        if not last or item.get("thumb_tag", "") != last:
            return item
    return ready[0]


def thumb_for(item: dict) -> Path | None:
    t = SHORTS / "thumbs" / (Path(item["file"]).stem + ".jpg")
    return t if t.exists() else None


def caption_for(item: dict, platform: str = "instagram") -> str:
    """Platform-tuned text. Instagram/Facebook: hook in the first 125 characters (shown before "more"),
    a save/share prompt (saves and sends weigh most for Explore/Reels reach), the comment question and
    3-5 niche hashtags. YouTube: searchable first line, subscribe line, and 3 hashtags (YouTube shows
    the first three above the title; more than that adds nothing)."""
    note = AI_NOTE if item.get("ai_voice", True) else ""
    if item.get("voice") == "elevenlabs":
        note += " Voice: ElevenLabs."      # credit the free ElevenLabs plan asks for
    tags = item.get("tags", [])
    if platform == "youtube":
        yt_tags = ["#shorts"] + [t for t in tags if t != "#shorts"][:2]
        return (f"{item['title']}. {item['caption']}\n\n"
                "A new money breakdown every day. Subscribe so you don't miss one: @FinanceHubW\n"
                f"Educational content, not financial advice.{note}\n\n" + " ".join(yt_tags))
    q = item.get("comment", "")
    return (f"{item['title']} 👀\n\n{item['caption']}\n\n"
            "💾 Save this for later and send it to a friend who needs it.\n"
            + (f"{q}\n" if q else "") +
            f"\nFollow @financehubw for a new one every day.\nEducational content, not financial advice.{note}\n\n"
            + " ".join(tags[:5]))


# ---------------------------------------------------------------- YouTube
def post_youtube(item: dict, path: Path) -> str:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    creds = Credentials.from_authorized_user_info(json.loads(os.environ["YT_TOKEN_JSON"]))
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    title = item["title"][:90] + " #Shorts"
    try:   # never upload the same Short twice, even if the log was lost
        ch = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0]
        up = ch["contentDetails"]["relatedPlaylists"]["uploads"]
        for v in yt.playlistItems().list(part="snippet", playlistId=up, maxResults=25).execute().get("items", []):
            if v["snippet"]["title"].strip() == title.strip():
                print("  YouTube: already uploaded, skipping")
                return f"https://youtube.com/shorts/{v['snippet']['resourceId']['videoId']}"
    except Exception as e:  # noqa: BLE001
        print(f"  YouTube duplicate check skipped - {e}", file=sys.stderr)
    body = {
        "snippet": {"title": title, "description": caption_for(item, "youtube"),
                    "tags": [t.lstrip("#") for t in item.get("tags", [])], "categoryId": "27"},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False,
                   # YouTube's altered/synthetic content disclosure (realistic AI voice)
                   "containsSyntheticMedia": bool(item.get("ai_voice", True))},
    }
    r = yt.videos().insert(part="snippet,status", body=body,
                           media_body=MediaFileUpload(str(path), resumable=True)).execute()
    t = thumb_for(item)
    if t:
        try:   # needs a phone-verified channel; skipped quietly if not allowed
            yt.thumbnails().set(videoId=r["id"], media_body=MediaFileUpload(str(t), mimetype="image/jpeg")).execute()
        except Exception as e:  # noqa: BLE001
            print(f"  YouTube thumbnail skipped - {e}", file=sys.stderr)
    return f"https://youtube.com/shorts/{r['id']}"


# ---------------------------------------------------------------- Instagram
def post_instagram(item: dict, url: str) -> str:
    ig, tok = os.environ["IG_USER_ID"], os.environ["META_TOKEN"]
    try:   # never post the same Reel twice, even if the log was lost
        recent = requests.get(f"{GRAPH}/{ig}/media", timeout=30, params={
            "fields": "id,caption", "limit": 25, "access_token": tok}).json().get("data", [])
        dup = next((r for r in recent if (r.get("caption") or "").startswith(item["title"])), None)
        if dup:
            print("  Instagram: already posted, skipping")
            return dup["id"]
    except requests.RequestException:
        pass
    c = requests.post(f"{GRAPH}/{ig}/media", timeout=60, data={
        "media_type": "REELS", "video_url": url, "caption": caption_for(item),
        "share_to_feed": "true", "access_token": tok,   # in followers' Home feed and the grid (more reach)
        **({"cover_url": f"{SITE_URL}/media/shorts/thumbs/{thumb_for(item).name}"} if thumb_for(item) else {})}).json()
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
        time.sleep(20)       # Instagram sometimes reports an error after it has published: check first
        rows = requests.get(f"{GRAPH}/{ig}/media", timeout=30, params={
            "fields": "id,caption", "limit": 3, "access_token": tok}).json().get("data", [])
        live = next((x for x in rows if (x.get("caption") or "").startswith(item["title"])), None)
        if live:
            return live["id"]
        raise RuntimeError(f"publish failed: {r.get('error', r)}")
    return r["id"]


# ---------------------------------------------------------------- Facebook Page
def page_token() -> str:
    """FB_PAGE_TOKEN if set, otherwise the Page token derived from META_TOKEN."""
    if os.environ.get("FB_PAGE_TOKEN"):
        return os.environ["FB_PAGE_TOKEN"]
    r = requests.get(f"{GRAPH}/{os.environ['FB_PAGE_ID']}", timeout=30,
                     params={"fields": "access_token", "access_token": os.environ["META_TOKEN"]}).json()
    if "access_token" not in r:
        raise RuntimeError(f"no Page token: {r.get('error', r)}")
    return r["access_token"]


def post_facebook(item: dict, url: str) -> str:
    page, tok = os.environ["FB_PAGE_ID"], page_token()
    try:   # never post the same video twice on the Page
        vids = requests.get(f"{GRAPH}/{page}/videos", timeout=30, params={
            "fields": "id,title", "limit": 25, "access_token": tok}).json().get("data", [])
        dup = next((v for v in vids if (v.get("title") or "").strip() == item["title"].strip()), None)
        if dup:
            print("  Facebook: already posted, skipping")
            return dup["id"]
    except requests.RequestException:
        pass
    t = thumb_for(item)
    files = {"thumb": (t.name, t.read_bytes(), "image/jpeg")} if t else None
    r = requests.post(f"{GRAPH}/{page}/videos", timeout=180, files=files, data={
        "file_url": url, "title": item["title"], "description": caption_for(item),
        "access_token": tok}).json()
    if "id" not in r:
        raise RuntimeError(f"{r.get('error', r)}")
    return r["id"]


COMMENT_TAIL = "\nNew finance breakdown every day at 8:30 PM IST."


def post_comments(item: dict, results: dict) -> None:
    """First comment under each new post (pin it by hand: ⋮ → Pin). Never blocks posting."""
    text = item.get("comment")
    if not text:
        return
    text += COMMENT_TAIL
    for name, target in results.items():
        try:
            if name == "YouTube":
                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build
                yt = build("youtube", "v3", cache_discovery=False,
                           credentials=Credentials.from_authorized_user_info(json.loads(os.environ["YT_TOKEN_JSON"])))
                vid = target.rsplit("/", 1)[-1]
                yt.commentThreads().insert(part="snippet", body={"snippet": {"videoId": vid,
                    "topLevelComment": {"snippet": {"textOriginal": text}}}}).execute()
            else:
                tok = os.environ["META_TOKEN"] if name == "Instagram" else page_token()
                r = requests.post(f"{GRAPH}/{target}/comments", timeout=60,
                                  data={"message": text, "access_token": tok}).json()
                if "id" not in r:
                    raise RuntimeError(r.get("error", r))
            print(f"  {name}: comment posted")
        except Exception as e:  # noqa: BLE001
            print(f"  {name}: comment skipped - {e}", file=sys.stderr)


def story_teaser(item: dict) -> None:
    """Put the new Reel itself in Instagram Stories (the full video plays there), so followers who
    open Stories first see it. Instagram's API cannot add a tappable link or reshare sticker to a
    Story, so the video goes in directly; the cover image is the fallback. Never blocks posting."""
    ig, tok = os.environ.get("IG_USER_ID"), os.environ.get("META_TOKEN")
    if not (ig and tok):
        return
    url = f"{SITE_URL}/media/shorts/{item['file']}"
    try:
        c = requests.post(f"{GRAPH}/{ig}/media", timeout=60,
                          data={"media_type": "STORIES", "video_url": url, "access_token": tok}).json()
        if "id" not in c:
            raise RuntimeError(c.get("error", c))
        for _ in range(40):
            st = requests.get(f"{GRAPH}/{c['id']}", timeout=30,
                              params={"fields": "status_code", "access_token": tok}).json()
            if st.get("status_code") == "FINISHED":
                break
            if st.get("status_code") == "ERROR":
                raise RuntimeError("Instagram could not process the Story video")
            time.sleep(8)
        r = requests.post(f"{GRAPH}/{ig}/media_publish", timeout=60,
                          data={"creation_id": c["id"], "access_token": tok}).json()
        print("  Instagram Story (Reel video):", r.get("id", r))
        return
    except Exception as e:  # noqa: BLE001
        print(f"  Story video failed ({e}); sharing the cover instead", file=sys.stderr)
    t = thumb_for(item)
    if not t:
        return
    try:
        import x_story
        img = x_story.image_url(t, f"{SITE_URL}/media/shorts/thumbs/{t.name}")
        c = requests.post(f"{GRAPH}/{ig}/media", timeout=60,
                          data={"media_type": "STORIES", "image_url": img, "access_token": tok}).json()
        time.sleep(5)
        r = requests.post(f"{GRAPH}/{ig}/media_publish", timeout=60,
                          data={"creation_id": c["id"], "access_token": tok}).json()
        print("  Instagram Story (cover):", r.get("id", r))
    except Exception as e:  # noqa: BLE001
        print(f"  Story teaser skipped - {e}", file=sys.stderr)


def video_is_live(url: str) -> bool:
    try:
        r = requests.head(url, timeout=30, allow_redirects=True)
        return r.ok and "video" in r.headers.get("content-type", "")
    except requests.RequestException:
        return False


def backfill() -> None:
    """A Short posted before a platform was connected also goes to that platform (within 3 days)."""
    if os.environ.get("DRY_RUN"):
        return
    log = load(POSTED, {"posted": []})
    queue = {i["file"]: i for i in load(QUEUE, {"items": []})["items"]}
    changed = False
    for entry in log["posted"]:
        age = time.time() - calendar.timegm(time.strptime(entry["date"], "%Y-%m-%dT%H:%M:%SZ"))
        item = queue.get(entry["file"])
        if not item or age > float(os.environ.get("BACKFILL_DAYS") or 3) * 86400:
            continue
        url = f"{SITE_URL}/media/shorts/{item['file']}"
        for name, env, fn in (("Instagram", "IG_USER_ID", post_instagram), ("Facebook", "FB_PAGE_ID", post_facebook)):
            if name in entry["results"] or not os.environ.get(env):
                continue
            try:
                entry["results"][name] = fn(item, url)
                changed = True
                post_comments(item, {name: entry["results"][name]})
                print(f"  backfill {item['file']} -> {name}: {entry['results'][name]}")
            except Exception as e:  # noqa: BLE001
                print(f"  backfill {item['file']} -> {name}: FAILED - {e}", file=sys.stderr)
                entry.setdefault("errors", {})[name] = str(e)[:300]
                changed = True
    if changed:
        POSTED.write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    backfill()
    if os.environ.get("BACKFILL_ONLY"):
        return
    import ig_gate
    if os.environ.get("IG_USER_ID") and os.environ.get("META_TOKEN") and not os.environ.get("DRY_RUN"):
        m = ig_gate.wait_needed(os.environ["IG_USER_ID"], os.environ["META_TOKEN"])
        if m > 0:
            print(f"Instagram had a feed post under 2h ago; this waits {m:.0f} min (next run)"); return
    item = next_item()
    if not item:
        print("queue empty: add a video to site/media/shorts/ and an entry to social/queue.json")
        return
    path = SHORTS / item["file"]
    url = f"{SITE_URL}/media/shorts/{item['file']}"
    if not thumb_for(item) and not os.environ.get("DRY_RUN"):
        try:   # new Shorts get a cover automatically
            import thumbs
            thumbs.make(item)
        except Exception as e:  # noqa: BLE001
            print(f"  thumbnail skipped - {e}", file=sys.stderr)
    print(f"next Short: {item['title']}\n  file: {path.name} ({path.stat().st_size // 1024} KB)\n  url:  {url}")
    print("--- Instagram\n" + caption_for(item) + "\n--- YouTube\n" + caption_for(item, "youtube"))

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

    results, failed, errors = {}, [], {}
    for name, fn in active:
        try:
            results[name] = fn()
            print(f"  {name}: posted {results[name]}")
        except Exception as e:  # noqa: BLE001  one platform failing must not stop the others
            failed.append(name)
            errors[name] = str(e)[:300]
            print(f"  {name}: FAILED - {e}", file=sys.stderr)

    post_comments(item, results)
    if "Instagram" in results:
        story_teaser(item)
    if results:   # mark as done only if at least one platform got it, so a total failure retries
        log = load(POSTED, {"posted": []})
        log["posted"].append({"file": item["file"], "title": item["title"],
                              "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                              "results": results, "failed": failed, "errors": errors})
        POSTED.write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
    if failed and not results:
        sys.exit("every platform failed")


if __name__ == "__main__":
    main()
