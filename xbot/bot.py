"""
FinanceHubW auto-poster
-----------------------
Each run:
 1. Reads 150+ finance sources worldwide (sources.py), grouped by region.
 2. Groups reports of the same story from different outlets.
 3. Keeps only trustworthy stories: reported by 2+ independent outlets, or by an
    official body (central bank / regulator), or by a top-tier newsroom.
 4. Claude writes the post; every AI fact-checker (verify.py) must approve it.
 5. Posts to X with the region and the original source credited.

Required secrets: X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN,
X_ACCESS_SECRET. Fact-check keys: GEMINI_API_KEY, GROQ_API_KEY,
OPENROUTER_API_KEY (free), XAI_API_KEY (Grok, optional).
Optional: DRY_RUN=1, POSTS_PER_RUN (default 2), YOUTUBE_URL, X_HANDLE.
"""
from __future__ import annotations

import calendar
import hashlib
import json
import os
import re
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import feedparser
import tweepy

import markets
import newsroom
import verify
from sources import FEEDS, REGIONS, TIER1

HERE = Path(__file__).parent
ROOT = HERE.parent
STATE_FILE = HERE / "state.json"
SITE_FEED = ROOT / "site" / "tweets.json"   # read by the website's "Live from X" calendar
SITE_FEED_KEEP = 3000
HANDLE = os.environ.get("X_HANDLE", "FinanceHubW")

MAX_AGE_HOURS = 4
KEEP_HISTORY = 6000
POSTS_PER_RUN = max(1, min(int(os.environ.get("POSTS_PER_RUN", "2") or 2), 6))
# Hard ceiling across all runs in any 24 hours, so the account stays inside X's API limit.
MAX_POSTS_PER_DAY = max(1, int(os.environ.get("MAX_POSTS_PER_DAY") or 15))
MAX_CANDIDATES = 12        # stories tried per run before giving up
TWEET_LIMIT = 280
URL_LEN = 23               # X counts every link as 23 characters
WRITER_MODEL = os.environ.get("WRITER_MODEL", "claude-haiku-4-5-20251001")

socket.setdefaulttimeout(15)

SKIP_PATTERNS = re.compile(
    r"\b(sponsored|advertorial|partner content|podcast|quiz|live updates?|live blog|"
    r"horoscope|best credit cards?|deal of the day|webinar|how to|opinion|op-ed|"
    r"stocks to buy|top picks|should you buy|price prediction)\b", re.I)

STOPWORDS = set("""a an the and or of to in on for at by with from as is are was were be been
it its this that these those after over amid into up down new says said report reports
could may might will would than more less vs about""".split())


# ------------------------------------------------------------------ state
def load_state() -> dict:
    state = {"posted": [], "last_region": "", "last_category": ""}
    if STATE_FILE.exists():
        try:
            state.update(json.loads(STATE_FILE.read_text()))
        except json.JSONDecodeError:
            print("state.json corrupted, starting fresh", file=sys.stderr)
    return state


def save_state(state: dict) -> None:
    state["posted"] = state["posted"][-KEEP_HISTORY:]
    STATE_FILE.write_text(json.dumps(state, indent=1, ensure_ascii=False))


# ------------------------------------------------------------------ fetching
def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def norm_pub(name: str) -> str:
    n = name.lower()
    n = re.sub(r"\b(the|news|online|\.com|com|rss|feed|latest|top stories|business|markets?)\b", " ", n)
    return re.sub(r"[^a-z0-9 ]", "", n).strip() or name.lower()


PUBLISHER_NAMES = {
    "press releases from rbi": "RBI", "notifications from rbi": "RBI", "reserve bank of india": "RBI",
    "european securities and markets": "ESMA", "financial conduct authority": "FCA",
    "economic times": "Economic Times", "mint": "Mint", "livemint": "Mint",
    "businessday": "BusinessDay", "the guardian": "The Guardian",
}


