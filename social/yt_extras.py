"""YouTube-only extras added at upload time, so every queued Short gets them without re-rendering.

  endcard()      last 2 seconds: a "Subscribe" card ("Part 6 is next" for series episodes)
  add_to_playlist()  files each Short into its series playlist (Money Stories, Compound Interest...),
                     so a viewer who likes one can binge the rest, which is what turns viewers into subscribers
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "motion" / "fonts"
PLAYLISTS = ROOT / "social" / "yt_playlists.json"
W, H = 1080, 1920


def _font(name: str, size: int):
    return ImageFont.truetype(str(FONTS / name), size)


def series_of(item: dict) -> tuple[str, str] | None:
    """(playlist name, short description) for the Short, or None."""
    f, t = item["file"], item.get("title", "")
    if item.get("series") == "Fed Watch":
        return "Fed Watch", "The Federal Reserve in its own words: rates, inflation and jobs, clipped from the source."
    if item.get("series"):
        return item["series"], "Real footage, the speaker's own words: the moments that shaped money."
    if "Money Stories" in t:
        return "Money Stories", "True money stories: the deals, mistakes and fortunes behind them."
    if "Compound Interest" in t or f.startswith("compound_"):
        return "Compound Interest, Explained", "How money grows: the snowball, the rule of 72 and why starting early wins."
    if f.startswith("mistakes_") or "mistake" in t.lower():
        return "Money Mistakes", "The money mistakes that cost the most, by age."
    if f.startswith(("whatif_", "monthly_")) or "now worth this" in t:
        return "What If You Invested?", "$1,000 or $100 a month in famous stocks: what it's worth today (real price data)."
    if f.startswith(("vs_", "race_", "top5_", "realestate_")):
        return "Head to Head", "Stocks, gold, bitcoin and more, raced against each other with real data."
    if f.startswith("news_"):
        return "Today's Money News", "The day's biggest money story in under a minute."
    return "Money Basics", "Simple money rules, explained in under a minute."


def endcard(src: Path, item: dict) -> Path:
    """Copy of the Short with a Subscribe card over the last 2 seconds (needs ffmpeg)."""
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)],
                               capture_output=True, text=True, check=True).stdout.strip())
    m = re.search(r"Money Stories #(\d+)", item.get("title", "")) or re.search(r"Compound Interest #(\d+)", item.get("title", ""))
    line = f"Part {int(m.group(1)) + 1} is next" if m else "A new money story every day"
    card = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    box = (90, 1380, W - 90, 1640)
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((box[0], box[1] + 14, box[2], box[3] + 14), 44, fill=(0, 0, 0, 120))
    card = Image.alpha_composite(card, shadow.filter(ImageFilter.GaussianBlur(18)))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle(box, 44, fill=(255, 255, 255, 255))
    d.rounded_rectangle((box[0] + 40, box[1] + 50, box[0] + 400, box[1] + 150), 50, fill=(230, 33, 23, 255))
    d.text((box[0] + 220, box[1] + 100), "SUBSCRIBE", font=_font("archivo-latin-800-normal.ttf", 44),
           fill=(255, 255, 255), anchor="mm")
    d.text((box[0] + 440, box[1] + 78), "FinanceHubW", font=_font("archivo-latin-800-normal.ttf", 46), fill=(20, 20, 20))
    d.text((box[0] + 440, box[1] + 138), line, font=_font("archivo-latin-600-normal.ttf", 36), fill=(90, 90, 90))
    d.text((W / 2, box[1] + 215), "Tap the channel name above to follow", font=_font("archivo-latin-600-normal.ttf", 30),
           fill=(120, 120, 120), anchor="mm")
    tmp = Path(tempfile.mkdtemp())
    png, out = tmp / "card.png", tmp / src.name
    card.save(png)
    start = max(0.0, dur - 2.0)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-loop", "1", "-t", f"{dur:.2f}", "-i", str(png),
                    "-filter_complex",
                    f"[1:v]format=rgba,fade=t=in:st={start:.2f}:d=0.3:alpha=1[c];"
                    f"[0:v][c]overlay=0:0:enable='gte(t,{start:.2f})'[v]",
                    "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-c:a", "copy", "-shortest", str(out)], check=True)
    return out


def add_to_playlist(yt, video_id: str, item: dict) -> str | None:
    s = series_of(item)
    if not s:
        return None
    name, desc = s
    known = json.loads(PLAYLISTS.read_text()) if PLAYLISTS.exists() else {}
    pid = known.get(name)
    if not pid:   # reuse a playlist with this name if it already exists on the channel
        r = yt.playlists().list(part="snippet", mine=True, maxResults=50).execute()
        pid = next((p["id"] for p in r.get("items", []) if p["snippet"]["title"] == name), None)
    if not pid:
        pid = yt.playlists().insert(part="snippet,status", body={
            "snippet": {"title": name, "description": desc + " New episodes every week. Subscribe: @FinanceHubW"},
            "status": {"privacyStatus": "public"}}).execute()["id"]
    known[name] = pid
    PLAYLISTS.write_text(json.dumps(known, indent=1), encoding="utf-8")
    insert_item(yt, pid, video_id, tries=2)
    return name


def insert_item(yt, pid: str, video_id: str, tries: int = 4) -> None:
    """A just-uploaded video often can't join a playlist yet (YouTube answers 409 'operation aborted' while it is
    still processing), so retry with growing pauses; sync_playlists() catches anything still missing later."""
    import time
    from googleapiclient.errors import HttpError
    for k in range(tries):
        try:
            yt.playlistItems().insert(part="snippet", body={"snippet": {
                "playlistId": pid, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute()
            return
        except HttpError as e:
            if k == tries - 1 or e.resp.status not in (409, 500, 503):
                raise
            time.sleep(20 * (k + 1))


def sync_playlists(yt, posted: list[dict], queue: dict[str, dict]) -> int:
    """Puts every posted Short into its series playlist, oldest first. Returns how many were added."""
    known = json.loads(PLAYLISTS.read_text()) if PLAYLISTS.exists() else {}
    members: dict[str, set] = {}
    added = 0
    for p in sorted(posted, key=lambda x: x["date"]):
        url = p.get("results", {}).get("YouTube", "")
        if not url:
            continue
        vid = url.rstrip("/").rsplit("/", 1)[-1]
        item = {**queue.get(p["file"], {}), **p}
        s = series_of(item)
        if not s:
            continue
        name = s[0]
        pid = known.get(name)
        if pid and pid not in members:
            ids, tok = set(), None
            while True:
                r = yt.playlistItems().list(part="contentDetails", playlistId=pid, maxResults=50,
                                            **({"pageToken": tok} if tok else {})).execute()
                ids |= {i["contentDetails"]["videoId"] for i in r.get("items", [])}
                tok = r.get("nextPageToken")
                if not tok:
                    break
            members[pid] = ids
        if pid and vid in members.get(pid, set()):
            continue
        try:
            if pid:
                insert_item(yt, pid, vid)
            else:
                add_to_playlist(yt, vid, item)
                known = json.loads(PLAYLISTS.read_text())
                pid = known.get(name)
            members.setdefault(pid, set()).add(vid)
            added += 1
            print(f"  playlist {name}: + {p['title'][:60]}")
        except Exception as e:  # noqa: BLE001
            print(f"  playlist {name}: could not add {vid} - {str(e)[:120]}")
    return added
