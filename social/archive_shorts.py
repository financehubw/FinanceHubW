"""Keeps every published Short: video files in a GitHub Release, and a catalog page (SHORTS.md).

Videos are removed from the repository a week or so after posting (social/prune_media.py), because keeping every
file in git made the repo grow by ~200 MB a week. Before that happens, each posted Short is uploaded as an asset of
the `shorts` release, which does not count toward the repository size. Videos removed before this existed are
restored from git history first. SHORTS.md lists every Short with its cover, YouTube link, views and download.

Runs in GitHub Actions (needs GH_TOKEN with contents: write).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
SHORTS = ROOT / "site" / "media" / "shorts"
ARCHIVE = ROOT / "social" / "shorts_archive.json"
CATALOG = ROOT / "SHORTS.md"
REPO = os.environ.get("GITHUB_REPOSITORY", "financehubw/FinanceHubW")
SITE = (os.environ.get("SITE_URL") or "https://financehubw-site.vercel.app").rstrip("/")
API = f"https://api.github.com/repos/{REPO}"
TAG = "shorts"
H = {"Authorization": f"Bearer {os.environ.get('GH_TOKEN', '')}", "Accept": "application/vnd.github+json"}


def load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def release() -> dict:
    r = requests.get(f"{API}/releases/tags/{TAG}", headers=H, timeout=30)
    if r.status_code == 200:
        return r.json()
    r = requests.post(f"{API}/releases", headers=H, timeout=30, json={
        "tag_name": TAG, "name": "Shorts archive", "make_latest": "false",
        "body": "Every FinanceHubW Short as it was published, one video file per Short. "
                "The full list with covers, links and views is in [SHORTS.md](../../blob/main/SHORTS.md)."})
    r.raise_for_status()
    return r.json()


def assets(rel: dict) -> dict[str, str]:
    out, page = {}, 1
    while True:
        r = requests.get(f"{API}/releases/{rel['id']}/assets", headers=H, timeout=30,
                         params={"per_page": 100, "page": page}).json()
        out.update({a["name"]: a["browser_download_url"] for a in r})
        if len(r) < 100:
            return out
        page += 1


def fetch_video(name: str, dest: Path) -> bool:
    """The repo copy, else the website copy, else the last version in git history."""
    if (SHORTS / name).exists():
        dest.write_bytes((SHORTS / name).read_bytes()); return True
    try:
        r = requests.get(f"{SITE}/media/shorts/{name}", timeout=120)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("video"):
            dest.write_bytes(r.content); return True
    except requests.RequestException:
        pass
    rel = f"site/media/shorts/{name}"
    sha = subprocess.run(["git", "log", "--diff-filter=D", "-1", "--format=%H", "--", rel],
                         capture_output=True, text=True, cwd=ROOT).stdout.strip()
    if sha:
        data = subprocess.run(["git", "show", f"{sha}^:{rel}"], capture_output=True, cwd=ROOT).stdout
        if len(data) > 10_000:
            dest.write_bytes(data); return True
    return False


def upload_new() -> dict[str, str]:
    arch = load(ARCHIVE, {})
    rel = release()
    have = assets(rel)
    arch.update({k: v for k, v in have.items() if k.endswith(".mp4")})
    posted = load(ROOT / "social" / "posted.json", {"posted": []})["posted"]
    up = rel["upload_url"].split("{")[0]
    with tempfile.TemporaryDirectory() as td:
        for p in posted:
            name = p["file"]
            if name in arch:
                continue
            tmp = Path(td) / name
            if not fetch_video(name, tmp):
                print("not found anywhere:", name); continue
            r = requests.post(up, headers={**H, "Content-Type": "video/mp4"}, params={"name": name},
                              data=tmp.read_bytes(), timeout=300)
            if r.status_code in (200, 201):
                arch[name] = r.json()["browser_download_url"]
                print("archived", name, f"({tmp.stat().st_size / 1e6:.1f} MB)")
            else:
                print("upload failed", name, r.status_code, r.text[:200])
            tmp.unlink(missing_ok=True)
    ARCHIVE.write_text(json.dumps(dict(sorted(arch.items())), indent=1), encoding="utf-8")
    return arch


def catalog(arch: dict[str, str]) -> None:
    posted = load(ROOT / "social" / "posted.json", {"posted": []})["posted"]
    queue = {i["file"]: i for i in load(ROOT / "social" / "queue.json", {"items": []})["items"]}
    stats = {v["file"]: v for v in load(ROOT / "social" / "yt_stats.json", {}).get("videos", [])}
    sys.path.insert(0, str(ROOT / "social"))
    import mix
    import yt_extras
    names = {"clip": "Real footage", "micro": "10-second loop", "story": "Money story", "lesson": "Money lesson",
             "data": "Data race", "news": "Money news"}
    rows = []
    for p in sorted(posted, key=lambda x: x["date"], reverse=True):
        item = {**queue.get(p["file"], {}), **p}
        yt = p.get("results", {}).get("YouTube", "")
        st = stats.get(p["file"], {})
        thumb = f"site/media/shorts/thumbs/{p['file'][:-4]}.jpg"
        cover = f'<img src="{thumb}" height="112" alt="">' if (ROOT / thumb).exists() else ""
        if yt and cover:
            cover = f'<a href="{yt}">{cover}</a>'
        series = (yt_extras.series_of(item) or ("", ""))[0]
        title = p["title"].replace("|", "·").replace(" #Shorts", "")
        links = " · ".join(x for x in [f"[YouTube]({yt})" if yt else "",
                                         f"[Video]({arch[p['file']]})" if p["file"] in arch else ""] if x)
        views = f"{st['views']:,}" if "views" in st else ""
        watch = f"{st['avg_view_pct']:.0f}%" if st.get("avg_view_pct") is not None else ""
        day = dt.date.fromisoformat(p["date"][:10])
        when = f"{day:%-d %b}" if day.year == dt.date.today().year else f"{day:%-d %b %Y}"
        rows.append(f"| {cover} | **{title}**<br><sub>{names.get(mix.category(item), '')} · {series}</sub> "
                    f"| {when} | {views} | {watch} | {links} |")
    total_views = sum(v.get("views", 0) for v in stats.values())
    text = f"""# Shorts catalog

Every Short FinanceHubW has published, newest first: {len(posted)} so far, {total_views:,} YouTube views in total.
Views and watch-through (the average share of the Short that people watch) come from the YouTube Data and Analytics
APIs and refresh daily. Each video file is kept in the [`shorts` release](../../releases/tag/{TAG}).

_Updated {dt.datetime.utcnow():%d %b %Y, %H:%M} UTC by [`social/archive_shorts.py`](social/archive_shorts.py)._

| Cover | Short | Posted | Views | Watched | Links |
|---|---|---|--:|--:|---|
""" + "\n".join(rows) + "\n"
    CATALOG.write_text(text, encoding="utf-8")
    print("catalog:", len(rows), "Shorts")


if __name__ == "__main__":
    arch = upload_new() if os.environ.get("GH_TOKEN") else load(ARCHIVE, {})
    catalog(arch)