def display_pub(name: str) -> str:
    """Turns feed titles like 'Economy-News-Economic Times' or 'mint - markets' into
    the outlet's plain name for the post footer."""
    raw = (name or "").strip()
    low = raw.lower()
    for key, nice in PUBLISHER_NAMES.items():
        if key in low:
            return nice
    raw = re.split(r"\s+[-|:\u2013\u2014]\s+", raw)[0]                     # 'mint - markets' -> 'mint'
    raw = re.sub(r"^(?:[A-Za-z]+-)+(?=[A-Z])", "", raw)               # 'Economy-News-Economic Times'
    raw = re.sub(r"\b(NG|RSS|Feed|Latest News|Top Stories)\b", "", raw).strip(" -|:")
    return raw.title() if raw.isupper() and " " in raw else raw


def is_tier1(publisher: str) -> bool:
    p = publisher.lower()
    return any(t in p for t in TIER1)


def _fetch_one(feed_def) -> list[dict]:
    url, region, category, official = feed_def
    try:
        feed = feedparser.parse(url, agent="Mozilla/5.0 (FinanceHubW news bot)")
    except Exception:  # noqa: BLE001
        return []
    now, out = time.time(), []
    feed_name = clean(feed.feed.get("title", "")) or url.split("/")[2]
    google = "news.google.com" in url
    for e in feed.entries[:25]:
        t = e.get("published_parsed") or e.get("updated_parsed")
        ts = time.mktime(t) if t else now - 3600
        if now - ts > MAX_AGE_HOURS * 3600 or ts > now + 3600:
            continue
        title, link = clean(e.get("title")), e.get("link", "")
        if not title or not link.startswith("http"):
            continue
        publisher = feed_name
        if google:  # Google News: "Headline - Publisher"
            src = e.get("source") or {}
            publisher = clean(src.get("title") if isinstance(src, dict) else "") or \
                (title.rsplit(" - ", 1)[1] if " - " in title else "Google News")
            if " - " in title:
                title = title.rsplit(" - ", 1)[0].strip()
        if SKIP_PATTERNS.search(title):
            continue
        out.append({
            "title": title,
            "summary": clean(e.get("summary"))[:700] if not google else "",
            "link": link,
            "publisher": publisher[:40],
            "region": region,
            "category": category,
            "official": official,
            "ts": ts,
        })
    return out


def fetch_all() -> list[dict]:
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(_fetch_one, FEEDS))
    ok = sum(1 for r in results if r)
    items = [s for r in results for s in r]
    print(f"{ok}/{len(FEEDS)} sources returned news, {len(items)} recent items")
    return items


# ------------------------------------------------------------------ grouping
def keywords(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9$%.&]+", title.lower())
    return {w.strip(".") for w in words if len(w) > 2 and w not in STOPWORDS}


def story_key(title: str) -> str:
    return hashlib.sha1(" ".join(sorted(keywords(title))).encode()).hexdigest()[:16]


def similar(a: set[str], b: set[str]) -> bool:
    shared = a & b
    if len(shared) < 3:
        return False
    return len(shared) / min(len(a), len(b)) >= 0.5


def cluster(items: list[dict]) -> list[dict]:
    """Group reports of the same story. Returns stories with all their reports."""
    stories: list[dict] = []
    for it in sorted(items, key=lambda s: s["ts"]):
        kw = keywords(it["title"])
        for st in stories:
            if similar(kw, st["kw"]):
                st["reports"].append(it)
                st["kw"] |= kw if len(st["kw"]) < 25 else set()
                break
        else:
            stories.append({"kw": set(kw), "reports": [it]})
    for st in stories:
        reps = st["reports"]
        # best report to link: official > tier1 > one with a summary > earliest
        reps.sort(key=lambda r: (not r["official"], not is_tier1(r["publisher"]),
                                 not r["summary"], r["ts"]))
        lead = reps[0]
        st.update(lead=lead, key=story_key(lead["title"]),
                  outlets={norm_pub(r["publisher"]) for r in reps},
                  links={r["link"].split("?")[0] for r in reps},
                  region=lead["region"], category=lead["category"],
                  newest=max(r["ts"] for r in reps))
    return stories


def trusted(st: dict) -> bool:
    return (len(st["outlets"]) >= 2 or st["lead"]["official"] or is_tier1(st["lead"]["publisher"]))


