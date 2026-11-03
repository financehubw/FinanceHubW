"""Real-footage Shorts: money moments in the speaker's own words, from public-domain footage.

Why: in finance and news Shorts, real people on camera beat AI narration (comparable clip channels get about
3x the views per Short). Legal sources only, always credited:
  - Universal Newsreel and Prelinger films (public domain) via the Internet Archive
  - presidential speeches on Wikimedia Commons (public domain / CC BY)
  - the Federal Reserve Board's own videos (works of the US government)
YouTube itself is never downloaded from (it blocks cloud runners, and its terms forbid it).

  python social/clips.py scout KEY...   download + transcribe a source  -> social/clip_sources/KEY.json
  python social/clips.py make ID...     render social/clip_specs/ID.json -> site/media/shorts/ID.mp4 + queue
  python social/clips.py mine KEY...    let Gemini pick the best moments of these sources, then render them
  python social/clips.py auto           new Fed press conference, or a fresh history source, mined by Gemini
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SHORTS = ROOT / "site" / "media" / "shorts"
THUMBS = SHORTS / "thumbs"
QUEUE = ROOT / "social" / "queue.json"
REGISTRY = ROOT / "social" / "clip_sources.json"
SRC_DIR = ROOT / "social" / "clip_sources"
SPEC_DIR = ROOT / "social" / "clip_specs"
DONE = ROOT / "social" / "clips_done.json"
FONTS = ROOT / "motion" / "fonts"
CACHE = Path(os.environ.get("CLIP_CACHE", "/tmp/fhw_clips"))
UA = {"User-Agent": "FinanceHubW-clips/1.0 (https://github.com/financehubw/FinanceHubW) python-requests"}
W, H, FPS = 1080, 1920, 30
DEEP, WHITE, AMBER, NEON, GREY = (8, 12, 22), (244, 246, 250), (255, 192, 46), (60, 230, 140), (150, 160, 176)
BOLD, SEMI, SERIF = "archivo-latin-800-normal.ttf", "archivo-latin-600-normal.ttf", "fraunces-latin-900-normal.ttf"

FED_PLAYER = "https://players.brightcove.net/66043936001/default_default/index.html?videoId={}"


def font(name: str, size: int):
    return ImageFont.truetype(str(FONTS / name), size)


def load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------ sources
def download(url: str, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.stat().st_size > 10_000:
        return out
    url = re.sub(r"\?utm_[^#]*$", "", url)
    for attempt in range(6):
        try:
            with requests.get(url, headers=UA, timeout=120, stream=True) as r:
                if r.status_code == 429:      # Wikimedia rate limit: wait as long as it asks
                    wait = int(r.headers.get("Retry-After", "0") or 0) or 30 * 2 ** attempt
                    print(f"  rate limited, waiting {wait}s"); time.sleep(min(wait, 300)); continue
                r.raise_for_status()
                tmp = out.with_suffix(out.suffix + ".part")
                with open(tmp, "wb") as fh:
                    for ch in r.iter_content(1 << 20):
                        fh.write(ch)
                tmp.rename(out)
                return out
        except requests.RequestException as e:
            print(f"  download retry {attempt + 1}: {e}")
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"could not download {url}")


def commons_file(title: str) -> dict:
    r = requests.get("https://commons.wikimedia.org/w/api.php", headers=UA, timeout=60, params={
        "action": "query", "titles": f"File:{title}", "prop": "imageinfo", "iiprop": "url|extmetadata|size",
        "format": "json"}).json()
    page = next(iter(r["query"]["pages"].values()))
    ii = page["imageinfo"][0]
    em = ii.get("extmetadata", {})
    clean = lambda k: re.sub("<[^>]+>", "", em.get(k, {}).get("value", ""))[:300]
    return {"url": ii["url"], "page": ii.get("descriptionurl", ""), "license": clean("LicenseShortName"),
            "date": clean("DateTimeOriginal"), "description": clean("ImageDescription")}


def archive_file(ident: str, prefer: str | None = None) -> tuple[str, str]:
    j = requests.get(f"https://archive.org/metadata/{ident}", headers=UA, timeout=60).json()
    files = [f for f in j.get("files", []) if f["name"].lower().endswith(".mp4")]
    if prefer:
        files = [f for f in files if f["name"] == prefer] or files
    files = [f for f in files if int(f.get("size", 0)) < 400e6] or files
    best = max(files, key=lambda f: (int(f.get("height") or 0), "_edit" not in f["name"], int(f.get("size", 0))))
    return f"https://archive.org/download/{ident}/{best['name']}", f"https://archive.org/details/{ident}"


def media_for(key: str, info: dict) -> Path:
    cached = [p for p in CACHE.glob(f"{key}.*") if not p.name.endswith(".part") and p.stat().st_size > 10_000]
    if cached:
        return cached[0]
    kind = info["kind"]
    if kind == "archive":
        url, _ = archive_file(info["id"], info.get("file"))
        return download(url, CACHE / f"{key}.mp4")
    if kind == "commons":
        url = commons_file(info["title"])["url"]
        return download(url, CACHE / f"{key}{Path(url).suffix}")
    if kind == "brightcove":
        out = CACHE / f"{key}.mp4"
        if not out.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["yt-dlp", "-q", "-f", "best[height<=720]/best", "-o", str(out),
                            FED_PLAYER.format(info["id"])], check=True)
        return out
    if kind == "url":
        return download(info["url"], CACHE / f"{key}{Path(info['url']).suffix or '.mp4'}")
    raise ValueError(f"unknown source kind {kind}")


def probe(path: Path) -> dict:
    j = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height:format=duration", "-of", "json", str(path)],
                                  capture_output=True, text=True, check=True).stdout)
    return {"width": j["streams"][0]["width"], "height": j["streams"][0]["height"],
            "duration": float(j["format"]["duration"])}


# ------------------------------------------------------------------ transcripts
def audio16k(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def transcribe(path: Path, model_name: str | None = None) -> list[dict]:
    from faster_whisper import WhisperModel
    m = WhisperModel(model_name or os.environ.get("WHISPER_MODEL", "small.en"), device="cpu", compute_type="int8")
    segs, _ = m.transcribe(audio16k(path), language="en", beam_size=5, word_timestamps=True, vad_filter=True,
                           condition_on_previous_text=False)
    out = []
    for s in segs:
        words = [[w.word.strip(), round(w.start, 2), round(w.end, 2)] for w in (s.words or []) if w.word.strip()]
        out.append({"s": round(s.start, 2), "e": round(s.end, 2), "text": s.text.strip(), "words": words})
    return out


def scout(key: str) -> dict:
    info = load(REGISTRY, {})[key]
    media = media_for(key, info)
    meta = probe(media)
    print(f"scout {key}: {info.get('title')} | {meta}")
    if info["kind"] == "commons":
        c = commons_file(info["title"])
        print(f"  commons: date={c['date']} | license={c['license']} | {c['description']}")
    segs = transcribe(media)
    doc = {"key": key, "info": info, **meta, "segments": segs}
    save(SRC_DIR / f"{key}.json", doc)
    for s in segs:
        print(f"  [{s['s']:7.1f}-{s['e']:7.1f}] {s['text']}")
    return doc


# ------------------------------------------------------------------ drawing
def rich_tokens(text: str) -> list[tuple[str, bool]]:
    """'Reagan shows what *inflation* did' -> [(word, highlighted), ...]"""
    out = []
    for part in re.findall(r"[^\s*]*\*[^*]+\*[^\s*]*|[^*\s]+", text):   # quotes/punctuation stay glued
        hi = "*" in part
        out += [(w, hi) for w in part.replace("*", "").split()]
    return out


def wrap_rich(d, tokens, f, width):
    lines, cur = [], []
    for w, hi in tokens:
        test = " ".join(x for x, _ in cur + [(w, hi)])
        if cur and d.textlength(test, font=f) > width:
            lines.append(cur); cur = []
        cur.append((w, hi))
    return lines + ([cur] if cur else [])


def draw_rich(d, xy, lines, f, gap, color=WHITE, hcolor=AMBER, stroke=0):
    x0, y = xy
    for ln in lines:
        x = x0
        for w, hi in ln:
            d.text((x, y), w, font=f, fill=hcolor if hi else color, stroke_width=stroke, stroke_fill=(0, 0, 0))
            x += d.textlength(w + " ", font=f)
        y += gap
    return y


def fit_headline(d, text: str, width: int, max_h: int, start=78, lines_max=4):
    tokens = rich_tokens(text)
    size = start
    while size > 40:
        f = font(BOLD, size)
        lines = wrap_rich(d, tokens, f, width)
        if len(lines) <= lines_max and len(lines) * int(size * 1.16) <= max_h:
            return f, lines, int(size * 1.16)
        size -= 4
    f = font(BOLD, 40)
    return f, wrap_rich(d, tokens, f, width)[:lines_max], 46


def pill(d, xy, text, f, fg, bg, pad=(22, 12), anchor_right=False):
    tw = d.textlength(text, font=f)
    x, y = xy
    if anchor_right:
        x -= tw + 2 * pad[0]
    d.rounded_rectangle((x, y, x + tw + 2 * pad[0], y + f.size + 2 * pad[1]), radius=(f.size + 2 * pad[1]) // 2, fill=bg)
    d.text((x + pad[0], y + pad[1] - 2), text, font=f, fill=fg)
    return x + tw + 2 * pad[0]


def headline_layout(spec: dict):
    d = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    f, lines, gap = fit_headline(d, spec["headline"], W - 128, 340)
    return f, lines, gap, 206 + len(lines) * gap + 46


def panel(spec: dict) -> Image.Image:
    """Static RGBA overlay: headline panel on top, credit footer at the bottom."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f, lines, gap, top = headline_layout(spec)
    d.rectangle((0, 0, W, top), fill=DEEP + (250,))
    for k in range(70):                                    # soft edge into the footage
        d.line((0, top + k, W, top + k), fill=DEEP + (int(250 * (1 - k / 70) ** 2),))
    d.text((64, 62), "FINANCEHUBW", font=font(BOLD, 34), fill=NEON)
    pill(d, (W - 64, 52), spec["date"].upper(), font(BOLD, 30), WHITE, (38, 46, 62, 255), anchor_right=True)
    tag = spec.get("tag", "MONEY HISTORY").upper()
    d.ellipse((66, 146, 84, 164), fill=(235, 64, 52))
    d.text((98, 136), tag + "  ·  REAL FOOTAGE", font=font(BOLD, 30), fill=AMBER)
    draw_rich(d, (64, 206), lines, f, gap)
    fy = H - 190
    for k in range(120):
        d.line((0, fy + k, W, fy + k), fill=DEEP + (int(235 * min(1, k / 60)),))
    d.rectangle((0, fy + 120, W, H), fill=DEEP + (235,))
    cf = font(SEMI, 27)
    credit = "Source: " + spec["credit"]
    y = H - 120
    for ln in wrap_rich(d, [(w, False) for w in credit.split()], cf, W - 128)[:2]:
        d.text((64, y), " ".join(w for w, _ in ln), font=cf, fill=GREY); y += 36
    hf = font(BOLD, 30)
    d.text((W - 64 - d.textlength("@financehubw", font=hf), H - 168), "@financehubw", font=hf, fill=WHITE)
    return img


