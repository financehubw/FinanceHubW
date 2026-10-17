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


def speak(text: str, mp3: Path) -> list[dict]:
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
        # frames
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
             "thumb_tag": spec["thumb_tag"], "ai_voice": True, "made": dt.date.today().isoformat(),
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
