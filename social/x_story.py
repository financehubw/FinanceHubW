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
    ph = photo_for(post)
    if ph is not None:   # topic photo in the top band, fading into the dark page
        import photos
        band = int(H * (0.40 if H > 1500 else 0.34))
        pic = photos.cover_fit(ph, W, band)
        from PIL import ImageEnhance
        pic = ImageEnhance.Brightness(pic).enhance(0.75)
        mask = Image.new("L", (1, band))
        for yy in range(band):
            t = yy / band
            mask.putpixel((0, yy), int(255 * (1 - max(0, (t - 0.45) / 0.55)) ** 1.4 * (0.55 + 0.45 * min(1, t / 0.25))))
        img.paste(pic, (0, 0), mask.resize((W, band)))
        scrim = Image.new("L", (1, 300))
        for yy in range(300):
            scrim.putpixel((0, yy), int(170 * (1 - yy / 300) ** 1.5))
        img.paste(Image.new("RGB", (W, 300), BG), (0, 0), scrim.resize((W, 300)))
        top = band - (70 if H > 1500 else 40)
        if ph.info.get("credit"):
            cf = font("archivo-latin-600-normal.ttf", 18)
            ImageDraw.Draw(img).text((W - 40, 28), ph.info["credit"][:70], font=cf, fill=(200, 196, 188), anchor="ra")
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


_PHOTOS: dict = {}


def photo_for(post: dict):
    """Cached per post so the Story and the briefing slide use the same picture."""
    if os.environ.get("NO_PHOTOS"):
        return None
    if post["id"] not in _PHOTOS:
        try:
            import photos
            _PHOTOS[post["id"]] = photos.photo(post["text"], post["id"])
        except Exception as e:  # noqa: BLE001
            print("photo:", e); _PHOTOS[post["id"]] = None
    return _PHOTOS[post["id"]]


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

    render_digest()
    cutoff = time.time() - KEEP_DAYS * 86400
    for f in [*DIR.glob("*.jpg"), *FEED_DIR.glob("*.jpg"), *DIGEST_DIR.glob("*/*")]:
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


TOPIC_TAGS = [
    (r"\b(rbi|sebi|sensex|nifty|rupee|india)\b", ["#india", "#rbi", "#sensex", "#indianeconomy"]),
    (r"\b(fed|federal reserve|powell|wall street|s&p|nasdaq|dow|treasury)\b", ["#federalreserve", "#wallstreet", "#stocks"]),
    (r"\b(ecb|esma|euro|eurozone|europe|eu)\b", ["#ecb", "#europe", "#eurozone"]),
    (r"\b(bitcoin|crypto|ethereum|btc|eth|stablecoin)\b", ["#crypto", "#bitcoin", "#cryptonews"]),
    (r"\b(oil|opec|crude|gold|silver|commodit)", ["#oil", "#gold", "#commodities"]),
    (r"\b(inflation|cpi|rate|rates|repo|interest)\b", ["#interestrates", "#inflation"]),
    (r"\b(earnings|revenue|profit|ipo|shares)\b", ["#earnings", "#stockmarket"]),
]


def caption(p: dict) -> str:
    """Grid caption tuned for Explore: the headline as the hook (first 125 characters show before
    "more"), the facts in plain words, a question for comments, a save/send prompt (the strongest
    reach signals), keywords written out, and 5 hashtags matched to the story's topic."""
    import re
    lines = [ln.strip() for ln in p["text"].split("\n") if ln.strip() and not ln.strip().startswith("http")]
    head, body = (lines[0] if lines else ""), lines[1:]
    head = re.sub(r"^[^A-Za-z0-9$₹€£]+", "", head).replace("BREAKING:", "").strip()
    hook = head   # kept in capitals: acronyms (RBI, ECB, SEC) stay right and it reads as a headline
    low = p["text"].lower()
    tags = []
    for pat, t in TOPIC_TAGS:
        if re.search(pat, low):
            tags += [x for x in t if x not in tags]
    tags = (tags + [t for t in ["#financenews", "#markets", "#economy", "#investing", "#money"] if t not in tags])[:5]
    q = "Good news or bad news for your money? Tell us 👇\n👉 Swipe for the full story."
    return (f"🚨 {hook}\n\n" + "\n".join(body) + f"\n\n{q}\n"
            "💾 Save this and send it to someone who follows the markets.\n\n"
            "Follow @financehubw for fact-checked finance news every day.\n"
            "Information only, not investment advice.\n\n" + " ".join(tags))


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