def caption_groups(words: list[dict], max_words=4) -> list[list[dict]]:
    groups, cur = [], []
    for k, w in enumerate(words):
        cur.append(w)
        nxt = words[k + 1] if k + 1 < len(words) else None
        pause = nxt is not None and nxt["t"] - (w["t"] + w["d"]) > 0.35
        end = w["w"].endswith((".", "?", "!", ","))
        if len(cur) >= max_words or pause or (end and len(cur) >= 2):
            groups.append(cur); cur = []
    if cur:
        groups.append(cur)
    return groups


def draw_caption(img: Image.Image, group: list[dict], t: float, y: int) -> None:
    d = ImageDraw.Draw(img)
    f = font(BOLD, 66)
    words = [g["w"].upper() for g in group]
    sp = 16
    width = lambda f_: sum(d.textlength(w, font=f_) for w in words) + (len(words) - 1) * (d.textlength(" ", font=f_) + sp)
    while width(f) > W - 260 and f.size > 40:
        f = font(BOLD, f.size - 4)
    x = (W - width(f)) / 2
    for g, wtxt in zip(group, words):
        on = g["t"] <= t < g["t"] + g["d"] + 0.1
        d.text((x, y), wtxt, font=f, fill=AMBER if on else WHITE, stroke_width=7, stroke_fill=(0, 0, 0))
        x += d.textlength(wtxt, font=f) + d.textlength(" ", font=f) + sp


