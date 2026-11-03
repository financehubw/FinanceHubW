"""Weekly long video: stitches finished Shorts into one 16:9 episode with chapters and uploads it.

Long videos turn viewers into subscribers far better than Shorts, and their watch time counts toward
YouTube's 4,000-hour monetisation goal. Shorts are placed centre-stage over a blurred copy of
themselves, with a numbered title beside each one, plus an intro card and a subscribe outro.

    python social/compile_long.py                     # auto: this week's posted Shorts (not news)
    python social/compile_long.py --files a b c --title "..."
    DRY_RUN=1 ...                                     # build the video, don't upload
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SHORTS = ROOT / "site" / "media" / "shorts"
FONTS = ROOT / "motion" / "fonts"
LOG = ROOT / "social" / "long_posted.json"
W, H = 1920, 1080
BG, INK, MUTED, ACCENT = (11, 14, 22), (240, 244, 248), (140, 152, 170), (60, 230, 140)


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


BOLD, SEMI, SERIF = "archivo-latin-800-normal.ttf", "archivo-latin-600-normal.ttf", "fraunces-latin-900-normal.ttf"


def wrap(d, text, f, width):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if cur and d.textlength(t, font=f) > width:
            lines.append(cur); cur = w
        else:
            cur = t
    return lines + ([cur] if cur else [])


def run(*a):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True)


def dur(p: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True, check=True).stdout.strip())


def restore(f: Path) -> bool:
    """Bring back a Short's video that was cleaned out of the repo after posting (from git history)."""
    if f.exists():
        return True
    rel = f.relative_to(ROOT).as_posix()
    sha = subprocess.run(["git", "log", "--diff-filter=D", "-1", "--format=%H", "--", rel],
                         capture_output=True, text=True, cwd=ROOT).stdout.strip()
    if not sha:
        return False
    data = subprocess.run(["git", "show", f"{sha}^:{rel}"], capture_output=True, cwd=ROOT).stdout
    if not data:
        return False
    f.write_bytes(data)
    return True


def clean_title(t: str) -> str:
    return t.split(" | ")[0].replace("#Shorts", "").strip()


def card(text_big: str, text_small: str, out: Path, sub: bool = False):
    img = Image.new("RGB", (W, H), BG)
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-300, -200, 900, 900), fill=(14, 70, 58)); gd.ellipse((1100, 400, 2300, 1400), fill=(44, 30, 90))
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(200)), 0.6)
    d = ImageDraw.Draw(img)
    d.text((120, 120), "FINANCEHUBW", font=font(BOLD, 40), fill=ACCENT)
    y = 330
    for ln in wrap(d, text_big, font(SERIF, 112), W - 240)[:3]:
        d.text((120, y), ln, font=font(SERIF, 112), fill=INK); y += 128
    d.text((120, y + 40), text_small, font=font(SEMI, 46), fill=MUTED)
    if sub:
        d.rounded_rectangle((120, y + 140, 640, y + 250), 55, fill=(230, 33, 23))
        d.text((380, y + 195), "SUBSCRIBE", font=font(BOLD, 52), fill=(255, 255, 255), anchor="mm")
    img.save(out, quality=95)


