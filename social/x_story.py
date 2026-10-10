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


def card(post: dict, out: Path) -> None:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 14], fill=CORAL)
    icon = ROOT / "brand" / "financehubw-icon.png"
    if icon.exists():
        m = Image.open(icon).convert("RGBA"); m.thumbnail((92, 92))
        img.paste(m, (90, 170), m)
    d.text((200, 182), "FinanceHubW", font=font("archivo-latin-800-normal.ttf", 44), fill=INK)
    d.text((200, 236), "LIVE FROM X", font=font("archivo-latin-600-normal.ttf", 28), fill=CORAL)
    text = post["text"].split("\n\nhttp")[0].strip()
    text = " ".join(w for w in text.split(" ") if not w.startswith("http")) if "http" in text else text
    for size in (64, 58, 52, 46, 40, 36):
        f = font("archivo-latin-600-normal.ttf", size)
        lines = wrap(d, text, f, W - 180)
        if len(lines) * size * 1.32 < 1050:
            break
    y = 420
    d.text((90, y - 10), "“", font=font("fraunces-latin-900-normal.ttf", 160), fill=CORAL)
    y += 130
    for ln in lines:
        d.text((90, y), ln, font=f, fill=INK)
        y += int(size * 1.32)
    when = dt.datetime.strptime(post["date"], "%Y-%m-%dT%H:%M:%SZ").strftime("%-d %b %Y, %H:%M UTC")
    d.text((90, H - 330), when, font=font("archivo-latin-600-normal.ttf", 30), fill=MUTED)
    d.rectangle([90, H - 260, W - 90, H - 258], fill=(60, 57, 52))
    d.text((90, H - 225), "Follow @FinanceHubW on X for live updates",
           font=font("archivo-latin-600-normal.ttf", 34), fill=INK)
    d.text((90, H - 175), "Information only, not investment advice.",
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
    cutoff = time.time() - KEEP_DAYS * 86400
    for f in DIR.glob("*.jpg"):
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
        for _ in range(36):
            try:
                r = requests.head(url, timeout=20)
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


if __name__ == "__main__":
    {"render": render, "post": post}[sys.argv[1]]()