def draw_context(img: Image.Image, text: str, y: int, a: float) -> None:
    """'What happened next' line that slides up over the footage near the end."""
    d = ImageDraw.Draw(img, "RGBA")
    f = font(BOLD, 40)
    tokens = rich_tokens(text)
    lines = wrap_rich(d, tokens, f, W - 200)[:3]
    h = len(lines) * 52 + 50
    off = int((1 - a) * 40)
    d.rounded_rectangle((60, y - h + off, W - 60, y + off), 30, fill=(8, 12, 22, int(225 * a)))
    d.rectangle((60, y - h + off + 24, 70, y + off - 24), fill=AMBER + (int(255 * a),))
    draw_rich(d, (100, y - h + 25 + off), lines, f, 52)


# ------------------------------------------------------------------ live numbers for "what happened next" lines
_FRED: dict[str, dict[str, float]] = {}


def fred(series: str) -> dict[str, float]:
    """FRED series as {YYYY-MM-DD: value} (free CSV, no key)."""
    if series not in _FRED:
        t = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}", headers=UA, timeout=60).text
        out = {}
        for line in t.splitlines()[1:]:
            d, _, v = line.partition(",")
            try:
                out[d] = float(v)
            except ValueError:
                pass
        _FRED[series] = out
    return _FRED[series]


