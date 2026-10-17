"""Replies to new comments on Instagram and YouTube (free models, never Claude).

Every run: reads comments on the 12 most recent Instagram posts and YouTube Shorts, and answers each
new top-level comment from someone else once. Replies are short, warm, factual, in the commenter's
language when it is English/Hinglish, and never give investment advice. Spam, insults, links and
questions about specific trades are skipped (left for a human), not argued with.
State: social/replied.json (ids already handled).
"""
from __future__ import annotations
import json, os, re, sys
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "xbot"))
STATE = ROOT / "social" / "replied.json"
GRAPH = "https://graph.facebook.com/v21.0"
MAX_PER_RUN = 25
SKIP = re.compile(r"https?://|www\.|t\.me|whatsapp|dm me|check my|follow me|telegram|crypto signal|giveaway", re.I)

PROMPT = """You manage replies for FinanceHubW, a finance education page (Instagram Reels and YouTube Shorts).
Post: {post}
Comment from a viewer: {comment}

Write ONE reply, max 25 words, friendly and human, no hashtags, at most one emoji.
- Thank or engage; if they ask a simple factual question about the post, answer in one sentence using only the post's facts.
- Never recommend buying, selling or holding anything, and never predict prices. If asked, say we share education, not advice.
- If the comment is spam, hostile, sexual, political, or you are unsure, reply exactly: SKIP
Reply:"""


def load():
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {"done": []}


def ask(post: str, comment: str) -> str | None:
    import verify
    if SKIP.search(comment) or len(comment.strip()) < 2:
        return None
    text, _ = verify.write(PROMPT.format(post=post[:400], comment=comment[:400]))
    text = text.strip().strip('"').split("\n")[0].strip()
    if not text or "SKIP" in text.upper() or len(text) > 220 or SKIP.search(text):
        return None
    if re.search(r"\b(buy|sell|hold)\b.*\b(now|today|this)\b", text, re.I):
        return None
    return text


def instagram(state, budget):
    ig, tok = os.environ.get("IG_USER_ID"), os.environ.get("META_TOKEN")
    if not (ig and tok):
        return 0
    me = requests.get(f"{GRAPH}/{ig}", params={"fields": "username", "access_token": tok}, timeout=30).json().get("username")
    media = requests.get(f"{GRAPH}/{ig}/media", timeout=30, params={
        "fields": "id,caption", "limit": 12, "access_token": tok}).json().get("data", [])
    n = 0
    for m in media:
        cs = requests.get(f"{GRAPH}/{m['id']}/comments", timeout=30, params={
            "fields": "id,text,username,replies{username}", "access_token": tok}).json().get("data", [])
        for c in cs:
            key = "ig:" + c["id"]
            if n >= budget or key in state["done"] or c.get("username") == me:
                continue
            if any(r.get("username") == me for r in c.get("replies", {}).get("data", [])):
                state["done"].append(key); continue
            reply = ask(m.get("caption") or "", c.get("text", ""))
            state["done"].append(key)
            if reply:
                r = requests.post(f"{GRAPH}/{c['id']}/replies", timeout=30,
                                  data={"message": reply, "access_token": tok}).json()
                print("IG reply:", c.get("text", "")[:60], "->", reply, "|", r.get("id", r))
                n += 1
    return n


def youtube(state, budget):
    if not os.environ.get("YT_TOKEN_JSON"):
        return 0
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    yt = build("youtube", "v3", cache_discovery=False,
               credentials=Credentials.from_authorized_user_info(json.loads(os.environ["YT_TOKEN_JSON"])))
    ch = yt.channels().list(part="id", mine=True).execute()["items"][0]["id"]
    log = json.loads((ROOT / "social" / "posted.json").read_text())["posted"]
    vids = [e["results"]["YouTube"].rsplit("/", 1)[-1] for e in log if "YouTube" in e["results"]][-12:]
    titles = {e["results"]["YouTube"].rsplit("/", 1)[-1]: e["title"] for e in log if "YouTube" in e["results"]}
    n = 0
    for v in vids:
        try:
            res = yt.commentThreads().list(part="snippet", videoId=v, maxResults=50).execute()
        except Exception as e:  # noqa: BLE001  comments off etc.
            print("YT comments:", v, e); continue
        for th in res.get("items", []):
            top = th["snippet"]["topLevelComment"]
            key = "yt:" + top["id"]
            sn = top["snippet"]
            if n >= budget or key in state["done"] or sn.get("authorChannelId", {}).get("value") == ch:
                continue
            state["done"].append(key)
            if th["snippet"].get("totalReplyCount", 0) and th["snippet"].get("canReply") is False:
                continue
            reply = ask(titles.get(v, ""), sn.get("textOriginal", ""))
            if reply:
                yt.comments().insert(part="snippet", body={"snippet": {"parentId": top["id"], "textOriginal": reply}}).execute()
                print("YT reply:", sn.get("textOriginal", "")[:60], "->", reply)
                n += 1
    return n


def main():
    state = load()
    done = 0
    for fn in (instagram, youtube):
        try:
            done += fn(state, MAX_PER_RUN - done)
        except Exception as e:  # noqa: BLE001
            print(f"{fn.__name__}: {e}", file=sys.stderr)
    state["done"] = state["done"][-5000:]
    STATE.write_text(json.dumps(state, indent=0))
    print(f"{done} replies")


if __name__ == "__main__":
    main()
