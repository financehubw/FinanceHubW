"""Every post the bot publishes on X also goes out as an Instagram Story.

  python social/x_story.py render   draw a 1080x1920 card for each new X post
                                    -> site/media/stories/<tweet id>.jpg (runs before the commit)
  python social/x_story.py post     once the website serves the card, post it as a Story
                                    (runs after the push; waits up to 6 minutes for the redeploy)

Cards older than 7 days are deleted so the repo stays small. Uses META_TOKEN and IG_USER_ID.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FEED = ROOT / "site" / "tweets.json"
DIR = ROOT / "site" / "media" / "stories"
FEED_DIR = ROOT / "site" / "media" / "newsposts"      # 4:5 feed versions
FEED_LOG = ROOT / "social" / "newsposts_posted.json"
FEED_PER_DAY = int(os.environ.get("IG_NEWS_POSTS_PER_DAY") or 4)   # feed posts a day (the rest stay Stories)
LOG = ROOT / "social" / "stories_posted.json"
FONTS = ROOT / "motion" / "fonts"
SITE_URL = (os.environ.get("SITE_URL") or "https://financehubw-site.vercel.app").rstrip("/")
GRAPH = "https://graph.facebook.com/v21.0"
W, H = 1080, 1920
BG, INK, MUTED, CORAL = (20, 19, 17), (240, 236, 228), (150, 144, 135), (250, 91, 60)
KEEP_DAYS, MAX_AGE_HOURS = 7, 12


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def wrap(d: ImageDraw.ImageDraw, text: str, f, width: int) -> list[str]:
    lines = []
    for para in text.split("\n"):
        line = ""
        for word in para.split():
            t = (line + " " + word).strip()
            if d.textlength(t, font=f) <= width:
                line = t
            else:
                if line:
                    lines.append(line)
                line = word
        lines.append(line)
    return lines


def card(post: dict, out: Path, W: int = W, H: int = H) -> None:
    top = 470 if H > 1500 else 300
    fy = H - 390 if H > 1500 else H - 300   # footer block top
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 14], fill=CORAL)
    icon = ROOT / "brand" / "financehubw-icon.png"
    if icon.exists():
        m = Image.open(icon).convert("RGBA"); m.thumbnail((92, 92))
        img.paste(m, (90, 170 if H > 1500 else 80), m)
    d.text((200, 182 if H > 1500 else 92), "FinanceHubW", font=font("archivo-latin-800-normal.ttf", 44), fill=INK)
    d.text((200, 236 if H > 1500 else 146), "LIVE NEWS" if str(post.get("id", "")).startswith("web-") else "LIVE FROM X", font=font("archivo-latin-600-normal.ttf", 28), fill=CORAL)
    import re
    lines_in = [ln for ln in post["text"].split("\n") if not ln.strip().startswith("http")]
    clean = [re.sub(r"[^\u0000-\u024F\u2010-\u2027\u2030-\u205E\u20AC\u2122]", "", ln).strip(" ·") for ln in (l.replace("\u2192", " to ") for l in lines_in)]
    head = clean[0] if clean else ""
    rest = [c for c in clean[1:] if c and not c.startswith("#")]
    foot = rest.pop() if rest and ("·" in lines_in[-1] or "📍" in lines_in[-1]) else ""
    head = head.replace("BREAKING:", "").strip()
    rest = [r.replace("\u2192", "to") for r in rest]
    y = top
    if "BREAKING" in lines_in[0]:
        d.text((90, y - 70), "BREAKING", font=font("archivo-latin-800-normal.ttf", 34), fill=CORAL)
    for hs in ((84, 76, 68, 60, 54) if H > 1500 else (70, 62, 56, 50)):
        hf = font("archivo-latin-800-normal.ttf", hs)
        hl = wrap(d, head, hf, W - 180)
        if len(hl) <= (4 if H > 1500 else 3):
            break
    for ln in hl:
        d.text((90, y), ln, font=hf, fill=INK)
        y += int(hs * 1.15)
    y += 40
    d.rectangle([90, y, 210, y + 8], fill=CORAL)
    y += 60
    for bs in (44, 40, 36, 32, 28):
        bf = font("archivo-latin-600-normal.ttf", bs)
        blocks = [wrap(d, r, bf, W - 180) for r in rest]
        if sum(len(b) for b in blocks) * bs * 1.35 + len(blocks) * 28 < (fy - 40) - y:
            break
    for blk in blocks:
        for ln in blk:
            d.text((90, y), ln, font=bf, fill=(214, 208, 198))
            y += int(bs * 1.35)
        y += 28
    when = dt.datetime.strptime(post["date"], "%Y-%m-%dT%H:%M:%SZ").strftime("%-d %b %Y, %H:%M UTC")
    if foot:
        d.text((90, fy), foot[:60], font=font("archivo-latin-600-normal.ttf", 30), fill=CORAL)
    d.text((90, fy + 60), when, font=font("archivo-latin-600-normal.ttf", 30), fill=MUTED)
    d.rectangle([90, fy + 130, W - 90, fy + 132], fill=(60, 57, 52))
    d.text((90, fy + 165), "Follow @financehubw for daily finance news" if H < 1500 else "Follow @FinanceHubW on X for live updates",
           font=font("archivo-latin-600-normal.ttf", 34), fill=INK)
    d.text((90, fy + 215), "Information only, not investment advice.",
           font=font("archivo-latin-600-normal.ttf", 26), fill=MUTED)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=92)


def load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def fresh(posts: list[dict]) -> list[dict]:
    now = dt.datetime.utcnow()
    return [p for p in posts
            if now - dt.datetime.strptime(p["date"], "%Y-%m-%dT%H:%M:%SZ") < dt.timedelta(hours=MAX_AGE_HOURS)]


def render() -> None:
    done = set(load(LOG, {"posted": []})["posted"])
    for p in fresh(load(FEED, {"posts": []})["posts"]):
        out = DIR / f"{p['id']}.jpg"
        if p["id"] not in done and not out.exists():
            card(p, out)
            print("card:", out.name)
        fo = FEED_DIR / f"{p['id']}.jpg"
        if not fo.exists():
            card(p, fo, 1080, 1350)
    cutoff = time.time() - KEEP_DAYS * 86400
    for f in [*DIR.glob("*.jpg"), *FEED_DIR.glob("*.jpg")]:
        if f.stat().st_mtime < cutoff:
            f.unlink()


def post() -> None:
    ig, tok = os.environ.get("IG_USER_ID"), os.environ.get("META_TOKEN")
    log = load(LOG, {"posted": []})
    todo = [p for p in fresh(load(FEED, {"posts": []})["posts"])
            if p["id"] not in log["posted"] and (DIR / f"{p['id']}.jpg").exists()]
    if not todo:
        print("no new X posts to share as Stories"); return
    if os.environ.get("DRY_RUN") or not (ig and tok):
        print(f"{len(todo)} Story card(s) ready; not posting (dry run or Instagram not connected)"); return
    for p in todo:
        url = f"{SITE_URL}/media/stories/{p['id']}.jpg"
        for _ in range(12):
            try:
                r = requests.head(url, timeout=8)
                if r.ok and "image" in r.headers.get("content-type", ""):
                    break
            except requests.RequestException:
                pass
            time.sleep(10)
        else:
            print(f"{url} not live yet; will retry next run"); continue
        try:
            c = requests.post(f"{GRAPH}/{ig}/media", timeout=60,
                              data={"media_type": "STORIES", "image_url": url, "access_token": tok}).json()
            if "id" not in c:
                raise RuntimeError(c.get("error", c))
            time.sleep(5)
            r = requests.post(f"{GRAPH}/{ig}/media_publish", timeout=60,
                              data={"creation_id": c["id"], "access_token": tok}).json()
            if "id" not in r:
                raise RuntimeError(r.get("error", r))
            print("Story posted:", r["id"])
            log["posted"].append(p["id"])
        except Exception as e:  # noqa: BLE001
            print(f"Story for {p['id']} failed: {e}", file=sys.stderr)
    log["posted"] = log["posted"][-200:]
    LOG.write_text(json.dumps(log, indent=1), encoding="utf-8")


def caption(p: dict) -> str:
    lines = [ln for ln in p["text"].split("\n") if ln.strip() and not ln.strip().startswith("http")]
    return ("\n".join(lines) + "\n\nDaily finance news, fact-checked. Follow @financehubw\n"
            "Information only, not investment advice.\n\n#financenews #markets #economy #stockmarket #investing")


def wait_live(url: str) -> bool:
    for _ in range(12):
        try:
            r = requests.head(url, timeout=8)
            if r.ok and "image" in r.headers.get("content-type", ""):
                return True
        except requests.RequestException:
            pass
        time.sleep(10)
    return False


def feed() -> None:
    """The best news updates also go on the Instagram grid, at most FEED_PER_DAY a day, spaced out."""
    ig, tok = os.environ.get("IG_USER_ID"), os.environ.get("META_TOKEN")
    log = load(FEED_LOG, {"posted": []})
    today = [e for e in log["posted"] if time.time() - e["t"] < 86400]
    if len(today) >= FEED_PER_DAY or (today and time.time() - max(e["t"] for e in today) < 86400 / FEED_PER_DAY * 0.8):
        print("news feed post: not due yet"); return
    done = {e["id"] for e in log["posted"]}
    todo = [p for p in fresh(load(FEED, {"posts": []})["posts"]) if p["id"] not in done and (FEED_DIR / f"{p['id']}.jpg").exists()]
    if not todo:
        print("news feed post: nothing new"); return
    p = max(todo, key=lambda p: ("✅" in p["text"]) + ("BREAKING" in p["text"]) * 2 + ("Official" in p["text"]))
    if os.environ.get("DRY_RUN") or not (ig and tok):
        print("news feed post ready:", p["id"]); return
    url = f"{SITE_URL}/media/newsposts/{p['id']}.jpg"
    if not wait_live(url):
        print("feed card not live yet"); return
    try:
        c = requests.post(f"{GRAPH}/{ig}/media", timeout=60,
                          data={"image_url": url, "caption": caption(p), "access_token": tok}).json()
        if "id" not in c:
            raise RuntimeError(c.get("error", c))
        time.sleep(5)
        r = requests.post(f"{GRAPH}/{ig}/media_publish", timeout=60,
                          data={"creation_id": c["id"], "access_token": tok}).json()
        if "id" not in r:
            raise RuntimeError(r.get("error", r))
        print("news feed post:", r["id"])
        log["posted"] = (log["posted"] + [{"id": p["id"], "t": time.time(), "ig": r["id"]}])[-300:]
        FEED_LOG.write_text(json.dumps(log, indent=1), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"news feed post failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    {"render": render, "post": post, "feed": feed}[sys.argv[1]]()