def px(ticker: str, date: str | None = None) -> float:
    import yfinance as yf
    if date:
        d = dt.date.fromisoformat(date)
        h = yf.Ticker(ticker).history(start=d.isoformat(), end=(d + dt.timedelta(days=10)).isoformat(), auto_adjust=False)
        return float(h["Close"].dropna().iloc[0])
    return float(yf.Ticker(ticker).history(period="10d", auto_adjust=False)["Close"].dropna().iloc[-1])


def resolve(text: str) -> str:
    """Live figures, filled in at render time so 'today' is always true:
      {cpi:1981-02}          prices multiplied since then, e.g. 3.6x (US CPI, FRED CPIAUCSL)
      {cpi$:1947-06:2.98}    $2.98 then in today's dollars;  {cpic:1960-01}  a 1960 dollar today, in cents
      {yoy:CPIAUCSL}         change over the last 12 months (%)
      {fred:DPRIME:1:2}      latest value of a FRED series / 1, 2 decimals
      {px:GC=F} {px$:GC=F}   latest price (with $), {px:^GSPC:1982-10-13} close on that date"""
    def cpi(m):
        s = fred("CPIAUCSL")
        last = s[max(s)]
        base = next(v for k, v in sorted(s.items()) if k[:7] >= m.group(2))
        x = last / base
        if m.group(1) == "cpic":                 # what that old dollar is worth today, in cents
            return f"{100 / x:.0f} cents"
        return f"${x * float(m.group(3)):,.2f}" if m.group(1) == "cpi$" else f"{x:.1f}x"

    def yoy(m):                                  # change over the last 12 months, in %
        s = fred(m.group(1))
        k = sorted(s)
        last = k[-1]
        prev = max(d for d in k if d <= f"{int(last[:4]) - 1}{last[4:]}")
        return f"{(s[last] / s[prev] - 1) * 100:.1f}"

    def fr(m):
        s = fred(m.group(1))
        v = s[max(s)] / float(m.group(2))
        return f"{v:,.{int(m.group(3))}f}"

    def pr(m):
        v = px(m.group(2), m.group(3))
        txt = f"{v:,.0f}" if v >= 100 else f"{v:,.2f}"
        return ("$" if m.group(1) == "px$" else "") + txt
    text = re.sub(r"\{(cpi\$?|cpic):(\d{4}-\d{2})(?::([\d.]+))?\}", cpi, text)
    text = re.sub(r"\{yoy:([A-Z0-9]+)\}", yoy, text)
    text = re.sub(r"\{fred:([A-Z0-9]+):([\d.e]+):(\d)\}", fr, text)
    return re.sub(r"\{(px\$?):([^:}]+)(?::(\d{4}-\d{2}-\d{2}))?\}", pr, text)


# ------------------------------------------------------------------ render
def cropdetect(src: Path, s: float, e: float) -> str | None:
    p = subprocess.run(["ffmpeg", "-v", "info", "-ss", f"{s:.2f}", "-t", f"{min(12.0, e - s):.2f}", "-i", str(src),
                        "-vf", "cropdetect=limit=24:round=2:reset=0", "-f", "null", "-"], capture_output=True, text=True)
    crops = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", p.stderr)
    if not crops:
        return None
    cw, ch, cx, cy = map(int, crops[-1])
    m = probe(src)
    if cw * ch >= 0.95 * m["width"] * m["height"] or cw < 100 or ch < 100:
        return None
    return f"crop={cw}:{ch}:{cx}:{cy}"


def words_in(doc: dict, s: float, e: float) -> list[dict]:
    out = []
    for seg in doc["segments"]:
        for w, ws, we in seg["words"]:
            if ws >= s - 0.05 and we <= e + 0.4:
                if out and re.match(r"^[.,%'\-]|^'s$", w):        # Whisper splits '12' '.4', 'trillion' '-dollar'
                    out[-1]["w"] += w
                    out[-1]["d"] = max(out[-1]["d"], we - s - out[-1]["t"])
                    continue
                out.append({"w": w, "t": ws - s, "d": max(0.08, we - ws), "abs": ws})
    return out


def apply_fixes(words: list[dict], fixes: dict, fix_at: list | None = None) -> list[dict]:
    """Caption fixes. `fix` maps names Whisper misspells ('Rosevelt' -> 'Roosevelt'). `fix_at` = [[time, heard,
    said], ...] for a single misheard word at that moment ('' drops it). Never used to change numbers or dates."""
    for w in words:
        core = re.sub(r"[^\w'-]", "", w["w"])
        if core in fixes:
            w["w"] = w["w"].replace(core, fixes[core])
    drop = set()
    for at, heard, said in fix_at or []:
        k = min(range(len(words)), key=lambda i: abs(words[i]["abs"] - float(at)), default=None)
        if k is None or heard.lower() not in words[k]["w"].lower():
            print(f"  fix_at {at} '{heard}' not found"); continue
        if said:
            words[k]["w"] = re.sub(re.escape(heard), said, words[k]["w"], flags=re.I)
        else:
            drop.add(k)
    return [w for i, w in enumerate(words) if i not in drop]


