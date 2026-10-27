"""Voiced Shorts, made for free, in the style that performs best on the channel
(the "Manhattan for $24" look: cream paper, a taped photo card, a big number, word-by-word captions).

    python social/shorts_factory.py                    render every script in social/shorts_scripts/ not yet rendered
    python social/shorts_factory.py netflix_blockbuster   render one

Pieces
  voice    edge-tts (Microsoft neural voice, free, no key) with word timings for the captions
  photos   Pixabay (PIXABAY_API_KEY), magazine photo library as backup  (social/photos.py)
  music    synthesized pad from motion/sound.py (owned outright)
  numbers  live figures are computed at render time, never typed:
             {growth:NVDA:2016-01-04}   what $1,000 became (split-adjusted price only, no dividends)
             {price:BTC-USD*10000}      today's value of an amount of an asset
             {cap:AAPL*0.10}            share of a company's current market value
           Every script lists its sources in "sources"; render refuses a script without them.
Output: site/media/shorts/<id>.mp4 + an entry appended to social/queue.json (with thumbnail fields).
"""
from __future__ import annotations

import asyncio
import os
import datetime as dt
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "social"))
sys.path.insert(0, str(ROOT / "motion"))
SCRIPTS = ROOT / "social" / "shorts_scripts"
SHORTS = ROOT / "site" / "media" / "shorts"
QUEUE = ROOT / "social" / "queue.json"
FONTS = ROOT / "motion" / "fonts"
W, H, FPS = 1080, 1920, 30
PAPER, INK, MUTED, GOLD, CARD = (233, 225, 210), (24, 22, 20), (110, 102, 92), (242, 178, 51), (250, 248, 243)
VOICE = "en-US-AndrewNeural"


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


SERIF = "fraunces-latin-900-normal.ttf"
BOLD = "archivo-latin-800-normal.ttf"
SEMI = "archivo-latin-600-normal.ttf"


# ------------------------------------------------------------------ live numbers
def money(v: float) -> str:
    for n, s in ((1e12, "trillion"), (1e9, "billion"), (1e6, "million")):
        if v >= n:
            x = v / n
            return f"${x:,.0f} {s}" if x >= 100 else f"${x:,.1f} {s}".replace(".0 ", " ")
    return f"${v:,.0f}"


_cache: dict = {}


def resolve(text: str) -> str:
    import yfinance as yf

    def rep(m):
        kind, arg = m.group(1), m.group(2)
        if m.group(0) in _cache:
            return _cache[m.group(0)]
        if kind == "growth":
            tick, start = arg.split(":")
            h = yf.Ticker(tick).history(start=start, auto_adjust=False)["Close"].dropna()
            out = money(1000 * float(h.iloc[-1]) / float(h.iloc[0]))
        elif kind == "dca":
            tick, start = arg.split(":")
            h = yf.Ticker(tick).history(start=start, auto_adjust=False)["Close"].dropna()
            monthly = h.groupby([h.index.year, h.index.month]).head(1)   # first trading day of each month
            shares = sum(100 / float(px) for px in monthly)
            out = money(shares * float(h.iloc[-1]))
        elif kind == "price":
            tick, mult = arg.split("*")
            h = yf.Ticker(tick).history(period="5d")["Close"].dropna()
            out = money(float(h.iloc[-1]) * float(mult))
        elif kind == "cap":
            tick, frac = arg.split("*")
            out = money(float(yf.Ticker(tick).fast_info["market_cap"]) * float(frac))
        else:
            raise ValueError(m.group(0))
        _cache[m.group(0)] = out
        return out
    return re.sub(r"\{(growth|dca|price|cap):([^}]+)\}", rep, text)


def deep_resolve(obj):
    if isinstance(obj, str):
        return resolve(obj)
    if isinstance(obj, list):
        return [deep_resolve(x) for x in obj]
    if isinstance(obj, dict):
        return {k: deep_resolve(v) for k, v in obj.items()}
    return obj


