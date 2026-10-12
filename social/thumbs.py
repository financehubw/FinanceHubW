"""YouTube/Instagram cover for each Short, built to win the click:
a full-bleed, vivid topic photo (Pixabay, or the magazine library as backup), a strong bottom shade,
a topic tag, one short white line and the key number huge in gold with a dark outline.
Everything important sits in the centre square, so it still reads when a feed crops it.

    python social/thumbs.py [file.mp4 ...]   -> site/media/shorts/thumbs/<name>.jpg
Uses the queue entry's "thumb" (*words* = the big gold part), "thumb_photo" and "thumb_tag".
"""
from __future__ import annotations
import json, re, subprocess, sys, tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "social"))
SHORTS = ROOT / "site" / "media" / "shorts"
OUT = SHORTS / "thumbs"
F800 = ROOT / "motion" / "fonts" / "archivo-latin-800-normal.ttf"
F600 = ROOT / "motion" / "fonts" / "archivo-latin-600-normal.ttf"
W, H = 1080, 1920
GOLD, WHITE, INK, RED = (255, 196, 37), (255, 255, 255), (12, 12, 14), (232, 52, 46)


def frame(video: Path) -> Image.Image:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "f.jpg"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", "0.6", "-i", str(video),
                        "-frames:v", "1", str(out)], check=True)
        return Image.open(out).convert("RGB")


def background(item: dict) -> Image.Image:
    import photos
    img = None
    if item.get("thumb_photo"):
        img = photos.photo(item["thumb_photo"], item["file"], query=item["thumb_photo"])
        if img is not None and not img.info.get("credit") and img.width < 900:
            img = None
    if img is None:
        img = frame(SHORTS / item["file"])
    img = photos.cover_fit(img, W, H)
    img = ImageEnhance.Color(img).enhance(1.25)
    img = ImageEnhance.Contrast(img).enhance(1.1)
    shade = Image.new("L", (1, H))
    for y in range(H):
        t = y / H
        shade.putpixel((0, y), int(255 * (0.25 + 0.7 * max(0, (t - 0.25) / 0.75) ** 0.9)))
    img.paste(Image.new("RGB", (W, H), INK), mask=shade.resize((W, H)))
    return img


def outlined(d, xy, text, font, fill, stroke=10):
    d.text(xy, text, font=font, fill=fill, stroke_width=stroke, stroke_fill=INK)


def fit(d, text, path, start, maxw, minsize=60):
    size = start
    while size > minsize and d.textlength(text, font=ImageFont.truetype(str(path), size)) > maxw:
        size -= 6
    return ImageFont.truetype(str(path), size)


def make(item: dict) -> Path:
    img = background(item)
    d = ImageDraw.Draw(img)
    hook = item.get("thumb") or item["title"]
    big = " ".join(re.findall(r"\*([^*]+)\*", hook)) or hook
    small = re.sub(r"\s+", " ", re.sub(r"\*[^*]+\*", " ", hook)).strip(" =→-")
    small, big = small.upper(), big.upper()
    # tag
    tag = item.get("thumb_tag", "")
    if tag:
        tf = ImageFont.truetype(str(F800), 44)
        tw = d.textlength(tag, font=tf)
        x0 = (W - tw) / 2 - 30
        d.rounded_rectangle((x0, 620, x0 + tw + 60, 700), 40, fill=RED)
        d.text((x0 + 30, 633), tag, font=tf, fill=WHITE)
    y = 760
    if small:
        words, lines, cur = small.split(), [], ""
        sf = ImageFont.truetype(str(F800), 96)
        for w_ in words:
            t = (cur + " " + w_).strip()
            if cur and d.textlength(t, font=sf) > W - 120:
                lines.append(cur); cur = w_
            else:
                cur = t
        lines.append(cur)
        for ln in lines[:3]:
            f = fit(d, ln, F800, 96, W - 120)
            outlined(d, ((W - d.textlength(ln, font=f)) / 2, y), ln, f, WHITE, 8)
            y += int(f.size * 1.08)
        y += 20
    bf = fit(d, big, F800, 230, W - 90, 110)
    if d.textlength(big, font=bf) > W - 90 and " " in big:   # two lines for long phrases
        a, b = big.rsplit(" ", 1)
        for part in (a, b):
            f = fit(d, part, F800, 200, W - 90, 100)
            outlined(d, ((W - d.textlength(part, font=f)) / 2, y), part, f, GOLD, 12)
            y += int(f.size * 1.02)
    else:
        outlined(d, ((W - d.textlength(big, font=bf)) / 2, y), big, bf, GOLD, 12)
        y += int(bf.size * 1.05)
    # brand
    icon = ROOT / "brand" / "financehubw-icon.png"
    if icon.exists():
        m = Image.open(icon).convert("RGBA"); m.thumbnail((84, 84))
        img.paste(m, ((W - m.width) // 2 - 150, H - 330), m)
    bfnt = ImageFont.truetype(str(F800), 44)
    d.text(((W - m.width) // 2 - 150 + m.width + 20, H - 312), "FinanceHubW", font=bfnt, fill=WHITE)
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / (Path(item["file"]).stem + ".jpg")
    img.save(out, quality=92)
    return out


if __name__ == "__main__":
    items = json.loads((ROOT / "social" / "queue.json").read_text(encoding="utf-8"))["items"]
    for it in items:
        if (SHORTS / it["file"]).exists() and (len(sys.argv) < 2 or it["file"] in sys.argv[1:]):
            print(make(it))