def render(spec_id: str) -> dict:
    spec = load(SPEC_DIR / f"{spec_id}.json", None)
    if not spec:
        raise SystemExit(f"no spec {spec_id}")
    key = spec["source"]
    doc = load(SRC_DIR / f"{key}.json", None) or scout(key)
    info = doc["info"]
    src = media_for(key, info)
    s, e = float(spec["start"]), float(spec["end"])
    dur = e - s
    if not 8 <= dur <= 60:
        raise SystemExit(f"{spec_id}: clip must be 8-60 s, got {dur:.1f}")
    spec.setdefault("credit", info["credit"])
    spec.setdefault("date", info.get("date", ""))
    for k in ("context", "caption", "title"):
        if spec.get(k):
            spec[k] = resolve(spec[k])
    crop = cropdetect(src, s, e)
    m = probe(src)
    cw, ch = (int(crop.split("=")[1].split(":")[0]), int(crop.split(":")[1])) if crop else (m["width"], m["height"])
    zoom = float(spec.get("zoom", 1.25 if cw / ch > 1.5 else 1.0))     # wide footage: crop the sides a little
    sw = int(round(W * zoom / 2) * 2)
    fg_h = min(1000, int(round(sw * ch / cw / 2) * 2))
    fx = int((sw - W) * float(spec.get("focus_x", 0.5)))
    top = headline_layout(spec)[3]
    block = fg_h + 34 + 84                                   # video + one caption line
    vy = top + 10 + max(0, (1560 - (top + 10) - block) // 2)
    cap_y = vy + fg_h + 34
    over = panel(spec)
    words = apply_fixes(words_in(doc, s, e), spec.get("fix", {}), spec.get("fix_at"))
    groups = caption_groups(words)
    pre = crop + "," if crop else ""
    vf = (f"[0:v]{pre}fps={FPS},split[a][b];"
          f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=34,eq=brightness=-0.22:saturation=0.8[bg];"
          f"[b]scale={sw}:{fg_h}:flags=lanczos,crop={W}:{fg_h}:{fx}:0,unsharp=5:5:0.6[fg];[bg][fg]overlay=0:{vy},format=rgb24[v]")
    frame_bytes = W * H * 3

    def decode(at: float, length: float | None):
        cmd = ["ffmpeg", "-v", "error", "-ss", f"{at:.3f}"] + (["-t", f"{length:.3f}"] if length else []) + \
              ["-i", str(src), "-filter_complex", vf, "-map", "[v]"] + ([] if length else ["-frames:v", "1"]) + \
              ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        return subprocess.Popen(cmd, stdout=subprocess.PIPE)

    out = SHORTS / f"{spec['id']}.mp4"
    SHORTS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        vtmp, atmp = td / "v.mp4", td / "a.m4a"
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                                "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "20",
                                "-pix_fmt", "yuv420p", str(vtmp)], stdin=subprocess.PIPE)
        one = decode(s + float(spec.get("cover_at", min(2.0, dur / 3))), None)
        raw = one.stdout.read(frame_bytes); one.wait()
        cover = make_cover(spec, raw, vy, fg_h)
        for _ in range(int(0.4 * FPS)):                 # the cover is also the first 0.4 s
            enc.stdin.write(cover.tobytes())
        dec = decode(s, dur)
        n = 0
        ctx_from = dur - float(spec.get("context_secs", 4.5))
        while True:
            buf = dec.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            t = n / FPS
            fr = Image.frombytes("RGB", (W, H), buf)
            fr.paste(over, (0, 0), over)
            g = next((g for g in groups if g[0]["t"] - 0.05 <= t <= g[-1]["t"] + g[-1]["d"] + 0.3), None)
            if g:
                draw_caption(fr, g, t, cap_y)
            if spec.get("context") and t >= ctx_from:
                draw_context(fr, spec["context"], vy + fg_h - 30, min(1.0, (t - ctx_from) / 0.35))
            enc.stdin.write(fr.tobytes())
            n += 1
        dec.wait()
        enc.stdin.close(); enc.wait()
        if n < FPS * 5:
            raise SystemExit(f"{spec_id}: decoded only {n} frames")
        a0 = 0.4
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{s:.3f}", "-t", f"{dur:.3f}", "-i", str(src), "-vn",
                        "-af", f"adelay={int(a0 * 1000)}:all=1,afade=t=in:st={a0}:d=0.12,"
                               f"afade=t=out:st={a0 + dur - 0.35:.2f}:d=0.35,highpass=f=60,"
                               "loudnorm=I=-14:TP=-1.5:LRA=11",
                        "-ar", "48000", "-ac", "2", "-c:a", "aac", "-b:a", "192k", str(atmp)], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(vtmp), "-i", str(atmp), "-map", "0:v", "-map", "1:a",
                        "-c:v", "copy", "-c:a", "copy", "-shortest", "-movflags", "+faststart", str(out)], check=True)
    page = info.get("page") or (f"https://archive.org/details/{info['id']}" if info["kind"] == "archive" else "")
    credit_line = f"Footage: {spec['credit']}." + (f" {page}" if page else "")
    entry = {"file": out.name, "title": spec["title"], "caption": spec["caption"].rstrip() + "\n\n" + credit_line,
             "tags": spec["tags"], "comment": spec["comment"], "thumb": spec.get("thumb", spec["headline"]),
             "thumb_photo": "", "thumb_tag": spec.get("tag", "MONEY HISTORY"), "ai_voice": False, "voice": "none",
             "made": dt.date.today().isoformat(), "sources": [credit_line], "format": "clip",
             "series": spec.get("series", "Money History, in Real Footage"), "ig_trial": True}
    return entry


