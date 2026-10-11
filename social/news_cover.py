"""Magazine-style cover (slide 1) and closing slide (slide 3) for a news update posted to the grid.
Slide 2 is the facts card from x_story.card(..., 1080, 1350)."""
from __future__ import annotations
import datetime as dt, re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "motion" / "fonts"
W, H = 1080, 1350
GOLD, WHITE = (242, 178, 51), (255, 255, 255)
THEMES = [  # (pattern, label, top colour, bottom colour)
    (r"\b(bitcoin|crypto|ethereum|btc|eth|xrp|solana|stablecoin|token)", "CRYPTO", (52, 22, 110), (12, 8, 38)),
    (r"🇮🇳|\b(rbi|sebi|sensex|nifty|rupee|india)\b", "INDIA", (120, 40, 10), (30, 10, 4)),
    (r"🇺🇸|\b(fed|wall street|s&p|nasdaq|dow|treasury|us stocks)\b", "UNITED STATES", (12, 44, 110), (4, 12, 34)),
    (r"🇪🇺|🇬🇧|\b(ecb|esma|euro|europe|eu|uk|boe)\b", "EUROPE", (10, 70, 90), (3, 18, 26)),
    (r"🇨🇳|🇯🇵|\b(china|japan|asia|yuan|yen)\b", "ASIA", (110, 14, 30), (30, 4, 10)),
    (r"\b(oil|opec|crude|gold|silver|commodit)", "COMMODITIES", (100, 70, 8), (28, 18, 2)),
]
DEFAULT = ("MARKETS", (15, 43, 85), (6, 14, 30))


def f(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def theme(text):
    low = text.lower()
    for pat, label, a, b in THEMES:
        if re.search(pat, text) or re.search(pat, low):
            return label, a, b
    return DEFAULT


def headline(text):
    first = next((ln for ln in text.split("\n") if ln.strip()), "")
    first = re.sub(r"^[^A-Za-z0-9$₹€£]+", "", first).replace("BREAKING:", "").strip()
    return first


def key_number(text):
    m = re.search(r"[$₹€£]?\d[\d,.]*\s?(%|percent|billion|million|trillion|bn|M|B)?", headline(text), re.I) \
        or re.search(r"[$₹€£]\d[\d,.]*\s?(billion|million|trillion|bn|M|B)?|\d[\d,.]*%", text, re.I)
    return m.group(0).strip() if m else ""


def background(a, b):
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3)))
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse((W * 0.35, -300, W * 1.4, 600), fill=90)
    img.paste(Image.new("RGB", (W, H), tuple(min(255, c + 70) for c in a)), mask=glow.filter(ImageFilter.GaussianBlur(160)))
    g = ImageDraw.Draw(img)
    for x in range(0, W, 54):
        g.line([(x, 0), (x, H)], fill=tuple(min(255, c + 12) for c in b))
    return img


def wrap(d, words, font, width):
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if cur and d.textlength(t, font=font) > width:
            lines.append(cur); cur = w
        else:
            cur = t
    return lines + ([cur] if cur else [])


def cover(post: dict, out: Path) -> None:
    text = post["text"]
    label, a, b = theme(text)
    img = background(a, b)
    d = ImageDraw.Draw(img)
    num = key_number(text)
    mark = re.sub(r"\s?percent", "%", num, flags=re.I)
    mark = re.sub(r"\s?(billion|bn)", "B", mark, flags=re.I); mark = re.sub(r"\s?(million)", "M", mark, flags=re.I)
    mark = re.sub(r"\s?(trillion)", "T", mark, flags=re.I)
    num_mark = mark if len(mark) <= 7 else ""
    if num_mark:  # giant faded number behind the headline
        big = f("fraunces-latin-900-normal.ttf", 460 if len(num_mark) < 4 else 330)
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text((W - 50, 520), num_mark, font=big, fill=(255, 255, 255, 34), anchor="rm")
        img.paste(layer, (0, 0), layer)
    # masthead
    d.text((70, 70), "FinanceHubW", font=f("fraunces-latin-900-normal.ttf", 92), fill=WHITE)
    d.rectangle([70, 196, W - 70, 199], fill=WHITE)
    when = dt.datetime.strptime(post["date"], "%Y-%m-%dT%H:%M:%SZ").strftime("%-d %B %Y").upper()
    small = f("archivo-latin-600-normal.ttf", 28)
    d.text((70, 214), f"LIVE NEWS  ·  {when}", font=small, fill=(220, 220, 220))
    chip = f("archivo-latin-800-normal.ttf", 28)
    cw = d.textlength(label, font=chip)
    d.rounded_rectangle([W - 70 - cw - 40, 208, W - 70, 252], 22, fill=GOLD)
    d.text((W - 70 - cw - 20, 213), label, font=chip, fill=(20, 20, 20))
    # headline, key number in gold
    words = headline(text).split()
    for size in (118, 104, 92, 82, 72):
        hf = f("archivo-latin-800-normal.ttf", size)
        lines = wrap(d, words, hf, W - 140)
        if len(lines) <= 5:
            break
    lh = int(size * 1.06)
    y = H - 300 - lh * len(lines)
    d.rectangle([70, y - 50, 190, y - 40], fill=GOLD)
    for ln in lines:
        x = 70
        for w in ln.split():
            hl = num and re.sub(r"\W", "", w) and re.sub(r"\W", "", w) in re.sub(r"\W", "", num.split()[0])
            d.text((x, y), w, font=hf, fill=GOLD if hl else WHITE)
            x += d.textlength(w + " ", font=hf)
        y += lh
    # footer
    d.text((70, H - 170), "Swipe for the facts", font=f("archivo-latin-800-normal.ttf", 40), fill=WHITE)
    ax = 70 + d.textlength("Swipe for the facts", font=f("archivo-latin-800-normal.ttf", 40)) + 24
    d.line([(ax, H - 146), (ax + 70, H - 146)], fill=GOLD, width=6)
    d.polygon([(ax + 70, H - 160), (ax + 92, H - 146), (ax + 70, H - 132)], fill=GOLD)
    d.text((70, H - 100), "Fact-checked by multiple sources  ·  @financehubw", font=small, fill=(200, 200, 200))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=92)