# ------------------------------------------------------------------ animated data scenes
def series(tick: str, start: str) -> list[tuple[dt.date, float]]:
    """Monthly value of $1,000 invested at `start` (split-adjusted price, no dividends). CASH stays flat."""
    if tick == "CASH":
        d0 = dt.date.fromisoformat(start)
        out, d = [], d0
        while d <= dt.date.today():
            out.append((d, 1000.0)); d = (d.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
        return out
    import yfinance as yf
    h = yf.Ticker(tick).history(start=start, auto_adjust=False)["Close"].dropna()
    m = h.groupby([h.index.year, h.index.month]).tail(1)
    base = float(h.iloc[0])
    pts = [(i.date(), 1000 * float(v) / base) for i, v in m.items()]
    pts.append((h.index[-1].date(), 1000 * float(h.iloc[-1]) / base))
    return pts


def prepare_dynamic(scene: dict) -> None:
    if "growth" in scene:
        g = scene["growth"]
        g["_data"] = series(g["tick"], g["start"])
    for key in ("race", "versus"):
        if key in scene:
            spec = scene[key]
            items = spec["items"] if key == "race" else [spec["a"], spec["b"]]
            spec["_data"] = [(name, series(tick, spec["start"])) for tick, name in items]


def ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def value_at(pts, frac):
    k = frac * (len(pts) - 1)
    a = int(k); b = min(a + 1, len(pts) - 1)
    return pts[a][1] + (pts[b][1] - pts[a][1]) * (k - a), pts[int(round(k))][0]


COLORS = [(232, 69, 44), (242, 178, 51), (40, 120, 200), (40, 150, 90), (120, 80, 170), (90, 90, 90)]


def draw_race(img: Image.Image, spec: dict, prog: float) -> None:
    prog = 1.0 if spec.get("hold") else prog
    d = ImageDraw.Draw(img)
    frac = ease(prog / 0.85)
    vals = []
    for k, (name, pts) in enumerate(spec["_data"]):
        v, when = value_at(pts, frac)
        vals.append((name, v, COLORS[k % len(COLORS)]))
    d.text((W / 2, 230), str(when.year), font=font(SERIF, 200), fill=INK, anchor="mm")
    d.text((W / 2, 360), spec.get("label", "$1,000 invested in each"), font=font(SEMI, 40), fill=MUTED, anchor="mm")
    vals.sort(key=lambda x: -x[1])
    top = max(v for _, v, _ in vals) or 1
    y = 470
    x0 = 60
    for name, v, col in vals:
        d.text((x0, y), name, font=font(BOLD, 46), fill=INK)
        wbar = int(24 + (W - 2 * x0 - 24) * (v / top))
        d.rounded_rectangle((x0, y + 62, x0 + wbar, y + 142), 16, fill=col)
        vt = money(v)
        inside = wbar > d.textlength(vt, font=font(BOLD, 46)) + 60
        d.text((x0 + wbar - 20, y + 102) if inside else (x0 + wbar + 16, y + 102), vt, font=font(BOLD, 46),
               fill=(255, 255, 255) if inside else INK, anchor="rm" if inside else "lm")
        y += 190


def draw_versus(img: Image.Image, spec: dict, prog: float) -> None:
    prog = 1.0 if spec.get("hold") else prog
    d = ImageDraw.Draw(img)
    frac = ease(prog / 0.8)
    (na, pa), (nb, pb) = spec["_data"]
    va, when = value_at(pa, frac)
    vb, _ = value_at(pb, frac)
    d.text((W / 2, 230), f"$1,000 each in {spec['start'][:4]}", font=font(SEMI, 44), fill=MUTED, anchor="mm")
    d.text((W / 2, 330), str(when.year), font=font(SERIF, 120), fill=INK, anchor="mm")
    d.text((W / 2, 1330), "VS", font=font(SERIF, 90), fill=INK, anchor="mm")
    done = prog > 0.85
    for x0, name, v, other in ((60, na, va, vb), (W // 2 + 15, nb, vb, va)):
        win = done and v >= other
        box = (x0, 450, x0 + W // 2 - 75, 1250)
        d.rounded_rectangle(box, 30, fill=GOLD if win else CARD, outline=INK, width=4)
        cx = (box[0] + box[2]) / 2
        nf = font(BOLD, 64)
        while d.textlength(name, font=nf) > box[2] - box[0] - 40 and nf.size > 34:
            nf = font(BOLD, nf.size - 4)
        d.text((cx, 560), name, font=nf, fill=INK, anchor="mm")
        vf = font(SERIF, 96)
        txt = money(v)
        while d.textlength(txt, font=vf) > box[2] - box[0] - 60 and vf.size > 40:
            vf = font(SERIF, vf.size - 6)
        d.text((cx, 850), txt, font=vf, fill=INK, anchor="mm")
        if win:
            d.text((cx, 1120), "WINNER", font=font(BOLD, 48), fill=INK, anchor="mm")


NEON, DEEP = (60, 230, 140), (8, 12, 22)


def draw_growth(img: Image.Image, spec: dict, prog: float) -> None:
    """3D-style growth chart: dark stage, perspective grid floor, glowing line drawing itself,
    a live count-up number riding the line head. One ticker, $1,000 start."""
    prog = 1.0 if spec.get("hold") else prog
    frac = ease(prog / 0.85)
    pts = spec["_data"]
    stage = Image.new("RGB", (W, H), DEEP)
    d = ImageDraw.Draw(stage)
    # perspective floor grid (vanishing point above the chart): reads as 3D depth
    vx, vy = W / 2, 1180                         # horizon just under the chart's baseline
    for i in range(-16, 17):
        d.line([(vx + i * 30, vy + 220), (vx + i * 260, H + 40)], fill=(26, 52, 74), width=2)
    for k in range(0, 12):
        y = vy + 220 + (H + 40 - vy - 220) * (k / 11) ** 2.0
        d.line([(0, y), (W, y)], fill=(26, 52, 74), width=2)
    d = ImageDraw.Draw(stage)
    # chart box
    x0, x1, y0, y1 = 90, W - 90, 520, 1360
    vals = [v for _, v in pts]
    top = max(vals) * 1.08
    n = max(2, int(frac * (len(pts) - 1)) + 1)
    xy = [(x0 + (x1 - x0) * i / (len(pts) - 1), y1 - (y1 - y0) * (pts[i][1] / top)) for i in range(n)]
    v_now, when = value_at(pts, frac)
    hx = x0 + (x1 - x0) * frac
    hy = y1 - (y1 - y0) * (v_now / top)
    xy.append((hx, hy))
    # glow: thick blurred line under a crisp one
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.line(xy, fill=NEON, width=26, joint="curve")
    gd.ellipse((hx - 34, hy - 34, hx + 34, hy + 34), fill=NEON)
    glow = glow.filter(ImageFilter.GaussianBlur(22))
    stage = Image.fromarray(np.clip(np.asarray(stage, dtype=np.int16) + np.asarray(glow, dtype=np.int16), 0, 255).astype("uint8"))
    d = ImageDraw.Draw(stage)
    fill_poly = xy + [(hx, y1), (x0, y1)]
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shade).polygon(fill_poly, fill=(60, 230, 140, 46))
    stage.paste(shade, (0, 0), shade)
    d.line(xy, fill=(200, 255, 225), width=8, joint="curve")
    d.ellipse((hx - 14, hy - 14, hx + 14, hy + 14), fill=(255, 255, 255))
    # header + count-up
    d.text((W / 2, 170), spec.get("name", ""), font=font(BOLD, 56), fill=(170, 190, 210), anchor="mm")
    d.text((W / 2, 250), f"$1,000 in {spec['start'][:4]}, now {when.year}", font=font(SEMI, 40),
           fill=(120, 140, 160), anchor="mm")
    big = money(v_now)
    bf = font(SERIF, 150)
    while d.textlength(big, font=bf) > W - 120 and bf.size > 70:
        bf = font(SERIF, bf.size - 8)
    d.text((W / 2, 400), big, font=bf, fill=(255, 255, 255), anchor="mm")
    if prog > 0.9:
        mult = v_now / 1000
        d.text((W / 2, 1520), f"{mult:,.0f}x your money" if mult >= 2 else f"{(mult - 1) * 100:+.0f}%",
               font=font(BOLD, 64), fill=NEON, anchor="mm")
    img.paste(stage)


def _glass(stage: Image.Image, box, radius=36):
    """Frosted-glass panel with a soft glowing edge."""
    x0, y0, x1, y1 = [int(v) for v in box]
    region = stage.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(14))
    tint = Image.new("RGB", region.size, (34, 44, 62))
    region = Image.blend(region, tint, 0.55)
    mask = Image.new("L", region.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, x1 - x0, y1 - y0), radius, fill=255)
    stage.paste(region, (x0, y0), mask)
    glow = Image.new("RGB", stage.size, (0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle(box, radius, outline=NEON, width=6)
    glow = glow.filter(ImageFilter.GaussianBlur(10))
    out = np.clip(np.asarray(stage, dtype=np.int16) + np.asarray(glow, dtype=np.int16) // 2, 0, 255).astype("uint8")
    stage.paste(Image.fromarray(out))
    ImageDraw.Draw(stage).rounded_rectangle(box, radius, outline=(120, 240, 180), width=2)


def _dark_stage() -> Image.Image:
    stage = Image.new("RGB", (W, H), DEEP)
    blob = Image.new("RGB", (W, H), (0, 0, 0))
    bd = ImageDraw.Draw(blob)
    bd.ellipse((-300, 200, 700, 1100), fill=(18, 70, 60))
    bd.ellipse((500, 900, 1400, 1800), fill=(40, 30, 80))
    blob = blob.filter(ImageFilter.GaussianBlur(160))
    return Image.fromarray(np.clip(np.asarray(stage, dtype=np.int16) + np.asarray(blob, dtype=np.int16), 0, 255).astype("uint8"))


def draw_chat(img: Image.Image, text: str, prog: float) -> None:
    """Hook: a glowing chat window types the question, letter by letter, with a blinking cursor."""
    stage = _dark_stage()
    d = ImageDraw.Draw(stage)
    nl = len(wrap(d, text, font(BOLD, 64), W - 260)) or 1
    hgt = 220 + nl * 84
    box = (70, H / 2 - hgt / 2 - 80, W - 70, H / 2 + hgt / 2 - 80)
    _glass(stage, box)
    d = ImageDraw.Draw(stage)
    ty = box[1] + 50
    for k, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        d.ellipse((120 + 45 * k, ty - 15, 150 + 45 * k, ty + 15), fill=c)
    d.text((W / 2, ty), "FinanceHubW", font=font(SEMI, 30), fill=(150, 170, 190), anchor="mm")
    n = int(len(text) * min(1.0, prog / 0.7))
    shown = text[:n]
    f = font(BOLD, 64)
    lines = wrap(d, shown, f, box[2] - box[0] - 120) or [""]
    y = box[1] + 130
    for ln in lines[:6]:
        d.text((box[0] + 60, y), ln, font=f, fill=(240, 246, 250)); y += 84
    if int(prog * 12) % 2 == 0 or n < len(text):
        cx = box[0] + 60 + d.textlength(lines[-1], font=f) + 8
        d.rectangle((cx, y - 80, cx + 8, y - 12), fill=NEON)
    img.paste(stage)


def draw_slide(img: Image.Image, lines: list, prog: float) -> None:
    """Key lines slide up one after another on a dark stage; the newest is bright, older ones dim."""
    stage = _dark_stage()
    d = ImageDraw.Draw(stage)
    n = len(lines)
    f = font(BOLD, 66)
    y0 = H / 2 - n * 70
    for i, ln in enumerate(lines):
        start = i / max(n, 1) * 0.8
        t = ease((prog - start) / 0.18)
        if t <= 0:
            continue
        y = y0 + i * 140 + (1 - t) * 90
        col = (255, 255, 255) if i == min(n - 1, int(prog / 0.8 * n)) else (130, 150, 170)
        hi = ln.startswith("*") and ln.endswith("*")
        txt = ln.strip("*")
        d.text((W / 2, y), txt, font=f, fill=NEON if hi else col, anchor="mm")
    img.paste(stage)


# ------------------------------------------------------------------ voice
async def _speak(text: str, mp3: Path) -> list[dict]:
    import edge_tts
    words = []
    com = edge_tts.Communicate(text, VOICE, rate="+4%", boundary="WordBoundary")
    with open(mp3, "wb") as f:
        async for ch in com.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append({"t": ch["offset"] / 1e7, "d": ch["duration"] / 1e7, "w": ch["text"]})
    return words


ELEVEN_VOICE = os.environ.get("ELEVEN_VOICE_ID") or "nPczCjzI2devNBz1zQrb"   # "Brian": deep, calm narrator
_ELEVEN_OK = [True]


def _eleven(text: str, mp3: Path) -> list[dict]:
    import base64, requests
    r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE}/with-timestamps",
                      headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]}, timeout=120,
                      params={"output_format": "mp3_44100_128"},
                      json={"text": text, "model_id": os.environ.get("ELEVEN_MODEL") or "eleven_turbo_v2_5",
                            "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.25,
                                               "use_speaker_boost": True}})
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:200]}")
    j = r.json()
    mp3.write_bytes(base64.b64decode(j["audio_base64"]))
    al = j["alignment"]
    words, cur, start, end = [], "", None, 0.0
    for ch, a, b in zip(al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]):
        if ch.isspace():
            if cur:
                words.append({"t": start, "d": end - start, "w": cur}); cur = ""
            continue
        if not cur:
            start = a
        cur += ch; end = b
    if cur:
        words.append({"t": start, "d": end - start, "w": cur})
    for w in words:
        w["w"] = w["w"].strip(".,!?;:\"")
    return words