def make_cover(spec: dict, raw: bytes, vy: int, fg_h: int) -> Image.Image:
    """Cover = the clip's own frame with a bigger headline and the key quote; saved as the thumbnail too."""
    img = Image.frombytes("RGB", (W, H), raw) if len(raw) == W * H * 3 else Image.new("RGB", (W, H), DEEP)
    d = ImageDraw.Draw(img, "RGBA")
    f, lines, gap = fit_headline(d, spec.get("thumb") or spec["headline"], W - 128, 340, start=96, lines_max=3)
    ctop = 222 + len(lines) * gap + 40
    d.rectangle((0, 0, W, ctop), fill=DEEP + (255,))
    for k in range(80):
        d.line((0, ctop + k, W, ctop + k), fill=DEEP + (int(255 * (1 - k / 80) ** 2),))
    d.text((64, 62), "FINANCEHUBW", font=font(BOLD, 34), fill=NEON)
    pill(d, (W - 64, 52), spec["date"].upper(), font(BOLD, 30), WHITE, (38, 46, 62, 255), anchor_right=True)
    pill(d, (64, 128), "REAL FOOTAGE", font(BOLD, 30), DEEP, AMBER + (255,))
    draw_rich(d, (64, 222), lines, f, gap)
    q = spec.get("quote")
    if q:
        qf = font(SERIF, 64)
        qlines = wrap_rich(d, [(w, False) for w in f"“{q}”".split()], qf, W - 160)[:3]
        qh = len(qlines) * 78 + 60
        y0 = min(1560 - qh, vy + fg_h - 40)
        d.rounded_rectangle((50, y0, W - 50, y0 + qh), 34, fill=(8, 12, 22, 225))
        draw_rich(d, (90, y0 + 28), qlines, qf, 78, color=WHITE)
    d.rectangle((0, H - 130, W, H), fill=DEEP + (235,))
    d.text((64, H - 100), "Source: " + spec["credit"][:70], font=font(SEMI, 27), fill=GREY)
    THUMBS.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(THUMBS / f"{spec['id']}.jpg", quality=90)
    return img.convert("RGB")


def make(ids: list[str], front: bool = False) -> list[dict]:
    q = load(QUEUE, {"items": []})
    made = []
    for sid in ids:
        print("clip:", sid)
        entry = render(sid)
        q["items"] = [i for i in q["items"] if i["file"] != entry["file"]]
        if front:   # timely clips (a Fed press conference) go next in line
            posted = {p["file"] for p in load(ROOT / "social" / "posted.json", {"posted": []})["posted"]}
            k = next((i for i, it in enumerate(q["items"]) if it["file"] not in posted), len(q["items"]))
            q["items"].insert(k, entry)
        else:
            q["items"].append(entry)
        save(QUEUE, q)
        made.append(entry)
        print("  ->", entry["file"], "|", entry["title"])
    return made


# ------------------------------------------------------------------ automatic mining (Gemini, free)
def ask_ai(prompt: str) -> str:
    sys.path.insert(0, str(ROOT / "xbot"))
    import verify
    errs = []
    for fn in (verify._gemini, getattr(verify, "_groq_oss", None), getattr(verify, "_openrouter", None)):
        if fn is None:
            continue
        try:
            return fn(prompt, 2000)
        except Exception as e:  # noqa: BLE001
            errs.append(str(e)[:120])
    raise RuntimeError("no AI model answered: " + " | ".join(errs))