def closer(post: dict, out: Path) -> None:
    label, a, b = theme(post["text"])
    img = background(a, b)
    d = ImageDraw.Draw(img)
    d.text((70, 70), "FinanceHubW", font=f("fraunces-latin-900-normal.ttf", 92), fill=WHITE)
    d.rectangle([70, 196, W - 70, 199], fill=WHITE)
    y = 430
    for ln in ["Markets move", "every hour.", "Stay ahead."]:
        d.text((70, y), ln, font=f("archivo-latin-800-normal.ttf", 104), fill=GOLD if ln == "Stay ahead." else WHITE)
        y += 116
    s = f("archivo-latin-600-normal.ttf", 40)
    for i, ln in enumerate(["Follow @financehubw", "Fact-checked finance news every day",
                            "Daily brief Tue–Sat · Magazine every Saturday"]):
        d.text((70, 860 + i * 62), ln, font=s if i else f("archivo-latin-800-normal.ttf", 46), fill=WHITE if i == 0 else (215, 215, 215))
    d.text((70, H - 100), "Information only, not investment advice.", font=f("archivo-latin-600-normal.ttf", 28), fill=(190, 190, 190))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=92)


def facts(post: dict, out: Path) -> None:
    """Slide 2: the story in plain words, same look as the cover."""
    text = post["text"]
    label, a, b = theme(text)
    img = background(a, b)
    d = ImageDraw.Draw(img)
    d.text((70, 70), "FinanceHubW", font=f("fraunces-latin-900-normal.ttf", 92), fill=WHITE)
    d.rectangle([70, 196, W - 70, 199], fill=WHITE)
    d.text((70, 214), "THE FACTS", font=f("archivo-latin-800-normal.ttf", 28), fill=GOLD)
    raw = [ln.strip() for ln in text.split("\n") if ln.strip() and not ln.strip().startswith(("http", "#"))]
    clean = lambda s: re.sub(r"[^\u0000-ɏ‐-‧‰-⁞€₹™]", "", s).strip(" ·")
    foot = clean(raw[-1]) if raw and "📍" in raw[-1] else ""
    body = [clean(s) for s in raw[1:-1 if foot else None]]
    y = 330
    hf = f("archivo-latin-800-normal.ttf", 54)
    for ln in wrap(d, headline(text).split(), hf, W - 140)[:3]:
        d.text((70, y), ln, font=hf, fill=WHITE); y += 64
    y += 40
    for size in (44, 40, 36, 32):
        bf = f("archivo-latin-600-normal.ttf", size)
        blocks = [wrap(d, s.split(), bf, W - 180) for s in body]
        if y + sum(len(x) for x in blocks) * size * 1.4 + 40 * len(blocks) < H - 230:
            break
    for blk in blocks:
        d.rectangle([70, y + 12, 82, y + 24], fill=GOLD)
        for ln in blk:
            d.text((110, y), ln, font=bf, fill=(235, 235, 235)); y += int(size * 1.4)
        y += 40
    d.rectangle([70, H - 200, W - 70, H - 198], fill=(255, 255, 255))
    if foot:
        d.text((70, H - 175), "SOURCE  " + foot, font=f("archivo-latin-600-normal.ttf", 30), fill=GOLD)
    d.text((70, H - 115), "Information only, not investment advice.  ·  @financehubw",
           font=f("archivo-latin-600-normal.ttf", 28), fill=(200, 200, 200))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=92)