PRIORITY_WORDS = {
    "fed": 3, "rate": 3, "rbi": 3, "ecb": 3, "boj": 3, "repo": 3, "inflation": 3, "cpi": 3,
    "gdp": 3, "sebi": 3, "sec": 2, "budget": 3, "tariff": 3, "policy": 2, "sanctions": 2,
    "sensex": 3, "nifty": 3, "s&p": 3, "nasdaq": 3, "dow": 2, "ftse": 2, "nikkei": 2, "hang seng": 2,
    "bitcoin": 3, "ethereum": 2, "crypto": 2, "etf": 2, "stablecoin": 2,
    "earnings": 2, "ipo": 2, "crash": 3, "surge": 2, "record": 2, "plunge": 3, "rally": 2,
    "oil": 2, "gold": 2, "dollar": 2, "rupee": 2, "yuan": 2, "yen": 2, "bond": 2, "yield": 2,
    "recession": 3, "regulation": 2, "ban": 2, "tax": 2, "default": 3, "merger": 2, "acquisition": 2,
}


def score(st: dict) -> float:
    text = " ".join(r["title"] + " " + r["summary"] for r in st["reports"][:3]).lower()
    kw = sum(w for k, w in PRIORITY_WORDS.items() if re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", text))
    coverage = min(len(st["outlets"]), 6)          # widely reported = important
    age_h = (time.time() - st["newest"]) / 3600
    return kw + coverage * 1.5 + (3 if st["lead"]["official"] else 0) - age_h * 1.5


def rank(stories: list[dict], state: dict) -> list[dict]:
    posted = set(state["posted"])
    fresh = [s for s in stories
             if s["key"] not in posted and not (s["links"] & posted) and trusted(s)]
    fresh.sort(key=score, reverse=True)
    # vary regions: prefer a different region from the last post among the top few
    for i, s in enumerate(fresh[:6]):
        if s["region"] != state.get("last_region"):
            fresh.insert(0, fresh.pop(i))
            break
    return fresh


# ------------------------------------------------------------------ writing
WRITE_PROMPT = """You write for @{handle}, a worldwide finance news account on X.
Goal: ANYONE understands the post in 5 seconds, from a school kid to a fund manager.
Plain everyday words. Short sentences. If a finance term is unavoidable, explain it in
2-4 words in brackets, e.g. "repo rate (the rate banks borrow at)".

Fill these fields from the reports below:
- headline: ALL CAPS, max 60 characters, the single most important fact. Start with
  "BREAKING: " only for a just-announced event. No emoji, no flag.
- what: max 90 characters. What happened, in plain words, with the key number.
- means: max 90 characters. Why it matters to an ordinary person, using only a
  widely accepted, general explanation (e.g. "Higher rates usually make loans costlier").
  Never predict prices or say what will happen. Leave empty if nothing safe to say.
- numbers: up to 2 short key figures, each max 45 characters, like "Sensex: 82,450 (+1.2%)".
  Only figures stated in the reports; if reports disagree, leave that figure out.
  Use cashtags for tickers/coins ($BTC, $NVDA, $RELIANCE).
- hashtag: one hashtag (e.g. #Nifty, #Fed, #Crypto, #Gold).
- region: the country/region the story is mainly about, one key from:
  {regions}

Rules: ONLY facts in the reports. No advice, no buy/sell, no predictions, no opinions.
No links or source names. If the story is not about finance, markets, economy,
business, crypto or finance policy, set headline to "SKIP".

Reply with JSON only:
{{"headline": "", "what": "", "means": "", "numbers": [], "hashtag": "", "region": ""}}

Reports:
{reports}"""

LONG_POSTS = os.environ.get("LONG_POSTS") == "1"  # needs X Premium (long posts)


def xlen(text: str) -> int:
    """Length as X counts it: emoji and CJK count as 2, links counted separately."""
    return sum(2 if ord(c) > 0x10FF else 1 for c in text if not 0xFE00 <= ord(c) <= 0xFE0F)


def compose(d: dict, region: str, st: dict, max_len: int) -> str:
    """Builds the fixed layout, dropping optional lines until it fits."""
    flag = REGIONS[region].split(" ", 1)[0]
    place = REGIONS[region].split(" ", 1)[1]
    n = len(st["outlets"])
    stamp = "🏛️ Official" if st["lead"]["official"] else (f"✅ {n} sources" if n >= 2 else "")
    foot = f"📍 {place} · 📰 {display_pub(st['lead']['publisher'])}" + (f" · {stamp}" if stamp else "")

    head = f"{flag} {d['headline']}"
    what = f"📌 {d['what']}" if d.get("what") else ""
    means = f"💡 {d['means']}" if d.get("means") else ""
    nums = [f"📊 {n}" for n in d.get("numbers", [])[:2] if n]
    tag = d.get("hashtag", "").strip()
    tag = tag if tag.startswith("#") else ""

    def build(parts_nums, with_means, with_tag):
        lines = [head, ""] + ([what] if what else []) + parts_nums + ([means] if with_means and means else [])
        body = "\n".join(lines)
        if with_tag and tag:
            body += f"\n{tag}"
        return f"{body}\n\n{foot}"

    # drop least-important pieces first: 2nd number, hashtag, means, 1st number
    for p in [(nums, True, True), (nums[:1], True, True), (nums[:1], True, False),
              (nums[:1], False, False), ([], True, False), ([], False, False)]:
        text = build(*p)
        if xlen(text) + URL_LEN + 1 <= max_len:
            return text
    return build([], False, False)[: max_len - URL_LEN - 2]


def write_post(st: dict, previous: str = "") -> tuple[str, str, str] | None:
    reports = "\n\n".join(f"[{r['publisher']}] {r['title']}\n{r['summary']}" for r in st["reports"][:6])
    prompt = WRITE_PROMPT.format(handle=HANDLE, reports=reports, regions=", ".join(REGIONS))
    if previous:
        prompt += ("\n\nThis is an UPDATE to a story we already posted (below). The headline "
                   "and 'what' must state only what is NEW compared with it. If nothing is "
                   "new, set headline to SKIP.\nEarlier post:\n" + previous)
    reply, writer = verify.write(prompt)
    m = re.search(r"\{.*\}", reply, re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return None
    for k in ("headline", "what", "means", "hashtag"):
        d[k] = re.sub(r"https?://\S+", "", str(d.get(k) or "")).strip()
    d["numbers"] = [str(n).strip() for n in (d.get("numbers") or []) if str(n).strip()]
    if not d["headline"] or d["headline"].upper().startswith("SKIP"):
        return None
    if previous:
        d["headline"] = "🔄 UPDATE: " + d["headline"]
    region = d.get("region") if d.get("region") in REGIONS else st["region"]
    max_len = 1200 if LONG_POSTS else TWEET_LIMIT
    return compose(d, region, st, max_len), region, writer


# ------------------------------------------------------------------ posting
def x_client() -> tweepy.Client:
    return tweepy.Client(
        consumer_key=os.environ["X_API_KEY"], consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"], access_token_secret=os.environ["X_ACCESS_SECRET"])


class RateLimited(Exception):
    pass


def posts_last_24h() -> int:
    try:
        feed = json.loads(SITE_FEED.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return 0
    cutoff = time.time() - 86400
    n = 0
    for p in feed.get("posts", []):
        try:
            if calendar.timegm(time.strptime(p["date"], "%Y-%m-%dT%H:%M:%SZ")) >= cutoff:
                n += 1
        except (KeyError, ValueError):
            pass
    return n


def record_for_site(text: str, tweet_id: str) -> None:
    """Appends a published post to site/tweets.json so the website can show it.
    Never lets a feed problem stop the bot from posting."""
    try:
        feed = {"sample": False, "posts": []}
        if SITE_FEED.exists():
            feed.update(json.loads(SITE_FEED.read_text(encoding="utf-8")))
        feed["sample"] = False
        feed["posts"] = [p for p in feed.get("posts", []) if p.get("id") != tweet_id]
        feed["posts"].append({
            "id": tweet_id,
            "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "text": text,
            "url": f"https://x.com/{HANDLE}/status/{tweet_id}",
        })
        feed["posts"] = feed["posts"][-SITE_FEED_KEEP:]
        SITE_FEED.parent.mkdir(exist_ok=True)
        SITE_FEED.write_text(json.dumps(feed, ensure_ascii=False, separators=(",", ":")),
                             encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"could not update site feed: {e}", file=sys.stderr)


def publish(client: tweepy.Client, text: str, **kw) -> str | None:
    try:
        tweet_id = str(client.create_tweet(text=text, **kw).data["id"])
        record_for_site(text, tweet_id)
        return tweet_id
    except tweepy.Forbidden as e:
        print(f"X rejected post: {e}", file=sys.stderr)
        return None
    except tweepy.TooManyRequests as e:
        raise RateLimited from e
    except tweepy.Unauthorized:
        sys.exit("X credentials invalid: check the X_* secrets and that the app has Read and Write")


# ------------------------------------------------------------------ scheduled specials (IST)
YOUTUBE_URL = os.environ.get("YOUTUBE_URL") or "https://www.youtube.com/@FinanceHubW"
PROMOS = [
    "📺 Markets moving fast? Get the full breakdown in minutes on our YouTube.\n\n"
    "Daily Shorts + deep dives on stocks, crypto and policy 👇",
    "📊 Tweets give you the headline. YouTube gives you the why.\n\n"
    "Subscribe to FinanceHubW for daily market explainers 👇",
    "🇮🇳🌍 Nifty, Sensex, Wall Street, crypto and RBI/Fed policy, explained simply.\n\n"
    "New videos on FinanceHubW 👇",
    "⏱️ 60-second market recaps, every day.\n\nWatch FinanceHubW Shorts on YouTube 👇",
]
# (hour, minute) in IST -> special post type
SPECIALS = {(7, 0): "global_close", (8, 30): "brief", (9, 0): "promo", (13, 0): "word",
            (16, 0): "india_close", (16, 30): "wrap", (20, 0): "promo"}
GLOSSARY = json.loads((HERE / "glossary.json").read_text())


def _fit(lines: list[str], tail: str, max_len: int = TWEET_LIMIT) -> str:
    while lines:
        text = "\n".join(lines) + tail
        if xlen(text) <= max_len:
            return text
        lines = lines[:-1]
    return tail.strip()


def brief(state: dict, title: str) -> str | None:
    cutoff = time.time() - 10 * 3600
    items = [r for r in state.get("recent", []) if r["ts"] >= cutoff]
    items = sorted(items, key=lambda r: -r.get("score", 0))[:3]
    if len(items) < 2:
        return None
    nums = ["1️⃣", "2️⃣", "3️⃣"]
    lines = [title, ""] + [f"{nums[i]} {r['flag']} {r['headline']}" for i, r in enumerate(items)]
    sign = newsroom.pick(newsroom.SIGNOFFS, state, "last_signoff").format(h=HANDLE)
    return _fit(lines, f"\n\n{sign}")


def word_of_day(state: dict) -> str:
    i = state.get("word_index", 0) % len(GLOSSARY)
    state["word_index"] = i + 1
    g = GLOSSARY[i]
    return (f"📚 FINANCE WORD OF THE DAY\n\n🔤 {g['term']}\n💬 {g['simple']}\n"
            f"🧠 {g['example']}\n\n#LearnFinance #{HANDLE}")


def specials_due(state: dict) -> list[str]:
    report = weekly_report(state)
    if report:
        return [report]
    ist = time.gmtime(time.time() + 5.5 * 3600)
    key = (ist.tm_hour, 0 if ist.tm_min < 30 else 30)
    kind = SPECIALS.get(key)
    slot = time.strftime("%Y-%m-%d-", ist) + f"{key[0]}:{key[1]}"
    if not kind or state.get("last_special") == slot:
        return []
    state["last_special"] = slot
    if kind == "promo":
        i = state.get("promo_index", 0) % len(PROMOS)
        state["promo_index"] = i + 1
        return [f"{PROMOS[i]}\n{YOUTUBE_URL}"]
    if kind == "word":
        return [word_of_day(state)]
    if kind in ("india_close", "global_close"):
        t = markets.india_close() if kind == "india_close" else markets.global_close()
        if t and xlen(t) > TWEET_LIMIT:
            lines = t.split("\n")
            while xlen("\n".join(lines)) > TWEET_LIMIT and len(lines) > 6:
                lines.pop(-4)  # drop the last price line, keep legend + hashtags
            t = "\n".join(lines)
        return [t] if t else []
    titles = newsroom.BRIEF_TITLES if kind == "brief" else newsroom.WRAP_TITLES
    text = brief(state, newsroom.pick(titles, state, "last_title_" + kind))
    return [text] if text else []


def remember(state: dict, st: dict, region: str, text: str, tweet_id: str = "") -> None:
    headline = text.split("\n", 1)[0].split(" ", 1)[1] if " " in text.split("\n", 1)[0] else text[:60]
    state.setdefault("recent", []).append({
        "flag": REGIONS[region].split(" ", 1)[0], "headline": headline[:70],
        "score": round(score(st), 2), "ts": time.time(), "tweet_id": tweet_id,
        "kw": sorted(st["kw"])[:30], "text": text, "outlets": len(st["outlets"]),
        "rechecked": False})
    state["recent"] = state["recent"][-60:]


# ------------------------------------------------------------------ transparency
def stat(state: dict, key: str, n: int = 1) -> None:
    week = time.strftime("%Y-%W", time.gmtime(time.time() + 5.5 * 3600))
    w = state.setdefault("stats", {}).setdefault(week, {})
    w[key] = w.get(key, 0) + n
    for old in sorted(state["stats"])[:-6]:
        del state["stats"][old]


def weekly_report(state: dict) -> str | None:
    t = time.gmtime(time.time() + 5.5 * 3600)
    week = time.strftime("%Y-%W", t)
    if not (t.tm_wday == 6 and t.tm_hour == 18) or state.get("last_report") == week:
        return None
    state["last_report"] = week
    w = state.get("stats", {}).get(week, {})
    if not w.get("posted"):
        return None
    return ("🧾 OUR WEEK, IN THE OPEN\n\n"
            f"🔎 Stories scanned: {w.get('scanned', 0):,}\n"
            f"✅ Confirmed by 2+ sources or official: {w.get('trusted', 0):,}\n"
            f"🛑 Blocked by our fact-check: {w.get('blocked', 0):,}\n"
            f"📢 Posted: {w.get('posted', 0):,}\n"
            f"⚠️ Corrections issued: {w.get('corrections', 0)}\n\n"
            "We'd rather be right than first. Every correction is public.")


def log_correction(state: dict, original: str, reason: str, tweet_id: str) -> None:
    path = ROOT / "docs" / "corrections.json"
    try:
        log = json.loads(path.read_text()) if path.exists() else []
    except json.JSONDecodeError:
        log = []
    log.insert(0, {"date": time.strftime("%Y-%m-%d %H:%M IST", time.gmtime(time.time() + 5.5 * 3600)),
                   "original": original.split("\n", 1)[0][:120], "reason": reason,
                   "url": f"https://x.com/{HANDLE}/status/{tweet_id}"})
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(log, indent=1, ensure_ascii=False))
    stat(state, "corrections")


# ------------------------------------------------------------------ corrections
def check_corrections(stories: list[dict], state: dict, x) -> None:
    """Re-checks one recent post per run against newer, wider reporting.
    A correction goes out only if most checkers agree the post was wrong."""
    cutoff = time.time() - 12 * 3600
    for rec in reversed(state.get("recent", [])):
        if rec.get("rechecked") or rec.get("ts", 0) < cutoff or not rec.get("tweet_id"):
            continue
        kw = set(rec.get("kw", []))
        match = next((st for st in stories if similar(kw, st["kw"])
                      and len(st["outlets"]) > rec.get("outlets", 1)), None)
        if not match:
            continue
        rec["rechecked"] = True
        fails, passes, reasons = verify.recheck(rec["text"], match["reports"])
        print(f"re-check of earlier post: {fails} fail / {passes} pass")
        if fails >= 2 and fails > passes:
            reason = reasons[0].rstrip(".")[:150]
            text = (f"⚠️ CORRECTION\n\nNewer reporting doesn't match part of our earlier post: "
                    f"{reason}.\n\nLatest: {match['lead']['title'][:90]}\n{match['lead']['link']}")
            if publish(x, text, in_reply_to_tweet_id=rec["tweet_id"]):
                log_correction(state, rec["text"], reason, rec["tweet_id"])
                print("  -> correction posted")
        return  # at most one re-check per run


# ------------------------------------------------------------------ main
def main() -> None:
    dry = os.environ.get("DRY_RUN") == "1"
    need = [] if dry else ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"]
    missing = [k for k in need if not os.environ.get(k)]
    if missing:
        sys.exit(f"Missing secrets: {', '.join(missing)}")
    checkers = verify.active_checkers()
    if not checkers:
        sys.exit("Missing secrets: add GEMINI_API_KEY, GROQ_API_KEY and OPENROUTER_API_KEY (all free)")
    print(f"models available: {', '.join(checkers)}")

    state = load_state()
    x = None if dry else x_client()
    posted_now = 0
    left_today = MAX_POSTS_PER_DAY - posts_last_24h()
    print(f"daily cap: {MAX_POSTS_PER_DAY}, room left in the last 24h: {max(left_today, 0)}")
    if left_today <= 0 and not dry:
        print("daily cap reached, nothing to do this run")
        save_state(state)
        return

    try:
        for special in specials_due(state):
            print("--- special\n" + special)
            if not dry and publish(x, special):
                posted_now += 1

        poll = newsroom.poll_due(state)
        if poll:
            print("--- poll\n" + poll[0])
            if not dry and publish(x, poll[0], poll_options=poll[1], poll_duration_minutes=1440):
                posted_now += 1

        items = fetch_all()
        seen = set(state.setdefault("seen", []))
        h = lambda u: hashlib.sha1(u.split("?")[0].encode()).hexdigest()[:10]
        new_links = {h(i["link"]) for i in items} - seen
        all_stories = cluster(items)
        if not dry:
            check_corrections(all_stories, state, x)
        stories = rank(all_stories, state)
        new_trusted = [st["key"] for st in stories if st["key"] not in seen]
        stat(state, "scanned", len(new_links))
        stat(state, "trusted", len(new_trusted))
        state["seen"] = (state["seen"] + sorted(new_links) + new_trusted)[-8000:]
        budget = newsroom.posts_this_run(POSTS_PER_RUN, score(stories[0]) if stories else 0)
        budget = min(budget, max(left_today - posted_now, 0)) if not dry else budget
        print(f"{len(stories)} new trusted stories, posting up to {budget} this run")

        news_posted = 0
        for st in stories[:MAX_CANDIDATES]:
            if news_posted >= budget:
                break
            state["posted"] += [st["key"], *st["links"]]  # never retry the same story
            prev = newsroom.match_recent(st["kw"], state.get("recent", []))
            try:
                result = write_post(st, previous=prev["text"] if prev else "")
            except RuntimeError as e:
                print(f"writer unavailable, stopping this run: {e}", file=sys.stderr)
                break
            if not result:
                print(f"skip (off-topic or nothing new): {st['lead']['title']}")
                continue
            body, region, writer = result
            text = f"{body}\n{st['lead']['link']}"

            ok, log = verify.fact_check(text, st["reports"], skip=writer)
            log.insert(0, f"written by {writer}")
            print("---\n" + text + "\n" + "\n".join("  " + l for l in log))
            if not ok:
                print("  -> blocked by fact-check")
                stat(state, "blocked")
                continue
            if dry:
                print("  -> DRY_RUN: not posted")
                news_posted += 1
                continue
            extra = {"quote_tweet_id": prev["tweet_id"]} if prev else {}
            tweet_id = publish(x, text, **extra)
            if tweet_id:
                news_posted += 1
                posted_now += 1
                state["last_region"], state["last_category"] = region, st["category"]
                remember(state, st, region, text, tweet_id)
                stat(state, "posted")
                print(f"  -> posted https://x.com/{HANDLE}/status/{tweet_id}")
    except RateLimited:
        print("X rate limit reached; stopping until the next run", file=sys.stderr)
    finally:
        if not dry:  # a preview must not use up stories
            save_state(state)
    print(f"done: {posted_now} post(s) this run")


if __name__ == "__main__":
    main()