def pick_moments(doc: dict, n: int, speaker: str, extra: str = "") -> list[dict]:
    info = doc["info"]
    lines = "\n".join(f"[{s['s']:.1f}-{s['e']:.1f}] {s['text']}" for s in doc["segments"])[:60000]
    prompt = f"""You edit FinanceHubW, a money channel. Real footage only, the speaker's own words, neutral and factual.
Source: {info.get('title')} ({info.get('date')}). Speaker: {speaker}. {extra}
Pick the {n} best self-contained moments for a vertical Short: 15-45 seconds, starting exactly at a strong statement
or where the speaker starts answering a question, ending right after the key line. In a press conference, prefer
direct answers to reporters' questions over the prepared opening statement. Prefer news people care about:
rate hikes or cuts, inflation, jobs, AI, markets, surprising numbers, clear warnings. Never cut mid-sentence.
Use only the timestamps given.

Return ONLY a JSON list, each item:
{{"start": <a segment start>, "end": <a segment end>,
 "headline": "<= 75 chars, names the speaker, 1-3 key words wrapped in *asterisks*>",
 "quote": "<= 12 words copied exactly from the moment",
 "thumb": "<= 6 words, 1-2 key words in *asterisks*",
 "title": "<= 70 chars, sentence case, in the form 'Speaker: key claim or question' (e.g. 'Fed Chair Warsh: Why not raise interest rates today?'), no hype words>",
 "caption": "<2 short factual sentences of context>",
 "comment": "<one question for viewers>",
 "tags": ["#tag", "#tag", "#tag", "#tag", "#tag"]}}

Transcript:
{lines}"""
    raw = ask_ai(prompt)
    m = re.search(r"\[.*\]", raw, re.S)
    try:
        picks = json.loads(m.group(0)) if m else []
    except json.JSONDecodeError as e:
        picks = []; print("  picks: bad JSON", e)
    if not picks:
        print("  picks: none in reply:", raw[:500].replace("\n", " "))
    starts = [s["s"] for s in doc["segments"]]
    ends = [s["e"] for s in doc["segments"]]
    good = []
    for p in picks:
        try:
            s = min(starts, key=lambda x: abs(x - float(p["start"])))
            e = min(ends, key=lambda x: abs(x - float(p["end"])))
        except (KeyError, TypeError, ValueError):
            print("  pick skipped (no usable times):", str(p)[:200]); continue
        if e - s > 50:             # too long: end at the last sentence that fits in 45 s
            e = max([x for x in ends if s + 12 <= x <= s + 45] or [e])
        if e - s < 15:             # too short: run on to the next sentence end
            e = min([x for x in ends if x >= s + 18] or [e])
        if not 12 <= e - s <= 50:
            print(f"  pick skipped ({e - s:.0f}s long):", p.get("headline")); continue
        text = " ".join(w for seg in doc["segments"] for w, ws, we in seg["words"] if s - 0.05 <= ws and we <= e + 0.4).lower()
        qw = re.sub(r"[^\w\s']", "", p.get("quote", "")).lower().split()
        if qw and sum(w in text for w in qw) < 0.7 * len(qw):
            print("  quote not in the moment, dropped:", p.get("quote")); p["quote"] = ""
        if not all(p.get(k) for k in ("headline", "title", "caption", "comment")):
            print("  pick skipped (missing text):", str(p)[:200]); continue
        print(f"  pick {s:.0f}-{e:.0f}s: {p['headline']}")
        good.append({**p, "start": s, "end": e})
    return good[:n]


def fed_latest() -> dict | None:
    """Most recent FOMC press conference (federalreserve.gov), if it happened in the last 10 days."""
    t = requests.get("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", headers=UA, timeout=60).text
    today = dt.date.today()
    dates = sorted({d for d in re.findall(r"fomcpresconf(\d{8})\.htm", t)
                    if 0 <= (today - dt.datetime.strptime(d, "%Y%m%d").date()).days <= 10})
    if not dates:
        return None
    d = dates[-1]
    page = f"https://www.federalreserve.gov/monetarypolicy/fomcpresconf{d}.htm"
    html = requests.get(page, headers=UA, timeout=60).text
    vid = re.search(r'data-video-id="(\d+)"', html)
    chair = re.search(r"Chair(?:man)?\s+([A-Z][a-zA-Z'-]+)", re.sub("<[^>]+>", " ", html))
    if not vid:
        return None
    name = chair.group(1) if chair else fed_chair()
    day = dt.datetime.strptime(d, "%Y%m%d")
    return {"key": f"fomc_{d}", "kind": "brightcove", "id": vid.group(1), "page": page,
            "title": f"FOMC Press Conference, {day:%B %-d, %Y}", "date": f"{day:%b %-d, %Y}",
            "credit": "Federal Reserve Board (public domain)", "speaker": f"Fed Chair {name}" if name else "the Fed Chair",
            "tag": "FED WATCH", "series": "Fed Watch"}


