"""Views, likes and comments for every posted Short -> docs/yt_stats.json."""
import json, os
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
ROOT = Path(__file__).resolve().parent.parent
log = json.loads((ROOT / "social/posted.json").read_text())["posted"]
ids = {e["results"]["YouTube"].rsplit("/", 1)[-1]: e for e in log if "YouTube" in e["results"]}
yt = build("youtube", "v3", cache_discovery=False, credentials=Credentials.from_authorized_user_info(json.loads(os.environ["YT_TOKEN_JSON"])))
out = []
try:
    r = yt.videos().list(part="statistics,contentDetails,snippet", id=",".join(ids)).execute()
except Exception as e:
    (ROOT / "docs/yt_stats.json").write_text(json.dumps({"error": str(e)[:400]})); raise SystemExit(0)
for v in r.get("items", []):
    s = v["statistics"]
    out.append({"file": ids[v["id"]]["file"], "posted": ids[v["id"]]["date"], "title": v["snippet"]["title"],
                "duration": v["contentDetails"]["duration"], "views": int(s.get("viewCount", 0)),
                "likes": int(s.get("likeCount", 0)), "comments": int(s.get("commentCount", 0))})
try:
    ch = yt.channels().list(part="statistics", mine=True).execute()["items"][0]["statistics"]
except Exception as e:
    ch = {"error": str(e)[:150]}
(ROOT / "docs/yt_stats.json").write_text(json.dumps({"channel": ch, "videos": sorted(out, key=lambda x: x["posted"])}, indent=1))
print(json.dumps(out, indent=1))