def speak(text: str, mp3: Path) -> list[dict]:
    """ElevenLabs studio voice when ELEVENLABS_API_KEY is set (falls back to the free voice if its
    monthly credits run out, so a Short is never blocked)."""
    if os.environ.get("ELEVENLABS_API_KEY") and _ELEVEN_OK[0]:
        try:
            return _eleven(text, mp3)
        except Exception as e:  # noqa: BLE001
            print(f"  ElevenLabs unavailable ({e}); using the free voice for the rest of this run")
            _ELEVEN_OK[0] = False
    for attempt in range(3):
        try:
            return asyncio.run(_speak(text, mp3))
        except Exception as e:  # noqa: BLE001
            print(f"  voice retry {attempt + 1}: {e}")
    raise RuntimeError("voice failed")


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout
    return float(out.strip())


# ------------------------------------------------------------------ pictures
def paper() -> Image.Image:
    rng = np.random.default_rng(3)
    base = np.ones((H, W, 3)) * np.array(PAPER)
    y = np.linspace(-1, 1, H)[:, None]
    x = np.linspace(-1, 1, W)[None, :]
    vign = 1 - 0.10 * (x ** 2 + y ** 2)
    noise = rng.normal(0, 4, (H, W, 1))
    return Image.fromarray(np.clip(base * vign[..., None] + noise, 0, 255).astype("uint8"))