def fed_chair() -> str | None:
    """Surname of the current Fed Chair, from the Board's own list of members."""
    try:
        html = requests.get("https://www.federalreserve.gov/aboutthefed/bios/board/default.htm", headers=UA, timeout=60).text
    except requests.RequestException:
        return None
    lines = [l.strip() for l in re.sub(r"<[^>]+>", "\n", html).splitlines() if l.strip()]
    for i, l in enumerate(lines):
        if re.match(r"^Chair(man)?\b", l) and "Vice" not in l and i:
            name = lines[i - 1].rstrip(",")
            if re.match(r"^[A-Z][\w.' -]{3,40}$", name):
                print("  Fed Chair:", name)
                return name.split()[-1]
    m = re.search(r"([A-Z][a-z]+(?: [A-Z]\.)? [A-Z][a-z]+),?\s*Chair\b", " ".join(lines))
    return m.group(1).split()[-1] if m else None


def spec_from_pick(key: str, info: dict, p: dict, k: int) -> str:
    sid = f"clip_{key}_{k}"
    spec = {"id": sid, "source": key, "start": p["start"], "end": p["end"], "headline": p["headline"],
            "quote": p.get("quote", ""), "thumb": p.get("thumb", ""), "title": p["title"], "caption": p["caption"],
            "comment": p["comment"], "tags": (p.get("tags") or ["#money", "#finance"])[:6],
            "tag": info.get("tag", "MONEY HISTORY"), "series": info.get("series", "Money History, in Real Footage"),
            "auto": True}
    save(SPEC_DIR / f"{sid}.json", spec)
    return sid


def auto() -> None:
    done = load(DONE, {"sources": []})
    reg = load(REGISTRY, {})
    made = []
    try:
        fed = fed_latest()
    except requests.RequestException as e:
        fed = None; print("fed check failed:", e)
    tries = done.setdefault("tries", {})
    if fed and fed["key"] not in done["sources"] and tries.get(fed["key"], 0) < 3:
        reg[fed["key"]] = {k: v for k, v in fed.items() if k != "key"}
        save(REGISTRY, reg)
        doc = load(SRC_DIR / f"{fed['key']}.json", None) or scout(fed["key"])
        doc["info"] = reg[fed["key"]]
        picks = pick_moments(doc, 2, fed["speaker"], "Pick moments that answer what viewers care about: rate cuts, inflation, jobs, markets.")
        ids = [spec_from_pick(fed["key"], reg[fed["key"]], p, k) for k, p in enumerate(picks, 1)]
        made += make(ids, front=True)
        tries[fed["key"]] = tries.get(fed["key"], 0) + 1
        if ids:
            done["sources"].append(fed["key"])
        save(DONE, done)
    q = load(QUEUE, {"items": []})["items"]
    posted = {p["file"] for p in load(ROOT / "social" / "posted.json", {"posted": []})["posted"]}
    waiting = [i for i in q if i.get("format") == "clip" and i["file"] not in posted]
    if len(waiting) < 3:   # keep a small stock of history clips: mine the next source in the list
        nxt = next((k for k, v in reg.items() if v.get("mine", True) and k not in done["sources"]
                    and v["kind"] != "brightcove"), None)
        if nxt:
            doc = load(SRC_DIR / f"{nxt}.json", None) or scout(nxt)
            picks = pick_moments(doc, 2, reg[nxt].get("speaker", "the narrator"))
            ids = [spec_from_pick(nxt, reg[nxt], p, k) for k, p in enumerate(picks, 1)]
            made += make(ids)
            done["sources"].append(nxt); save(DONE, done)
    print(f"clips made: {len(made)}")


if __name__ == "__main__":
    cmd, args = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else ("auto", [])
    if cmd == "scout":
        for k in args:
            scout(k)
    elif cmd == "make":
        make(args)
    elif cmd == "mine":   # let the AI pick the best moments from these sources, then render them
        reg, done = load(REGISTRY, {}), load(DONE, {"sources": []})
        for k in args:
            info = reg[k]
            doc = load(SRC_DIR / f"{k}.json", None) or scout(k)
            doc["info"] = info
            picks = pick_moments(doc, int(info.get("moments", 2)), info.get("speaker", "the speaker"),
                                 info.get("pick_hint", ""))
            ids = [spec_from_pick(k, info, p, n) for n, p in enumerate(picks, 1)]
            make(ids)
            if ids and k not in done["sources"]:
                done["sources"].append(k)
            save(DONE, done)
    else:
        auto()