DIGEST_DIR = ROOT / "site" / "media" / "digests"
DIGEST_LOG = ROOT / "social" / "digests_posted.json"
EDITIONS = [("Morning", 3, 30), ("Evening", 12, 30)]   # UTC: 9:00 AM and 6:00 PM IST


def _head(p: dict) -> str:
    import re
    first = next((ln for ln in p["text"].split("\n") if ln.strip()), "")
    return re.sub(r"^[^A-Za-z0-9$₹€£]+", "", first).replace("BREAKING:", "").strip()


def _region(p: dict) -> str:
    import re
    m = re.search(r"📍\s*([^·\n]+)", p["text"])
    return m.group(1).strip() if m else ""


def briefing_cover(stories: list[dict], out: Path, edition: str, when: dt.datetime) -> None:
    """Cover in the same look as the Story cards: dark paper, coral accents, Archivo."""
    W2, H2 = 1080, 1350
    img = Image.new("RGB", (W2, H2), BG)
    ph = photo_for(stories[0]) if stories else None
    if ph is not None:   # lead story's photo behind the date, fading into the page
        import photos
        from PIL import ImageEnhance
        band = 500
        pic = ImageEnhance.Brightness(photos.cover_fit(ph, W2, band)).enhance(0.55)
        mask = Image.new("L", (1, band))
        for yy in range(band):
            mask.putpixel((0, yy), int(255 * max(0.0, 1 - max(0, (yy / band - 0.4) / 0.6)) ** 1.3))
        img.paste(pic, (0, 0), mask.resize((W2, band)))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W2, 14], fill=CORAL)
    icon = ROOT / "brand" / "financehubw-icon.png"
    if icon.exists():
        m = Image.open(icon).convert("RGBA"); m.thumbnail((92, 92))
        img.paste(m, (90, 80), m)
    d.text((200, 92), "FinanceHubW", font=font("archivo-latin-800-normal.ttf", 44), fill=INK)
    d.text((200, 146), f"{edition.upper()} BRIEFING", font=font("archivo-latin-600-normal.ttf", 28), fill=CORAL)
    big = font("archivo-latin-800-normal.ttf", 210)
    day = when.strftime("%-d")
    d.text((84, 225), day, font=big, fill=INK)
    x = 84 + d.textlength(day, font=big) + 36
    d.text((x, 262), when.strftime("%B").upper(), font=font("archivo-latin-800-normal.ttf", 64), fill=INK)
    d.text((x, 340), f"{when:%A}  ·  {len(stories)} stories".upper(), font=font("archivo-latin-600-normal.ttf", 30), fill=MUTED)
    d.rectangle([90, 470, 210, 478], fill=CORAL)
    d.text((90, 505), "IN THIS ISSUE", font=font("archivo-latin-800-normal.ttf", 30), fill=CORAL)
    n = len(stories)
    hs = 32 if n <= 6 else 28
    hf, nf = font("archivo-latin-800-normal.ttf", hs), font("archivo-latin-800-normal.ttf", hs)
    rf = font("archivo-latin-600-normal.ttf", 22)
    y, step = 565, (H2 - 300 - 565) // max(n, 1)
    for i, p in enumerate(stories, 1):
        h = _head(p)
        while d.textlength(h, font=hf) > W2 - 260 and " " in h:
            h = h.rsplit(" ", 1)[0].rstrip(",:;") + "…"
        d.text((90, y), f"{i:02d}", font=nf, fill=CORAL)
        d.text((160, y), h, font=hf, fill=INK)
        d.text((160, y + hs + 6), _region(p).upper(), font=rf, fill=MUTED)
        y += step
    d.rectangle([90, H2 - 230, W2 - 90, H2 - 228], fill=(60, 57, 52))
    sf = font("archivo-latin-800-normal.ttf", 38)
    d.text((90, H2 - 190), "Swipe for every story", font=sf, fill=INK)
    ax = 90 + d.textlength("Swipe for every story", font=sf) + 24
    d.line([(ax, H2 - 167), (ax + 64, H2 - 167)], fill=CORAL, width=6)
    d.polygon([(ax + 64, H2 - 180), (ax + 86, H2 - 167), (ax + 64, H2 - 154)], fill=CORAL)
    d.text((90, H2 - 120), "Fact-checked by multiple sources. Information only, not investment advice.",
           font=font("archivo-latin-600-normal.ttf", 24), fill=MUTED)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=92)


