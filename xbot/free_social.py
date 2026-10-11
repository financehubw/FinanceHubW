"""Free places to publish the checked news posts while X has no API credits.

Bluesky   BLUESKY_HANDLE + BLUESKY_APP_PASSWORD   (bsky.app -> Settings -> App passwords)
Threads   THREADS_USER_ID + THREADS_TOKEN          (Meta app with the Threads use case)
Telegram  TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID    (a channel with the bot as admin)
Each one switches itself on when its secrets exist; a failure never stops the others.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import sys

import requests


def _bluesky(text: str) -> str | None:
    h, pw = os.environ.get("BLUESKY_HANDLE"), os.environ.get("BLUESKY_APP_PASSWORD")
    if not (h and pw):
        return None
    s = requests.post("https://bsky.social/xrpc/com.atproto.server.createSession",
                      json={"identifier": h, "password": pw}, timeout=30)
    s.raise_for_status()
    s = s.json()
    text = text[:300]
    b = text.encode()
    facets = [{"index": {"byteStart": len(text[:m.start()].encode()), "byteEnd": len(text[:m.end()].encode())},
               "features": [{"$type": "app.bsky.richtext.facet#link", "uri": m.group(0)}]}
              for m in re.finditer(r"https?://\S+", text)]
    rec = {"$type": "app.bsky.feed.post", "text": text, "facets": facets,
           "createdAt": dt.datetime.utcnow().isoformat() + "Z", "langs": ["en"]}
    r = requests.post("https://bsky.social/xrpc/com.atproto.repo.createRecord", timeout=30,
                      headers={"Authorization": f"Bearer {s['accessJwt']}"},
                      json={"repo": s["did"], "collection": "app.bsky.feed.post", "record": rec})
    r.raise_for_status()
    return r.json().get("uri")


def _threads(text: str) -> str | None:
    uid, tok = os.environ.get("THREADS_USER_ID"), os.environ.get("THREADS_TOKEN")
    if not (uid and tok):
        return None
    c = requests.post(f"https://graph.threads.net/v1.0/{uid}/threads", timeout=30,
                      data={"media_type": "TEXT", "text": text[:500], "access_token": tok}).json()
    if "id" not in c:
        raise RuntimeError(c.get("error", c))
    p = requests.post(f"https://graph.threads.net/v1.0/{uid}/threads_publish", timeout=30,
                      data={"creation_id": c["id"], "access_token": tok}).json()
    if "id" not in p:
        raise RuntimeError(p.get("error", p))
    return p["id"]


def _telegram(text: str) -> str | None:
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        return None
    r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=30,
                      data={"chat_id": chat, "text": text, "disable_web_page_preview": "true"}).json()
    if not r.get("ok"):
        raise RuntimeError(r.get("description"))
    return str(r["result"]["message_id"])


def publish_free(text: str) -> list[str]:
    done = []
    for name, fn in (("Bluesky", _bluesky), ("Threads", _threads), ("Telegram", _telegram)):
        try:
            if fn(text):
                done.append(name)
        except Exception as e:  # noqa: BLE001
            print(f"{name}: failed ({str(e)[:120]})", file=sys.stderr)
    return done
