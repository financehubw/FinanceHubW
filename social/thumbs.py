"""Cover image for each Short: a calm frame from the video, darkened, with a big hook line.

    python social/thumbs.py            -> site/media/shorts/thumbs/<name>.jpg for every queued Short
The hook comes from the queue entry's "thumb" field; *words* are highlighted in gold.
"""
from __future__ import annotations
import json, re, subprocess, sys, tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SHORTS = ROOT / "site" / "media" / "shorts"
OUT = SHORTS / "thumbs"
FONT = ROOT / "motion" / "fonts" / "archivo-latin-800-normal.ttf"
SMALL = ROOT / "motion" / "fonts" / "archivo-latin-600-normal.ttf"
W, H = 1080, 1920
NAVY, GOLD, WHITE, GREEN = (10, 26, 51), (242, 178, 51), (255, 255, 255), (24, 201, 139)


def frame(video: Path) -> Image.Image:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "f.jpg"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", "0.6", "-i", str(video),
                        "-frames:v", "1", str(out)], check=True)
        img = Image.open(out).convert("RGB")
    img = img.resize((W, int(W * img.height / img.width))).crop((0, 0, W, H)) if img.height * W / img.width >= H \
        else img.resize((int(H * img.width / img.height), H)).crop((0, 0, W, H))
    img = img.filter(ImageFilter.GaussianBlur(30))
    return ImageEnhance.Brightness(img).enhance(0.32)


def wrap(words, font, width, draw):
    lines, cur = [], []
    for w in words:
        test = " ".join(t for t, _ in cur + [w])
        if cur and draw.textlength(test, font=font) > width:
            lines.append(cur); cur = [w]
        else:
            cur.append(w)
    return lines + ([cur] if cur else [])


def make(item: dict) -> Path:
    video = SHORTS / item["file"]
    img = frame(video)
    shade = Image.new("L", (1, H))
    for y in range(H):
        shade.putpixel((0, y), int(150 * abs(y - H * 0.47) / (H * 0.5)))
    img.paste(Image.new("RGB", (W, H), NAVY), mask=shade.resize((W, H)))
    d = ImageDraw.Draw(img)
    words = []
    for part in re.split(r"(\*[^*]+\*)", item.get("thumb") or item["title"]):
        hl = part.startswith("*")
        words += [(w, hl) for w in part.strip("*").split()]
    size = 150
    while True:
        f = ImageFont.truetype(str(FONT), size)
        lines = wrap(words, f, W - 140, d)
        if len(lines) <= 4 or size < 90:
            break
        size -= 8
    lh = int(size * 1.12)
    y = int(H * 0.47 - lh * len(lines) / 2)
    for line in lines:
        x0 = (W - d.textlength(" ".join(t for t, _ in line), font=f)) / 2
        sp = d.textlength(" ", font=f)
        pos, x = [], x0
        for t, hl in line:
            pos.append((x, t, hl)); x += d.textlength(t, font=f) + sp
        i = 0
        while i < len(pos):                      # one gold box per run of highlighted words
            if pos[i][2]:
                j = i
                while j + 1 < len(pos) and pos[j + 1][2]:
                    j += 1
                end = pos[j][0] + d.textlength(pos[j][1], font=f)
                d.rounded_rectangle((pos[i][0] - 16, y + size * 0.1, end + 16, y + size * 1.12), 20, fill=GOLD)
                i = j + 1
            else:
                i += 1
        for x, t, hl in pos:
            d.text((x, y), t, font=f, fill=NAVY if hl else WHITE)
        y += lh
    icon = ROOT / "brand" / "financehubw-icon.png"
    if icon.exists():
        m = Image.open(icon).convert("RGBA"); m.thumbnail((110, 110))
        img.paste(m, ((W - m.width) // 2, 170), m)
    s = ImageFont.truetype(str(SMALL), 40)
    t = "FINANCEHUBW"
    d.text(((W - d.textlength(t, font=s)) / 2, 300), t, font=s, fill=GREEN)
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / (video.stem + ".jpg")
    img.save(out, quality=90)
    return out


if __name__ == "__main__":
    items = json.loads((ROOT / "social" / "queue.json").read_text(encoding="utf-8"))["items"]
    for it in items:
        if (SHORTS / it["file"]).exists() and (len(sys.argv) < 2 or it["file"] in sys.argv[1:]):
            print(make(it))