def still(png: Path, seconds: float, out: Path):
    run("-loop", "1", "-t", f"{seconds}", "-i", str(png), "-f", "lavfi", "-t", f"{seconds}",
        "-i", "anullsrc=r=44100:cl=stereo", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", "-ac", "2", "-shortest", str(out))


def label(n: int, title: str, out: Path):
    """Transparent overlay: chapter number and title on the left of the frame."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((60, 380, 600, 700), 30, fill=(8, 10, 16, 190))
    d.text((100, 410), f"{n:02d}", font=font(SERIF, 120), fill=ACCENT)
    y = 560
    for ln in wrap(d, title, font(BOLD, 34), 460)[:3]:
        d.text((100, y), ln, font=font(BOLD, 34), fill=INK); y += 42
    img.save(out)


def segment(src: Path, lab: Path, out: Path):
    run("-i", str(src), "-i", str(lab), "-filter_complex",
        "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,gblur=sigma=40,eq=brightness=-0.18[bg];"
        "[0:v]scale=-2:1080[fg];[bg][fg]overlay=(W-w)/2:0[m];[m][1:v]overlay=0:0,fps=30,format=yuv420p[v]",
        "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "160k", str(out))


def thumbnail(title: str, first_thumb: Path | None, out: Path):
    img = Image.new("RGB", (1280, 720), BG)
    if first_thumb and first_thumb.exists():
        t = Image.open(first_thumb).convert("RGB")
        t.thumbnail((420, 720))
        img.paste(t, (1280 - t.width, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 14, 720), fill=ACCENT)
    y = 120
    for ln in wrap(d, title.upper(), font(BOLD, 86), 800)[:4]:
        d.text((60, y), ln, font=font(BOLD, 86), fill=INK); y += 100
    d.text((60, y + 30), "FULL EPISODE", font=font(BOLD, 40), fill=ACCENT)
    img.save(out, quality=92)


def stamp(sec: float) -> str:
    s = int(sec)
    return f"{s // 60}:{s % 60:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", nargs="*")
    ap.add_argument("--title")
    a = ap.parse_args()
    queue = {i["file"]: i for i in json.loads((ROOT / "social" / "queue.json").read_text())["items"]}
    posted = json.loads((ROOT / "social" / "posted.json").read_text())["posted"]
    log = json.loads(LOG.read_text()) if LOG.exists() else {"posted": []}
    used = {f for e in log["posted"] for f in e["files"]}
    if a.files:
        files = [f if f.endswith(".mp4") else f + ".mp4" for f in a.files]
    else:   # real-footage episode if there are enough new clips; otherwise this week's Shorts
        clips = [p["file"] for p in posted if p["file"].startswith("clip_") and p["file"] not in used]
        since = (dt.datetime.utcnow() - dt.timedelta(days=8)).strftime("%Y-%m-%d")
        files = clips[:8] if len(clips) >= 5 else [
            p["file"] for p in posted if p["date"] >= since and not p["file"].startswith(("news_", "loop_"))
            and p["file"] not in used]
    files = [f for f in files if restore(SHORTS / f)]
    if len(files) < 4:
        print(f"long video: only {len(files)} Shorts available, need 4"); return
    items = [queue.get(f, {"file": f, "title": f[:-4].replace("_", " ")}) for f in files]
    titles = [clean_title(i.get("title", "")) for i in items]
    real = all(f.startswith("clip_") for f in files)
    title = a.title or (f"Money History in Real Footage: {len(files)} Moments That Shaped Your Money" if real
                        else f"{len(files)} Money Stories You Need to Hear")
    tmp = Path(tempfile.mkdtemp())
    parts, chapters, t = [], [], 0.0
    mins = int(sum(dur(SHORTS / f) for f in files) // 60) + 2
    card(title, (f"{len(files)} real moments · in their own words · under {mins} minutes" if real
                 else f"{len(files)} stories · real numbers · under {mins} minutes"), tmp / "intro.png")
    still(tmp / "intro.png", 4, tmp / "000.mp4"); parts.append(tmp / "000.mp4")
    chapters.append(f"0:00 Intro"); t += 4
    for n, (f, ti) in enumerate(zip(files, titles), 1):
        label(n, ti, tmp / f"l{n}.png")
        segment(SHORTS / f, tmp / f"l{n}.png", tmp / f"{n:03d}.mp4")
        parts.append(tmp / f"{n:03d}.mp4")
        chapters.append(f"{stamp(t)} {n}. {ti}"); t += dur(tmp / f"{n:03d}.mp4")
    card("Enjoyed this? There's a new one every week.", "Subscribe for daily money stories in under a minute",
         tmp / "outro.png", sub=True)
    still(tmp / "outro.png", 6, tmp / "999.mp4"); parts.append(tmp / "999.mp4")
    chapters.append(f"{stamp(t)} More every week")
    (tmp / "list.txt").write_text("".join(f"file '{p}'\n" for p in parts))
    out = ROOT / "site" / "media" / "long" / f"long_{dt.date.today():%Y%m%d}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    run("-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"), "-c", "copy", "-movflags", "+faststart", str(out))
    thumbnail(title, SHORTS / "thumbs" / files[0].replace(".mp4", ".jpg"), tmp / "thumb.jpg")
    sources = sorted({s for i in items for s in i.get("sources", [])})
    desc = (f"{title}. " + (f"{len(files)} moments from real footage, in the speakers' own words.\n\n" if real
                             else f"{len(files)} true money stories and lessons, with real numbers.\n\n")
            + "\n".join(chapters) + "\n\nSubscribe for a new money story every day: @FinanceHubW\n"
            "Educational content, not financial advice." + ("" if real else " Narration is AI-generated.")
            + "\n\nSources:\n" + "\n".join(f"- {s}" for s in sources[:15])
            + "\n\n#money #finance #history #investing")
    print(title, f"{dur(out) / 60:.1f} min\n" + desc)
    if os.environ.get("DRY_RUN"):
        print("DRY_RUN: built", out); return
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    yt = build("youtube", "v3", cache_discovery=False,
               credentials=Credentials.from_authorized_user_info(json.loads(os.environ["YT_TOKEN_JSON"])))
    r = yt.videos().insert(part="snippet,status", body={
        "snippet": {"title": title[:100], "description": desc, "categoryId": "27",
                    "tags": ["money", "finance", "investing", "personal finance", "money stories", "money mistakes"]},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": not real}},
        media_body=MediaFileUpload(str(out), resumable=True)).execute()
    vid = r["id"]
    try:
        yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(tmp / "thumb.jpg"), mimetype="image/jpeg")).execute()
    except Exception as e:  # noqa: BLE001
        print("thumbnail skipped:", e)
    try:
        sys.path.insert(0, str(ROOT / "social"))
        import yt_extras
        yt_extras.add_to_playlist(yt, vid, {"file": "long_", "title": "Money Stories"} if not real else
                                  {"file": "long_", "title": title, "series": "Money History, in Real Footage"})
    except Exception as e:  # noqa: BLE001
        print("playlist skipped:", e)
    print("long video:", f"https://youtu.be/{vid}")
    log["posted"].append({"date": dt.date.today().isoformat(), "id": vid, "title": title, "files": files})
    LOG.write_text(json.dumps(log, indent=1), encoding="utf-8")
    out.unlink()      # the video lives on YouTube; don't keep 50 MB in the repo


if __name__ == "__main__":
    main()