PAPER_IMG = None


def wrap(d, text, f, width):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if cur and d.textlength(t, font=f) > width:
            lines.append(cur); cur = w
        else:
            cur = t
    return lines + ([cur] if cur else [])


def scene_image(scene: dict, seed: str) -> Image.Image:
    import photos
    global PAPER_IMG
    if PAPER_IMG is None:
        PAPER_IMG = paper()
    img = PAPER_IMG.copy()
    d = ImageDraw.Draw(img)
    d.text((60, 70), "FINANCEHUBW", font=font(BOLD, 26), fill=(150, 140, 126))
    if scene.get("race") or scene.get("versus") or scene.get("growth") or scene.get("chat") or scene.get("slide"):
        return img
    # photo card
    ph = photos.photo(scene.get("photo", ""), seed + scene.get("photo", ""), query=scene.get("photo"))
    cw, ch = 760, 620
    if ph is not None:
        pic = photos.cover_fit(ph, cw, ch)
        card = Image.new("RGB", (cw + 36, ch + 36), CARD)
        card.paste(pic, (18, 18))
        shadow = Image.new("RGBA", (card.width + 60, card.height + 60), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rectangle((30, 40, card.width + 30, card.height + 40), fill=(0, 0, 0, 70))
        shadow = shadow.filter(ImageFilter.GaussianBlur(18))
        ang = scene.get("tilt", -2.2 if hash(seed + scene.get("photo", "")) % 2 else 1.8)
        card = card.convert("RGBA").rotate(ang, expand=True, resample=Image.BICUBIC)
        shadow = shadow.rotate(ang, expand=True)
        cx, cy = (W - card.width) // 2, 200
        img.paste(shadow, (cx - 30, cy - 20), shadow)
        img.paste(card, (cx, cy), card)
        tape = Image.new("RGBA", (170, 46), (236, 226, 190, 200))
        tape = tape.rotate(-4, expand=True)
        img.paste(tape, (W // 2 - 85, cy - 18), tape)
        if ph.info.get("credit"):
            d.text((W - 60, cy + card.height + 8), ph.info["credit"][:60], font=font(SEMI, 18), fill=MUTED, anchor="ra")
    y = 960
    if scene.get("big"):
        big = scene["big"]
        size = 210
        while size > 90 and d.textlength(big, font=font(SERIF, size)) > W - 120:
            size -= 8
        lines = [big] if d.textlength(big, font=font(SERIF, size)) <= W - 120 else wrap(d, big, font(SERIF, 150), W - 120)
        for ln in lines:
            f = font(SERIF, size if len(lines) == 1 else 150)
            d.text(((W - d.textlength(ln, font=f)) / 2, y), ln, font=f, fill=INK)
            y += int(f.size * 1.05)
        if scene.get("sub"):
            sf = font(SEMI, 40)
            for ln in wrap(d, scene["sub"], sf, W - 200):
                d.text(((W - d.textlength(ln, font=sf)) / 2, y + 10), ln, font=sf, fill=MUTED)
                y += 52
    elif scene.get("quiz"):
        qz = scene["quiz"]
        qf = font(SERIF, 70)
        for ln in wrap(d, qz["q"], qf, W - 140):
            d.text(((W - d.textlength(ln, font=qf)) / 2, y), ln, font=qf, fill=INK); y += 84
        y += 30
        for tag, opt in (("A", qz["a"]), ("B", qz["b"])):
            d.rounded_rectangle((110, y, W - 110, y + 120), 26, fill=CARD, outline=INK, width=4)
            d.text((150, y + 60), tag, font=font(BOLD, 56), fill=GOLD, anchor="lm", stroke_width=3, stroke_fill=INK)
            d.text((230, y + 60), opt, font=font(BOLD, 50), fill=INK, anchor="lm")
            y += 150
    elif scene.get("clip"):
        c = scene["clip"]
        bx0, bx1 = 110, W - 110
        hf = font(SERIF, 64)
        lines = wrap(d, c["text"], hf, bx1 - bx0 - 80)
        bh = 110 + len(lines) * 76
        clip = Image.new("RGBA", (bx1 - bx0, bh), (246, 241, 230, 255))
        cd = ImageDraw.Draw(clip)
        cd.text((40, 30), c.get("kicker", "").upper(), font=font(BOLD, 26), fill=INK)
        if c.get("year"):
            cd.text((clip.width - 40, 30), c["year"], font=font(BOLD, 26), fill=INK, anchor="ra")
        cd.line((40, 72, clip.width - 40, 72), fill=INK, width=2)
        yy = 92
        for ln in lines:
            cd.text((40, yy), ln, font=hf, fill=INK); yy += 76
        clip = clip.rotate(-1.2, expand=True, resample=Image.BICUBIC)
        img.paste(clip, (bx0, y), clip)
    return img


def broll_clip(query: str, seed: str, seconds: float, td: Path):
    """Real stock footage (Pixabay videos, free for commercial use) for a scene: returns a generator of
    1080x1920 RGB frames, or None if no clip is available."""
    key = os.environ.get("PIXABAY_API_KEY")
    if not key or not query:
        return None
    import hashlib, requests
    try:
        r = requests.get("https://pixabay.com/api/videos/", timeout=20, params={
            "key": key, "q": query, "safesearch": "true", "per_page": 15, "min_width": 1280}).json()
        hits = [h for h in r.get("hits", []) if h.get("duration", 0) >= 4]
        if not hits:
            return None
        h = hits[int(hashlib.sha1(seed.encode()).hexdigest(), 16) % len(hits)]
        v = h["videos"].get("medium") or h["videos"].get("small")
        src = td / f"b_{hashlib.md5(seed.encode()).hexdigest()[:8]}.mp4"
        src.write_bytes(requests.get(v["url"], timeout=60).content)
    except Exception as e:  # noqa: BLE001
        print(f"  b-roll '{query}': {e}"); return None
    n = int(seconds * FPS) + 2
    proc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-stream_loop", "-1", "-i", str(src), "-t", f"{seconds + 0.2:.2f}",
                             "-vf", f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                                    "eq=saturation=1.08:contrast=1.05",
                             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)

    def frames():
        last = None
        for _ in range(n):
            buf = proc.stdout.read(W * H * 3)
            if len(buf) == W * H * 3:
                last = Image.frombytes("RGB", (W, H), buf)
            yield last
        proc.kill()
    return frames()


def broll_overlay(scene: dict) -> Image.Image:
    """Text layer for a footage scene: gradient for legibility, brand, and the big number or clipping."""
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    grad = Image.new("L", (1, H))
    for y in range(H):
        t = y / H
        grad.putpixel((0, y), int(255 * min(0.92, 0.35 * max(0, 1 - t / 0.18) + 0.9 * max(0, (t - 0.30) / 0.55) ** 0.9)))
    ov.paste(Image.new("RGBA", (W, H), (8, 8, 10, 255)), (0, 0), grad.resize((W, H)))
    d = ImageDraw.Draw(ov)
    d.text((60, 70), "FINANCEHUBW", font=font(BOLD, 28), fill=(255, 255, 255, 210))
    y = 1010
    if scene.get("big"):
        big = scene["big"]; size = 200
        while size > 90 and d.textlength(big, font=font(SERIF, size)) > W - 120:
            size -= 8
        f = font(SERIF, size)
        d.text(((W - d.textlength(big, font=f)) / 2, y), big, font=f, fill=(255, 255, 255, 255), stroke_width=4, stroke_fill=(0, 0, 0, 160))
        y += int(size * 1.08)
        if scene.get("sub"):
            sf = font(SEMI, 40)
            for ln in wrap(d, scene["sub"], sf, W - 200):
                d.text(((W - d.textlength(ln, font=sf)) / 2, y), ln, font=sf, fill=GOLD + (255,)); y += 52
    elif scene.get("clip"):
        c = scene["clip"]
        d.text((90, y), (c.get("kicker", "") + ("  ·  " + c["year"] if c.get("year") else "")).upper(),
               font=font(BOLD, 30), fill=GOLD + (255,))
        y += 56
        for ln in wrap(d, c["text"], font(SERIF, 76), W - 180):
            d.text((90, y), ln, font=font(SERIF, 76), fill=(255, 255, 255, 255), stroke_width=4, stroke_fill=(0, 0, 0, 160)); y += 88
    return ov


def caption_groups(words: list[dict], max_words=3) -> list[dict]:
    groups, cur = [], []
    for k, w in enumerate(words):
        cur.append(w)
        nxt = words[k + 1] if k + 1 < len(words) else None
        pause = nxt is not None and nxt["t"] - (w["t"] + w["d"]) > 0.18   # a spoken pause ends the caption
        if len(cur) >= max_words or pause:
            groups.append(cur); cur = []
    if cur:
        groups.append(cur)
    return groups


def draw_caption(img: Image.Image, group: list[dict], t: float) -> None:
    d = ImageDraw.Draw(img)
    f = font(BOLD, 74)
    words = [g["w"].upper() for g in group]
    total = d.textlength(" ".join(words), font=f)
    while total > W - 100 and f.size > 44:
        f = font(BOLD, f.size - 6)
        total = d.textlength(" ".join(words), font=f)
    x = (W - total) / 2
    y = 1560
    for g, wtxt in zip(group, words):
        on = g["t"] <= t < g["t"] + g["d"] + 0.12
        d.text((x, y), wtxt, font=f, fill=GOLD if on else (255, 255, 255), stroke_width=8, stroke_fill=INK)
        x += d.textlength(wtxt + " ", font=f)


# ------------------------------------------------------------------ assembly
def render(script_path: Path) -> dict:
    spec = json.loads(script_path.read_text(encoding="utf-8"))
    if not spec.get("sources"):
        sys.exit(f"{script_path.name}: no sources listed; not rendering")
    spec = deep_resolve(spec)
    vid = spec["id"]
    out = SHORTS / f"{vid}.mp4"
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        timeline, audio_parts, t0 = [], [], 0.0
        gap = 0.18
        for i, sc in enumerate(spec["scenes"]):
            mp3 = td / f"{i:02d}.mp3"
            words = speak(sc["say"], mp3)
            wav = td / f"{i:02d}.wav"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(mp3), "-ar", "24000", "-ac", "1", str(wav)], check=True)
            mp3 = wav
            dur = duration(mp3)
            for w in words:
                w["t"] += t0
            animated = any(sc.get(k) and not sc[k].get("hold") for k in ("race", "versus", "growth"))
            if sc.get("chat") or sc.get("slide"):
                animated = False                          # these follow the voice length
            hold = max(0.0, 6.0 - dur) if animated else 0.0     # let the race/count-up play out
            if hold:
                pad = td / f"{i:02d}_pad.wav"
                subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                                "-t", f"{hold:.2f}", str(pad)], check=True)
                padded = td / f"{i:02d}_full.wav"
                subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(mp3), "-i", str(pad), "-filter_complex",
                                "[0:a][1:a]concat=n=2:v=0:a=1", str(padded)], check=True)
                mp3, dur = padded, dur + hold
            timeline.append({"scene": sc, "start": t0, "end": t0 + dur + gap, "groups": caption_groups(words)})
            audio_parts.append(mp3)
            t0 += dur + gap
        total = t0 + 0.6
        # voice track with gaps
        lst = td / "list.txt"
        sil = td / "gap.wav"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                        "-t", str(gap), str(sil)], check=True)
        lst.write_text("".join(f"file '{p}'\nfile '{sil}'\n" for p in audio_parts))
        voice = td / "voice.wav"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-ar", "48000", "-ac", "1", str(voice)], check=True)
        bed = td / "bed.wav"
        from daily_short import music
        music(total, bed)
        try:   # soft whoosh on every cut, like an edited video
            import sound
            from scipy.io import wavfile
            sr, bm = wavfile.read(bed)
            bm = bm.astype("float32") / 32767
            for s_ in timeline[1:]:
                wv = sound.whoosh(0.45, 0.35)
                a = max(0, int((s_["start"] - 0.25) * sr))
                seg = wv[: max(0, len(bm) - a)]
                if bm.ndim == 2:
                    bm[a:a + len(seg), 0] += seg; bm[a:a + len(seg), 1] += seg
                else:
                    bm[a:a + len(seg)] += seg
            wavfile.write(bed, sr, (np.clip(bm, -1, 1) * 32767).astype("int16"))
        except Exception as e:  # noqa: BLE001
            print("  sfx skipped:", e)
        # frames
        for s in timeline:
            prepare_dynamic(s["scene"])
        for i, s in enumerate(timeline):
            sc = s["scene"]
            if not (sc.get("race") or sc.get("versus") or sc.get("growth") or sc.get("chat") or sc.get("slide") or sc.get("quiz")) and sc.get("photo"):
                s["broll"] = broll_clip(sc["photo"], vid + str(i), s["end"] - s["start"], td)
                if s["broll"] is not None:
                    s["overlay"] = broll_overlay(sc)
        bases = [scene_image(s["scene"], vid + str(i)) for i, s in enumerate(timeline)]
        vtmp = td / "v.mp4"
        p = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                              "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
                              "-crf", "20", "-pix_fmt", "yuv420p", str(vtmp)], stdin=subprocess.PIPE)
        n = int(total * FPS)
        for k in range(n):
            t = k / FPS
            i = next((j for j, s in enumerate(timeline) if s["start"] <= t < s["end"]), len(timeline) - 1)
            s = timeline[i]
            prog = (t - s["start"]) / max(0.1, s["end"] - s["start"])
            pop = min(1.0, (t - s["start"]) / 0.22)
            scale = 1.0 + 0.035 * prog - 0.05 * (1 - pop)
            base = bases[i]
            if abs(scale - 1) > 0.002:
                sw, sh = int(W * scale), int(H * scale)
                big = base.resize((sw, sh), Image.BILINEAR)
                if scale >= 1:
                    frame = big.crop(((sw - W) // 2, (sh - H) // 2, (sw - W) // 2 + W, (sh - H) // 2 + H))
                else:
                    frame = PAPER_IMG.copy(); frame.paste(big, ((W - sw) // 2, (H - sh) // 2))
            else:
                frame = base.copy()
            if s.get("broll") is not None:
                fr = next(s["broll"], None)
                if fr is not None:
                    sw, sh = int(W * (1.0 + 0.04 * prog)), int(H * (1.0 + 0.04 * prog))   # slow push-in
                    fr = fr.resize((sw, sh), Image.BILINEAR).crop(((sw - W) // 2, (sh - H) // 2, (sw - W) // 2 + W, (sh - H) // 2 + H))
                    frame = fr.convert("RGBA"); frame.alpha_composite(s["overlay"]); frame = frame.convert("RGB")
                    if t - s["start"] < 0.12:   # quick flash-cut between scenes
                        frame = Image.blend(frame, Image.new("RGB", (W, H), (255, 255, 255)), 0.25 * (1 - (t - s["start"]) / 0.12))
            if s["scene"].get("race"):
                frame = base.copy(); draw_race(frame, s["scene"]["race"], prog)
            elif s["scene"].get("versus"):
                frame = base.copy(); draw_versus(frame, s["scene"]["versus"], prog)
            elif s["scene"].get("growth"):
                frame = base.copy(); draw_growth(frame, s["scene"]["growth"], prog)
            elif s["scene"].get("chat"):
                frame = base.copy(); draw_chat(frame, s["scene"]["chat"], prog)
            elif s["scene"].get("slide"):
                frame = base.copy(); draw_slide(frame, s["scene"]["slide"], prog)
            grp = next((g for g in s["groups"] if g[0]["t"] - 0.05 <= t <= g[-1]["t"] + g[-1]["d"] + 0.25), None)
            if grp:
                draw_caption(frame, grp, t)
            p.stdin.write(frame.tobytes())
        p.stdin.close(); p.wait()
        SHORTS.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(vtmp), "-i", str(voice), "-i", str(bed),
                        "-filter_complex",
                        "[1:a]highpass=f=70,acompressor=threshold=-20dB:ratio=3,volume=1.0[v];"
                        "[2:a]volume=0.22[m];[v][m]amix=inputs=2:duration=first:normalize=0,"
                        "loudnorm=I=-14:TP=-1.5:LRA=9[a]",
                        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-shortest", "-movflags", "+faststart", str(out)], check=True)
    entry = {"file": out.name, "title": spec["title"], "caption": spec["caption"], "tags": spec["tags"],
             "comment": spec["comment"], "thumb": spec["thumb"], "thumb_photo": spec["thumb_photo"],
             "thumb_tag": spec["thumb_tag"], "ai_voice": True,
             "voice": "elevenlabs" if (os.environ.get("ELEVENLABS_API_KEY") and _ELEVEN_OK[0]) else "free", "made": dt.date.today().isoformat(),
             "sources": spec["sources"]}
    import thumbs
    thumbs.make(entry)
    return entry


def main() -> None:
    q = json.loads(QUEUE.read_text(encoding="utf-8"))
    have = {i["file"] for i in q["items"]}
    names = sys.argv[1:] or [p.stem for p in sorted(SCRIPTS.glob("*.json"))]
    for name in names:
        path = SCRIPTS / f"{name}.json"
        spec = json.loads(path.read_text(encoding="utf-8"))
        if f"{spec['id']}.mp4" in have and len(sys.argv) < 2:
            continue
        print("rendering", name)
        entry = render(path)
        q["items"] = [i for i in q["items"] if i["file"] != entry["file"]] + [entry]
        QUEUE.write_text(json.dumps(q, indent=1, ensure_ascii=False), encoding="utf-8")
        print("  ->", entry["file"], "|", entry["title"])


if __name__ == "__main__":
    main()