def briefing_end(out: Path) -> None:
    W2, H2 = 1080, 1350
    img = Image.new("RGB", (W2, H2), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W2, 14], fill=CORAL)
    y = 420
    for ln, col in (("Markets move", INK), ("every hour.", INK), ("Stay ahead.", CORAL)):
        d.text((90, y), ln, font=font("archivo-latin-800-normal.ttf", 100), fill=col); y += 112
    d.rectangle([90, y + 40, 210, y + 48], fill=CORAL)
    y += 100
    d.text((90, y), "Follow @financehubw", font=font("archivo-latin-800-normal.ttf", 46), fill=INK)
    for i, ln in enumerate(["Fact-checked finance news every day", "Daily brief Tue–Sat · Magazine every Saturday"]):
        d.text((90, y + 70 + i * 56), ln, font=font("archivo-latin-600-normal.ttf", 36), fill=MUTED)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=92)


def digest_due() -> tuple[str, dt.datetime] | None:
    now = dt.datetime.utcnow()
    log = load(DIGEST_LOG, {"posted": []})
    done = {e["key"] for e in log["posted"]}
    for name, hh, mm in reversed(EDITIONS):
        start = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if now >= start and now - start < dt.timedelta(hours=6):
            key = f"{now:%Y-%m-%d}-{name.lower()}"
            return None if key in done else (key, now)
    return None


def digest_stories() -> list[dict]:
    log = load(DIGEST_LOG, {"posted": []})
    used = {i for e in log["posted"] for i in e.get("ids", [])}
    now = dt.datetime.utcnow()
    posts = [p for p in load(FEED, {"posts": []})["posts"]
             if "📍" in p["text"] and p["id"] not in used
             and now - dt.datetime.strptime(p["date"], "%Y-%m-%dT%H:%M:%SZ") < dt.timedelta(hours=14)]
    score = lambda p: ("BREAKING" in p["text"]) * 3 + ("✅" in p["text"]) * 2 + ("Official" in p["text"]) + ("📊" in p["text"])
    top = sorted(posts, key=score, reverse=True)[:8]
    return sorted(top, key=lambda p: p["date"], reverse=True)


def render_digest() -> None:
    """Draw the briefing carousel before the commit, so the site serves it when feed() posts it."""
    due = digest_due()
    if not due:
        return
    key, now = due
    stories = digest_stories()
    if len(stories) < 3:
        print(f"digest {key}: only {len(stories)} new stories, waiting"); return
    folder = DIGEST_DIR / key
    if (folder / "manifest.json").exists():
        return
    edition = key.rsplit("-", 1)[1].title()
    briefing_cover(stories, folder / "00.jpg", edition, now)
    for i, p in enumerate(stories, 1):
        card(p, folder / f"{i:02d}.jpg", 1080, 1350)
    briefing_end(folder / f"{len(stories) + 1:02d}.jpg")
    (folder / "manifest.json").write_text(json.dumps({"key": key, "edition": edition,
        "ids": [p["id"] for p in stories], "slides": len(stories) + 2}), encoding="utf-8")
    print(f"digest {key}: {len(stories)} stories drawn")


