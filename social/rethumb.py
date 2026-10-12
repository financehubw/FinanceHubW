"""Apply the cover thumbnails to Shorts that were posted before thumbnails existed (YouTube + Facebook)."""
import json, os, sys
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).parent))
import publish as P
queue = {i["file"]: i for i in P.load(P.QUEUE, {"items": []})["items"]}
log = P.load(P.POSTED, {"posted": []})
for e in log["posted"]:
    t = P.thumb_for(queue.get(e["file"], {"file": e["file"]}))
    if not t:
        continue
    yt = e["results"].get("YouTube")
    if yt and os.environ.get("YT_TOKEN_JSON"):
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            api = build("youtube", "v3", cache_discovery=False,
                        credentials=Credentials.from_authorized_user_info(json.loads(os.environ["YT_TOKEN_JSON"])))
            api.thumbnails().set(videoId=yt.rsplit("/", 1)[-1], media_body=MediaFileUpload(str(t), mimetype="image/jpeg")).execute()
            e.setdefault("thumbs", {})["YouTube"] = "ok"
        except Exception as x:
            e.setdefault("thumbs", {})["YouTube"] = str(x)[:200]
    fb = e["results"].get("Facebook")
    if fb and os.environ.get("FB_PAGE_ID"):
      try:
        r = requests.post(f"{P.GRAPH}/{fb}/thumbnails", timeout=60, data={"is_preferred": "true", "access_token": P.page_token()},
                          files={"source": (t.name, t.read_bytes(), "image/jpeg")}).json()
        e.setdefault("thumbs", {})["Facebook"] = "ok" if r.get("success") or r.get("id") else str(r.get("error", r))[:200]
      except Exception as x:
        e.setdefault("thumbs", {})["Facebook"] = str(x)[:200]
    print(e["file"], e.get("thumbs"))
P.POSTED.write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
