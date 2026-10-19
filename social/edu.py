"""Save-worthy educational carousels (Mon/Wed/Fri) for Instagram and the Facebook Page.

Carousels people save and send are what Instagram pushes to new accounts, and they turn
profile visits into follows. Same look as the briefings. Text by the free models, kept to
evergreen basics (no prices, no predictions, no advice to buy anything).

    python social/edu.py          make the next topic and post it
    DRY_RUN=1 python social/edu.py   draw only
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import requests
from PIL import Image, ImageDraw

import x_story as xs

ROOT = xs.ROOT
OUT = ROOT / "site" / "media" / "edu"
LOG = ROOT / "social" / "edu_posted.json"

TOPICS = [
    ("compound-interest", "How compound interest turns small money into big money", "piggy bank"),
    ("money-mistakes-20s", "7 money mistakes people make in their 20s", "young people city"),
    ("sip-explained", "SIP explained in 60 seconds: how monthly investing works", "calendar coins"),
    ("emergency-fund", "How to build an emergency fund, step by step", "savings jar"),
    ("index-funds", "Index funds explained: why most experts recommend them", "stock market screen"),
    ("credit-score", "6 habits that build a great credit score", "credit card"),
    ("rule-of-72", "The Rule of 72: how fast your money doubles", "calculator"),
    ("inflation", "What inflation really does to your savings", "supermarket prices"),
    ("50-30-20", "The 50/30/20 budget rule, explained simply", "notebook budget"),
    ("stocks-vs-bonds", "Stocks vs bonds: the difference in plain English", "finance newspaper"),
    ("dollar-cost-averaging", "Dollar-cost averaging: why timing the market is overrated", "chart growth"),
    ("bull-bear", "Bull vs bear market: what the words actually mean", "bull statue"),
    ("pe-ratio", "The P/E ratio explained without the jargon", "stock analysis"),
    ("diversification", "Diversification: why you never put all your eggs in one basket", "eggs basket"),
    ("credit-card-traps", "5 credit card traps banks hope you fall for", "credit card"),
    ("dividends", "How dividends work, and how people live off them", "coins stack"),
    ("market-cap", "Market cap explained: how a company's value is measured", "skyscrapers"),
    ("ipo", "What happens in an IPO, explained simply", "stock exchange"),
    ("crypto-basics", "Crypto basics: what a blockchain actually is", "bitcoin"),
    ("interest-rates", "Why central bank interest rates move every market", "central bank building"),
    ("recession", "What a recession is, and what usually happens in one", "empty street"),
    ("etf", "ETFs explained: a basket of stocks in one click", "stock market screen"),
    ("money-habits-rich", "6 money habits wealthy people share", "luxury watch"),
    ("lifestyle-inflation", "Lifestyle inflation: the silent wealth killer", "shopping bags"),
    ("fees", "How a 1% fee can quietly eat a third of your returns", "receipt"),
    ("short-selling", "Short selling explained: betting a stock will fall", "red chart"),
]


def write_content(title: str) -> dict:
    from xbot.verify import write
    prompt = (
        f'Write an Instagram educational carousel titled "{title}" for a finance education account.\n'
        "Return ONLY JSON: {\"hook\": \"<cover line, max 8 words, curiosity>\", "
        "\"slides\": [{\"head\": \"<max 6 words>\", \"body\": \"<max 32 words, plain English>\"}], "
        "\"takeaway\": \"<one line, max 14 words>\", \"question\": \"<question for comments>\"}\n"
        "Use 6 slides. Evergreen, accurate basics only: no current prices, no predictions, "
        "no product or stock recommendations, no made-up statistics. Simple words a teenager understands.")
    for _ in range(3):
        text, _model = write(prompt)
        m = re.search(r"\{.*\}", text, re.S)
        try:
            j = json.loads(m.group(0))
            if len(j.get("slides", [])) >= 5:
                j["slides"] = j["slides"][:7]
                return j
        except Exception:  # noqa: BLE001
            pass
    raise RuntimeError("no usable carousel text")


W2, H2 = 1080, 1350


def _base():
    img = Image.new("RGB", (W2, H2), xs.BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W2, 14], fill=xs.CORAL)
    d.text((90, H2 - 90), "@financehubw", font=xs.font("archivo-latin-600-normal.ttf", 28), fill=xs.MUTED)
    return img, d


def cover(c: dict, title: str, photo_q: str, out: Path):
    img, d = _base()
    try:
        import photos
        from PIL import ImageEnhance
        ph = photos.photo(title, title, query=photo_q)
        if ph is not None:
            band = 620
            pic = ImageEnhance.Brightness(photos.cover_fit(ph, W2, band)).enhance(0.55)
            mask = Image.new("L", (1, band))
            for yy in range(band):
                mask.putpixel((0, yy), int(255 * max(0.0, 1 - max(0, (yy / band - 0.45) / 0.55)) ** 1.3))
            img.paste(pic, (0, 14), mask.resize((W2, band)))
            d = ImageDraw.Draw(img)
    except Exception as e:  # noqa: BLE001
        print("photo skipped:", e)
    d.text((90, 80), "FINANCEHUBW  ·  LEARN", font=xs.font("archivo-latin-800-normal.ttf", 30), fill=xs.CORAL)
    f = xs.font("archivo-latin-800-normal.ttf", 92)
    y = 600
    for ln in xs.wrap(d, c["hook"], f, W2 - 180)[:4]:
        d.text((90, y), ln, font=f, fill=xs.INK); y += 104
    d.rectangle([90, y + 30, 210, y + 38], fill=xs.CORAL)
    sf = xs.font("archivo-latin-600-normal.ttf", 36)
    for ln in xs.wrap(d, title, sf, W2 - 180)[:3]:
        d.text((90, y + 70), ln, font=sf, fill=xs.MUTED); y += 46
    d.text((W2 - 340, H2 - 90), "SWIPE  >>", font=xs.font("archivo-latin-800-normal.ttf", 34), fill=xs.CORAL)
    img.save(out, quality=92)


def slide(i: int, n: int, s: dict, out: Path, photo_q: str = ""):
    img, d = _base()
    try:   # topic photo along the bottom of every slide
        import photos
        from PIL import ImageEnhance
        ph = photos.photo(s["head"], f"{photo_q}-{i}", query=photo_q) if photo_q else None
        if ph is not None:
            band = 300
            pic = ImageEnhance.Brightness(photos.cover_fit(ph, W2, band)).enhance(0.6)
            mask = Image.new("L", (1, band))
            for yy in range(band):
                mask.putpixel((0, yy), int(255 * min(1.0, yy / (band * 0.6)) ** 1.4))
            img.paste(pic, (0, H2 - band), mask.resize((W2, band)))
            d = ImageDraw.Draw(img)
            d.text((90, H2 - 90), "@financehubw", font=xs.font("archivo-latin-600-normal.ttf", 28), fill=xs.INK)
    except Exception as e:  # noqa: BLE001
        print("photo skipped:", e)
    d.text((90, 110), f"{i:02d}", font=xs.font("archivo-latin-800-normal.ttf", 150), fill=xs.CORAL)
    d.text((W2 - 200, 140), f"{i}/{n}", font=xs.font("archivo-latin-600-normal.ttf", 30), fill=xs.MUTED)
    hf = xs.font("archivo-latin-800-normal.ttf", 70)
    y = 340
    for ln in xs.wrap(d, s["head"], hf, W2 - 180)[:3]:
        d.text((90, y), ln, font=hf, fill=xs.INK); y += 82
    d.rectangle([90, y + 30, 210, y + 38], fill=xs.CORAL)
    bf = xs.font("archivo-latin-600-normal.ttf", 44)
    y += 90
    for ln in xs.wrap(d, s["body"], bf, W2 - 180)[:7]:
        d.text((90, y), ln, font=bf, fill=xs.INK); y += 60
    img.save(out, quality=92)


def end(c: dict, out: Path):
    img, d = _base()
    d.text((90, 300), "THE TAKEAWAY", font=xs.font("archivo-latin-800-normal.ttf", 32), fill=xs.CORAL)
    f = xs.font("archivo-latin-800-normal.ttf", 72)
    y = 370
    for ln in xs.wrap(d, c["takeaway"], f, W2 - 180)[:4]:
        d.text((90, y), ln, font=f, fill=xs.INK); y += 84
    y += 80
    d.rectangle([90, y, 210, y + 8], fill=xs.CORAL)
    for k, (t, col, sz) in enumerate([("💾 Save this for later", xs.INK, 46), ("Send it to a friend who needs it", xs.MUTED, 38),
                                       ("Follow @financehubw to learn more", xs.CORAL, 46)]):
        d.text((90, y + 50 + k * 70), t.replace("💾 ", ""), font=xs.font("archivo-latin-800-normal.ttf" if sz == 46 else "archivo-latin-600-normal.ttf", sz), fill=col)
    img.save(out, quality=92)


def caption(c: dict, title: str) -> str:
    pts = "\n".join(f"{i}. {s['head']}" for i, s in enumerate(c["slides"], 1))
    return (f"{c['hook']} 👇\n\n{title}:\n{pts}\n\n{c['takeaway']}\n\n"
            f"💾 Save this so you have it when you need it, and send it to a friend.\n{c['question']}\n\n"
            "Follow @financehubw to learn money in a minute a day.\nEducational content, not financial advice.\n\n"
            "#personalfinance #moneytips #investing #financialliteracy #learnfinance")


def main():
    log = xs.load(LOG, {"posted": []})
    done = {e["key"] for e in log["posted"]}
    today = dt.date.today().isoformat()
    prev = next((e for e in log["posted"] if e.get("date") == today), None)
    if prev and prev.get("ig"):
        print("edu: already posted today"); return
    if prev:                                    # Instagram failed earlier today: retry the same topic, Instagram only
        key, title, photo_q = next(t for t in TOPICS if t[0] == prev["key"])
    else:
        todo = [t for t in TOPICS if t[0] not in done] or TOPICS      # cycle again after all topics
        key, title, photo_q = todo[0]
    c = write_content(title)
    folder = OUT / f"{key}-{int(time.time())}"
    folder.mkdir(parents=True, exist_ok=True)
    cover(c, title, photo_q, folder / "00.jpg")
    for i, s in enumerate(c["slides"], 1):
        slide(i, len(c["slides"]), s, folder / f"{i:02d}.jpg", photo_q)
    end(c, folder / f"{len(c['slides']) + 1:02d}.jpg")
    files = sorted(folder.glob("*.jpg"))
    cap = caption(c, title)
    print(cap)
    ig, tok = os.environ.get("IG_USER_ID"), os.environ.get("META_TOKEN")
    if os.environ.get("DRY_RUN") or not (ig and tok):
        print("edu drawn:", folder); return
    recent = requests.get(f"{xs.GRAPH}/{ig}/media", timeout=30, params={
        "fields": "id,caption", "limit": 15, "access_token": tok}).json().get("data", [])
    if any((r.get("caption") or "").startswith(c["hook"]) for r in recent):
        print("edu: already on Instagram"); return
    urls = [xs.fb_host(f) for f in files]                    # hosted on the Page CDN: no waiting for the site
    if not all(urls):
        raise SystemExit("edu: could not host slides")
    kids = []
    for u in urls:
        k = requests.post(f"{xs.GRAPH}/{ig}/media", timeout=60, data={
            "image_url": u, "is_carousel_item": "true", "access_token": tok}).json()
        if "id" not in k:
            raise SystemExit(f"edu: {k}")
        kids.append(k["id"])
    cc = requests.post(f"{xs.GRAPH}/{ig}/media", timeout=60, data={
        "media_type": "CAROUSEL", "children": ",".join(kids), "caption": cap, "access_token": tok}).json()
    if "id" not in cc:
        raise SystemExit(f"edu: carousel not created: {cc}")
    for _ in range(30):                       # wait until Instagram has processed every slide
        st = requests.get(f"{xs.GRAPH}/{cc['id']}", timeout=30,
                          params={"fields": "status_code", "access_token": tok}).json()
        if st.get("status_code") in ("FINISHED", None):
            break
        if st.get("status_code") == "ERROR":
            raise SystemExit(f"edu: Instagram error {st}")
        time.sleep(5)
    r = requests.post(f"{xs.GRAPH}/{ig}/media_publish", timeout=60,
                      data={"creation_id": cc["id"], "access_token": tok}).json()
    print("edu Instagram:", r)
    fb = prev.get("fb") if prev else None
    try:   # same carousel on the Facebook Page as a multi-photo post
        if fb:
            raise RuntimeError("already on Facebook")
        from publish import page_token
        page, ptok = os.environ["FB_PAGE_ID"], page_token()
        ids = []
        for f in files:
            p = requests.post(f"{xs.GRAPH}/{page}/photos", timeout=120, files={"source": (f.name, f.read_bytes(), "image/jpeg")},
                              data={"published": "false", "access_token": ptok}).json()
            ids.append(p["id"])
        data = {"message": cap, "access_token": ptok}
        for i, pid in enumerate(ids):
            data[f"attached_media[{i}]"] = json.dumps({"media_fbid": pid})
        fb = requests.post(f"{xs.GRAPH}/{page}/feed", timeout=60, data=data).json().get("id")
        print("edu Facebook:", fb)
    except Exception as e:  # noqa: BLE001
        print("edu Facebook skipped:", e)
    if prev:
        log["posted"].remove(prev)
    log["posted"].append({"key": key, "date": today, "ig": r.get("id"), "ig_error": None if r.get("id") else str(r)[:300], "fb": fb, "t": time.time()})
    LOG.write_text(json.dumps(log, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
