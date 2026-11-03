"""Probe 3: find more public-domain money footage (Fed press conference archive, newsreels, Prelinger, Commons)."""
import json, re, time
import requests

H = {"User-Agent": "FinanceHubW-research/1.0 (https://github.com/financehubw/FinanceHubW)"}

print("### Federal Reserve press conferences (Brightcove ids)")
dates = ["20110427", "20120913", "20130619", "20141217", "20151216", "20181219", "20200315", "20200429", "20210616",
         "20211215", "20220316", "20220504", "20220615", "20220727", "20220921", "20221102", "20221214", "20230322",
         "20230726", "20240131", "20240918", "20241218", "20250129", "20250618"]
for d in dates:
    u = f"https://www.federalreserve.gov/monetarypolicy/fomcpresconf{d}.htm"
    try:
        t = requests.get(u, headers=H, timeout=40).text
        vid = re.search(r'data-video-id="(\d+)"', t)
        title = re.search(r"<title>([^<]+)</title>", t)
        print(d, vid.group(1) if vid else "NO-VIDEO", "|", (title.group(1).strip() if title else "")[:80])
    except Exception as e:
        print(d, "ERR", e)
    time.sleep(0.5)

def ia(q, n=40, label=""):
    r = requests.get("https://archive.org/advancedsearch.php", headers=H, timeout=60, params={
        "q": q, "fl[]": ["identifier", "title", "year", "licenseurl", "downloads"], "rows": n,
        "sort[]": "downloads desc", "output": "json"})
    print(f"\n### {label or q}")
    for d in r.json()["response"]["docs"]:
        print(f"  {d['identifier']} | {d.get('year','')} | {str(d.get('title',''))[:90]} | {d.get('licenseurl','')} | dl={d.get('downloads')}")

ia('collection:universal_newsreels AND (description:(bank OR banks OR gold OR dollar OR money OR stock OR stocks OR inflation OR depression OR prices OR treasury OR "wall street" OR taxes OR budget OR wages OR "cost of living" OR rationing OR bonds OR coins OR currency OR unemployment OR relief OR economy) OR subject:(economics OR finance OR money OR banking))', 80, "Universal Newsreels: money in description/subject")
ia('collection:prelinger AND (title:(money OR bank OR banking OR credit OR stock OR stocks OR investment OR investing OR thrift OR savings OR budget OR dollar OR inflation OR prices OR consumer OR installment OR insurance OR market OR wall OR economics OR economy OR capitalism OR business) ) AND licenseurl:*publicdomain*', 80, "Prelinger: money titles (public domain)")
ia('mediatype:movies AND (title:("address to the nation" OR "fireside chat" OR "state of the union") ) AND (economy OR economic OR inflation OR tax OR budget OR energy)', 40, "Presidential addresses on archive.org")

print("\n### Wikimedia Commons videos")
api = "https://commons.wikimedia.org/w/api.php"
for q in ["President Reagan Address Nation", "Reagan tax reform", "Address to the Nation economy", "President Obama Weekly Address economy",
          "Carter address energy", "Ford whip inflation now", "Nixon address economy", "Kennedy press conference steel",
          "Eisenhower farewell address", "Federal Reserve Bernanke", "Johnson Great Society", "Roosevelt fireside chat",
          "Truman address inflation", "Bush address economy 2008", "Clinton budget surplus"]:
    for attempt in range(3):
        try:
            r = requests.get(api, headers=H, timeout=60, params={"action": "query", "list": "search", "srnamespace": 6,
                "srsearch": f"{q} filetype:video", "srlimit": 10, "format": "json"})
            if r.status_code != 200 or not r.text.startswith("{"):
                time.sleep(20); continue
            hits = [s["title"] for s in r.json().get("query", {}).get("search", [])]
            print(f"  [{q}]")
            for h in hits: print("     ", h[5:][:110])
            break
        except Exception as e:
            print("  ERR", q, e); time.sleep(20)
    time.sleep(6)