def digest_caption(m: dict, stories: list[dict]) -> str:
    import re
    heads = []
    for i, p in enumerate(stories, 1):
        h = re.sub(r"^[^A-Za-z0-9$₹€£]+", "", p["text"].split("\n")[0]).replace("BREAKING:", "").strip()
        heads.append(f"{i:02d} {h}")
    tags = []
    for pat, t in TOPIC_TAGS:
        if any(re.search(pat, p["text"].lower()) for p in stories):
            tags += [x for x in t[:1] if x not in tags]
    tags = (tags + ["#financenews", "#markets", "#economy", "#stockmarket", "#investing"])[:5]
    return (f"🗞️ {m['edition']} briefing: {len(stories)} finance stories you need to know today\n\n"
            + "\n".join(heads) +
            "\n\nWhich one matters most to you? Tell us 👇\n"
            "💾 Save this and send it to someone who follows the markets.\n\n"
            "Follow @financehubw for fact-checked finance news every day.\n"
            "Information only, not investment advice.\n\n" + " ".join(dict.fromkeys(tags)))


def feed() -> None:
    """Post the drawn briefing as a carousel: cover with date + contents, one slide per story, follow slide."""
    ig, tok = os.environ.get("IG_USER_ID"), os.environ.get("META_TOKEN")
    log = load(DIGEST_LOG, {"posted": []})
    done = {e["key"] for e in log["posted"]}
    pending = [json.loads(m.read_text()) for m in sorted(DIGEST_DIR.glob("*/manifest.json"))]
    pending = [m for m in pending if m["key"] not in done]
    if not pending:
        print("briefing: nothing to post"); return
    m = pending[-1]
    feedposts = {p["id"]: p for p in load(FEED, {"posts": []})["posts"]}
    stories = [feedposts[i] for i in m["ids"] if i in feedposts]
    urls = [f"{SITE_URL}/media/digests/{m['key']}/{n:02d}.jpg" for n in range(m["slides"])]
    if os.environ.get("DRY_RUN") or not (ig and tok):
        print("briefing ready:", m["key"]); return
    if not all(wait_live(u) for u in urls):
        print("briefing slides not live yet"); return
    try:
        kids = []
        for u in urls:
            k = requests.post(f"{GRAPH}/{ig}/media", timeout=60, data={
                "image_url": u, "is_carousel_item": "true", "access_token": tok}).json()
            if "id" not in k:
                raise RuntimeError(k.get("error", k))
            kids.append(k["id"])
        c = requests.post(f"{GRAPH}/{ig}/media", timeout=60, data={
            "media_type": "CAROUSEL", "children": ",".join(kids),
            "caption": digest_caption(m, stories), "access_token": tok}).json()
        if "id" not in c:
            raise RuntimeError(c.get("error", c))
        for _ in range(12):
            st = requests.get(f"{GRAPH}/{c['id']}", timeout=30, params={"fields": "status_code", "access_token": tok}).json()
            if st.get("status_code") in ("FINISHED", None):
                break
            time.sleep(5)
        r = requests.post(f"{GRAPH}/{ig}/media_publish", timeout=60,
                          data={"creation_id": c["id"], "access_token": tok}).json()
        if "id" not in r:
            raise RuntimeError(r.get("error", r))
        print("briefing posted:", r["id"])
        log["posted"] = (log["posted"] + [{"key": m["key"], "ids": m["ids"], "ig": r["id"], "t": time.time()}])[-120:]
        DIGEST_LOG.write_text(json.dumps(log, indent=1), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"briefing failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    {"render": render, "post": post, "feed": feed}[sys.argv[1]]()
