"""One-off probe: which free, legal footage sources can GitHub Actions actually reach and download?"""
import json, re, subprocess, sys
import requests

H = {"User-Agent": "FinanceHubW-research/1.0"}

def ia(q, n=12):
    r = requests.get("https://archive.org/advancedsearch.php", headers=H, timeout=60, params={
        "q": q, "fl[]": ["identifier", "title", "year", "collection", "licenseurl", "downloads"],
        "rows": n, "sort[]": "downloads desc", "output": "json"})
    print(f"\n### {q}")
    for d in r.json()["response"]["docs"]:
        col = d.get("collection"); col = ",".join(col) if isinstance(col, list) else col
        print(f"  {d['identifier']} | {d.get('year','')} | {str(d.get('title',''))[:80]} | {col} | {d.get('licenseurl','')} | dl={d.get('downloads')}")

for q in [
    'mediatype:movies AND (nixon) AND (economic OR gold OR dollar OR "wage and price")',
    'mediatype:movies AND (reagan) AND (economy OR inflation OR "economic recovery" OR tax)',
    'mediatype:movies AND ("stock market crash" OR "wall street crash" OR "black tuesday" OR "crash of 1929")',
    'mediatype:movies AND collection:universal_newsreels AND (bank OR banks OR depression OR gold OR inflation OR "wall street" OR stocks OR money)',
    'mediatype:movies AND (bush) AND (2008) AND (economy OR financial OR bailout)',
    'mediatype:movies AND (roosevelt OR fdr) AND (bank OR banking OR "new deal" OR gold)',
    'mediatype:movies AND (carter) AND (energy OR inflation OR "crisis of confidence")',
    'mediatype:movies AND ("gas lines" OR "gasoline shortage" OR "oil crisis" OR "energy crisis")',
    'mediatype:movies AND (inflation OR hyperinflation) AND year:[1920 TO 1985]',
    'mediatype:movies AND (dust bowl OR breadline OR "great depression") AND year:[1929 TO 1945]',
    'mediatype:movies AND (prelinger) AND (money OR banking OR credit OR thrift OR savings OR investing)',
]:
    try:
        ia(q)
    except Exception as e:
        print("  ERR", e)

print("\n### Miller Center page (video links?)")
try:
    t = requests.get("https://millercenter.org/the-presidency/presidential-speeches/august-15-1971-address-nation-new-economic-policy-challenge-peace", headers=H, timeout=60).text
    print(sorted(set(re.findall(r'https?://[^"\'\s<>]+\.(?:mp4|m3u8|mp3)[^"\'\s<>]*', t)))[:10])
    print(sorted(set(re.findall(r'(?:youtube\.com/embed/|youtu\.be/|vimeo\.com/)[\w\-/]+', t)))[:10])
except Exception as e:
    print("ERR", e)

print("\n### Federal Reserve press conference page (video links?)")
for u in ["https://www.federalreserve.gov/monetarypolicy/fomcpresconf20250917.htm", "https://www.federalreserve.gov/videos.htm"]:
    try:
        t = requests.get(u, headers=H, timeout=60).text
        print(u, len(t))
        print(sorted(set(re.findall(r'[^"\'\s<>]+\.(?:mp4|m3u8|vtt)[^"\'\s<>]*', t)))[:15])
        print(sorted(set(re.findall(r'(?:youtube(?:-nocookie)?\.com/embed/|youtu\.be/|brightcove|kaltura|jwplayer|vimeo)[\w\-/.?=]*', t)))[:15])
    except Exception as e:
        print("ERR", e)

print("\n### yt-dlp from Actions (does YouTube block datacenter IPs?)")
def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    print("$", " ".join(cmd[:6]), "...\n", (p.stdout[-1500:] + p.stderr[-1500:]).strip())
run(["yt-dlp", "--flat-playlist", "--playlist-end", "4", "--print", "%(id)s|%(title)s", "https://www.youtube.com/@WhiteHouse/videos"])
run(["yt-dlp", "--flat-playlist", "--playlist-end", "4", "--print", "%(id)s|%(title)s", "https://www.youtube.com/@federalreserve/videos"])
run(["yt-dlp", "-f", "18/best[height<=360]", "--download-sections", "*0-8", "-o", "/tmp/yt_test.%(ext)s",
     "--print", "after_move:filepath", "https://www.youtube.com/@federalreserve/videos", "--playlist-items", "1"])
subprocess.run(["ls", "-la", "/tmp"], check=False)
