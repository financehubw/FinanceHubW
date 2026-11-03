"""Probe 2: Wikimedia Commons public-domain money videos, the Fed's Brightcove videos, and transcripts of PD newsreels."""
import json, re, subprocess, os
import requests

H = {"User-Agent": "FinanceHubW-research/1.0 (contact via github.com/financehubw)"}
os.makedirs("/tmp/lab", exist_ok=True)

print("### Wikimedia Commons video search")
api = "https://commons.wikimedia.org/w/api.php"
seen = set()
for q in ["Reagan address economy 1981", "Nixon new economic policy 1971", "Bush address nation economy 2008",
          "Roosevelt inaugural 1933", "fireside chat banking", "stock market crash 1929", "Great Depression newsreel",
          "Liberation Day tariffs", "Federal Reserve chair press conference", "Volcker", "gold standard",
          "inflation speech president", "bank run", "Obama economy speech 2009", "Carter energy speech",
          "Kennedy steel", "Eisenhower economy", "Wall Street 1929", "hyperinflation Germany 1923", "oil crisis 1973"]:
    try:
        r = requests.get(api, headers=H, timeout=60, params={"action": "query", "list": "search", "srnamespace": 6,
            "srsearch": f"{q} filetype:video", "srlimit": 8, "format": "json"}).json()
        titles = [s["title"] for s in r.get("query", {}).get("search", []) if s["title"] not in seen]
        if not titles:
            print(f"  [{q}] none"); continue
        seen.update(titles)
        ii = requests.get(api, headers=H, timeout=60, params={"action": "query", "titles": "|".join(titles),
            "prop": "imageinfo", "iiprop": "size|url|extmetadata|mediatype", "format": "json"}).json()
        print(f"  [{q}]")
        for p in ii["query"]["pages"].values():
            i = (p.get("imageinfo") or [{}])[0]
            em = i.get("extmetadata", {})
            lic = em.get("LicenseShortName", {}).get("value", "")
            print(f"    {p['title'][5:][:90]} | {i.get('width')}x{i.get('height')} | {i.get('duration', '')}s | {round(i.get('size',0)/1e6,1)}MB | {lic}")
    except Exception as e:
        print("  ERR", q, e)

print("\n### Federal Reserve (Brightcove) download test")
try:
    t = requests.get("https://www.federalreserve.gov/monetarypolicy/fomcpresconf20261028.htm", headers=H, timeout=60).text
    ids = sorted(set(re.findall(r'data-video-id="(\d+)"|videoId["\':=\s]+(\d{10,})', t)))
    print("video ids:", ids[:5])
    print("pdfs:", sorted(set(re.findall(r'href="([^"]+\.pdf)"', t)))[:6])
    vid = next((a or b for a, b in ids), None)
    if vid:
        u = f"https://players.brightcove.net/66043936001/default_default/index.html?videoId={vid}"
        p = subprocess.run(["yt-dlp", "--print", "%(title)s|%(duration)s|%(width)sx%(height)s", "--no-simulate",
                            "-f", "best[height<=720]/best", "--download-sections", "*300-310", "-o", "/tmp/lab/fed.%(ext)s", u],
                           capture_output=True, text=True, timeout=600)
        print(p.stdout[-800:], p.stderr[-1200:])
        subprocess.run("ls -la /tmp/lab", shell=True)
except Exception as e:
    print("ERR", e)

print("\n### Universal Newsreels about money (titles)")
r = requests.get("https://archive.org/advancedsearch.php", headers=H, timeout=60, params={
    "q": 'collection:universal_newsreels AND title:(bank OR banks OR gold OR dollar OR money OR market OR stock OR stocks OR inflation OR depression OR prices OR price OR treasury OR wall OR jobless OR relief OR boom OR crash OR tax OR taxes OR budget OR strike OR wages OR economy OR business OR mint OR coins OR currency OR bonds)',
    "fl[]": ["identifier", "title", "year"], "rows": 120, "sort[]": "date asc", "output": "json"})
docs = r.json()["response"]["docs"]
print(len(docs), "items")
for d in docs:
    print(f"  {d['identifier']} | {d['title'][:90]}")

print("\n### Transcripts (faster-whisper base.en) of candidate PD films")
from faster_whisper import WhisperModel
m = WhisperModel("base.en", device="cpu", compute_type="int8")
def files(ident):
    j = requests.get(f"https://archive.org/metadata/{ident}", headers=H, timeout=60).json()
    vids = [f for f in j.get("files", []) if f["name"].lower().endswith((".mp4", ".mpeg4"))]
    vids.sort(key=lambda f: int(f.get("size", 0)))
    return j.get("metadata", {}), vids
for ident in ["1933-03-05_Extra_Special_Roosevelt_Inaugurated", "1933-03-20_Money_Stream_Flow_From_Treasury",
              "1933-11-06_City_Gold_Rush_Starts", "WhatIsMo1947", "Usingthe1947", "WhentheC1975"]:
    try:
        md, vids = files(ident)
        print(f"\n== {ident} | {md.get('title')} | {md.get('date')} | license={md.get('licenseurl')}")
        print("   files:", [(f['name'], round(int(f.get('size', 0))/1e6, 1), f.get('height')) for f in vids][:6])
        if not vids:
            continue
        pick = next((f for f in vids if int(f.get("size", 0)) > 3e6), vids[-1])
        path = f"/tmp/lab/{ident}.mp4"
        with requests.get(f"https://archive.org/download/{ident}/{pick['name']}", headers=H, timeout=300, stream=True) as rr:
            with open(path, "wb") as fh:
                for ch in rr.iter_content(1 << 20):
                    fh.write(ch)
        info = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height,codec_name:format=duration",
                               "-of", "compact", path], capture_output=True, text=True).stdout.strip().replace("\n", " ; ")
        print("   probe:", info)
        segs, _ = m.transcribe(path, vad_filter=True, beam_size=1)
        for s in segs:
            if s.start > 900:
                break
            print(f"   [{s.start:6.1f}-{s.end:6.1f}] {s.text.strip()}")
    except Exception as e:
        print("   ERR", e)
