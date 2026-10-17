"""The Daily: Gemini (free) writes the draft; a Claude review only checks facts, then publishes.

Flow (Tue-Sat):
  7:10 AM IST  GitHub "Daily draft" runs   python magazine/daily_free.py
               -> magazine/daily/D/edition.json + sources.json + slides (status: draft, not posted)
  7:47 AM IST  Claude task reviews edition.json against sources.json: removes or corrects false
               claims only (no new writing), then runs   python magazine/daily_free.py D --publish

Original notes:
The Daily, made for free: news from the X bot's sources, words from free AI models,
design from the fixed template (a copy of the 9 October 2026 edition), checked before it ships.

    python magazine/daily_free.py                 # covers the previous weekday
    python magazine/daily_free.py 2026-10-09      # a given market day
    python magazine/daily_free.py 2026-10-09 --sample   # build only: no site/queue entries

Why the quality holds:
  * The design never changes: every slide is magazine/daily_template/NN.html with only the
    words, numbers and photos swapped in.
  * The writing follows the sample edition (shown to the model as the model answer), with hard
    length limits per field matching the sample.
  * Every number in the text must appear in the source articles, or the edition is rejected.
  * Market figures (slide 6) come from market data, not from AI.
  * Two other free models must pass the whole edition against the sources (same rule as X posts).
  * The renderer fails on any clipped text; the writer then gets one shorter retry.
If any check still fails, nothing is published that day (better no edition than a wrong one).
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "xbot"))
import verify  # noqa: E402

TEMPLATE = ROOT / "magazine" / "daily_template"
PHOTOS = ROOT / "magazine" / "photos"
GREEN, RED, CORAL = "#0B6B3A", "#B4280E", "#FA5B3C"
REGIONS_OK = ["EUROPE", "ASIA", "THE AMERICAS", "MIDDLE EAST", "AFRICA", "ASIA-PACIFIC", "LATIN AMERICA"]
INDIA = re.compile(r"\b(india|indian|sensex|nifty|rbi|rupee|sebi|mumbai|delhi|bse|nse)\b", re.I)

# Field limits, measured from the sample edition (with a little headroom).
LIMITS = {"cover_title": 22, "cover_dek": 80, "big_headline": 90, "big_body": 150, "big_stat": 7,
          "big_stat_l1": 26, "big_stat_l2": 28, "region_text": 100, "pol_headline": 30, "pol_body": 170,
          "pol_stat": 7, "pol_stat_l1": 26, "pol_stat_l2": 30, "biz_headline": 34, "biz_body": 130,
          "s_value": 7, "s_name": 16, "s_note": 18, "up_headline": 40, "up_body": 140}

SAMPLE = {
    "cover_title": "The Iran promise",
    "cover_dek": "One sentence from Washington moved oil and shares around the world.",
    "cover_photo": "pumpjack",
    "big_headline": "America says it “will not attack Iran” before its 3 November elections.",
    "big_body": "President Trump's statement eased fears that fighting would cut off oil from the Middle East. Investors everywhere relaxed a little.",
    "big_stat": "$100+", "big_stat_l1": "Oil eased, but a barrel", "big_stat_l2": "still costs more than this",
    "big_photo": "tanker",
    "regions": [{"name": "EUROPE", "text": "Shares rose about 1% in London, Paris and Frankfurt as oil cooled."},
                {"name": "ASIA", "text": "Hong Kong's main share index jumped 1.8%. Japan's ended flat."},
                {"name": "THE AMERICAS", "text": "US shoppers are gloomier: a University of Michigan survey of their mood fell to 46.3 from 48.1."}],
    "pol_headline": "Rates are still the worry",
    "pol_body": "Americans now expect prices to rise 4.7% over the next year. Traders see about an 80% chance that the US central bank raises interest rates again in December.",
    "pol_stat": "5.24%", "pol_stat_l1": "what the US government", "pol_stat_l2": "pays to borrow for 10 years",
    "pol_photo": "fed",
    "biz_headline": "SpaceX rattles the phone giants",
    "biz_body": "It agreed to buy American mobile airwaves, a step toward becoming a phone company. Regulators still have to approve it.",
    "biz_stats": [{"value": "-13.3%", "name": "T-Mobile US", "note": "gets a new rival"},
                  {"value": "+15.6%", "name": "Crown Castle", "note": "owns the towers"}],
    "biz_photo": "rocket",
    "up_headline": "Tuesday: America's big banks report",
    "up_body": "Citigroup, JPMorgan and Wells Fargo publish their profits on 13 October, the first real look at how the economy is holding up.",
    "up_photo": "nyse",
    "sources_used": ["Associated Press", "TheStreet", "Yahoo Finance"],
    "story_ids": [3, 7, 12, 15, 21, 26, 30],
}


# ------------------------------------------------------------------ inputs
def market_day(arg: str | None) -> dt.date:
    if arg:
        return dt.date.fromisoformat(arg)
    d = dt.datetime.utcnow().date()          # today's edition (published the same evening, Mon-Fri)
    while d.weekday() > 4:
        d -= dt.timedelta(days=1)
    return d


def photo_library() -> dict[str, dict]:
    lib = {}
    for line in (PHOTOS / "CREDITS.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*color/([\w-]+)\.jpg\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|", line)
        if m:
            lib[m.group(1)] = {"subject": m.group(2), "author": m.group(3), "licence": m.group(4)}
    return lib


def gather_news(day: dt.date) -> list[dict]:
    import bot  # the X bot's fetcher, sources and trust rules
    bot.MAX_AGE_HOURS = 16   # today's news only, nothing from yesterday
    items = [i for i in bot.fetch_all() if not INDIA.search(i["title"] + " " + i["summary"])
             and "India" not in i.get("region", "")]
    stories = [s for s in bot.cluster(items) if bot.trusted(s)]
    stories.sort(key=bot.score, reverse=True)
    out = []
    for s in stories[:40]:
        reps = s["reports"][:4]
        out.append({"id": len(out) + 1, "region": s["region"], "category": s["category"],
                    "outlets": sorted(s["outlets"])[:5],
                    "reports": [{"publisher": bot.display_pub(r["publisher"]), "title": r["title"],
                                 "summary": r["summary"][:500], "link": r["link"]} for r in reps]})
    return out


def market_rows(day: dt.date) -> tuple[str, list[dict]]:
    import yfinance as yf
    want = [("^GSPC", "US shares", "(the S&amp;P 500) closed at {v:,.0f}."),
            ("GC=F", "Gold", "{verb} to about ${v:,.0f} an ounce."),
            ("BTC-USD", "Bitcoin", "ended the day at ${v:,.0f}.")]
    rows = []
    for tick, label, tpl in want:
        h = yf.Ticker(tick).history(start=(day - dt.timedelta(days=7)).isoformat(),
                                    end=(day + dt.timedelta(days=1)).isoformat(), auto_adjust=False)["Close"].dropna()
        h = h[[i.date() <= day for i in h.index]]
        if len(h) < 2:
            continue
        v, p = float(h.iloc[-1]), float(h.iloc[-2])
        ch = (v - p) / p * 100
        closed_today = h.index[-1].date() == day
        verb = "rose" if ch >= 0 else "fell"
        text = f"<strong>{label}</strong> " + tpl.format(v=v, verb=verb)
        if not closed_today and tick == "^GSPC":    # evening in India = before or at the US open
            text = f"<strong>US shares</strong> (the S&amp;P 500) last closed at {v:,.0f}."
        elif tick == "BTC-USD":
            text = f"<strong>Bitcoin</strong> trades at about ${v:,.0f}."
        elif tick == "GC=F" and not closed_today:
            text = f"<strong>Gold</strong> trades at about ${v:,.0f} an ounce."
        rows.append({"chg": ("+" if ch >= 0 else "−") + f"{abs(ch):.1f}%", "color": GREEN if ch >= 0 else RED,
                     "text": text})
    return "Shares, gold, bitcoin", rows


# ------------------------------------------------------------------ writing
PROMPT = """You are the editor of "The Daily", a 7-slide Instagram edition about WORLD finance for ordinary people.
Write today's edition for {day_long} as JSON with EXACTLY the same keys as the model answer below.
Match the model answer's style: plain words, short sentences, every term explained in the same sentence,
calm and precise, no hype, no emojis, no buy/sell advice. It must read as well as the model answer.

HARD RULES
- Use ONLY facts and numbers that appear in the SOURCES below. Never invent, estimate, round differently
  or calculate a number. If you cannot find a number for a stat field, pick a different story.
- Do NOT cover India at all.
- big story = the most important world finance story in the sources. regions = three DIFFERENT regions,
  each from a different story, mixing economy, policy and business (not only share prices).
  pol = a central-bank, government or economy story. biz = one company or deal story with two figures.
  up = the next dated event mentioned in the sources (with its day or date).
- Every story you use must be a different story. Do not repeat the big story anywhere else.
- Stats ("big_stat", "pol_stat", biz "value") are a single figure like "$100+", "5.24%", "+15.6%", "-13.3%".
- Region names must be one of: {regions}. (Bermuda, Canada, Brazil, the US -> THE AMERICAS; Japan, China -> ASIA; UK, Germany -> EUROPE.)
- Photos: choose for each *_photo the key from PHOTOS whose subject matches that slide's story; use each key once.
- Length limits (characters, hard maximum): {limits}
- "sources_used": the outlets you took facts from. "story_ids": the #numbers of EVERY source story you used.

MODEL ANSWER (9 October 2026):
{sample}

PHOTOS (key: subject):
{photos}

SOURCES (stories reported on or just before {day_long}):
{sources}
{extra}
Reply with the JSON only."""


def parse_json(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON in the reply")
    return json.loads(m.group(0))


WRITERS = {   # free writers we can test; DAILY_WRITER picks one
    "Gemini": ("GEMINI_API_KEY", lambda p: verify._gemini(p, 4000)),
    "GPT-OSS": ("GROQ_API_KEY", lambda p: verify._groq_oss(p, 4000)),
    "Qwen": ("GROQ_API_KEY", lambda p: verify._oa("Qwen", verify.GROQ, "GROQ_API_KEY", ["qwen/qwen3.8-27b"], 4000)(p, 4000)),
}
CHECKER_OF = {"Gemini": "Gemini", "GPT-OSS": "Groq GPT-OSS", "Qwen": "Groq Qwen"}


def llm(prompt: str) -> tuple[str, str]:
    order = [os.environ["DAILY_WRITER"]] if os.environ.get("DAILY_WRITER") else ["Gemini", "GPT-OSS"]
    for name in order:
        env, fn = WRITERS[name]
        if not os.environ.get(env):
            continue
        try:
            return fn(prompt), CHECKER_OF[name]
        except Exception as e:  # noqa: BLE001
            print(f"  writer {name} unavailable: {verify._detail(e)}", file=sys.stderr)
    raise RuntimeError("no free writer model answered")


def numbers(text: str) -> set[str]:
    return {n.replace(",", "").lstrip("0") or "0" for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def validate(ed: dict, src_text: str, lib: dict) -> list[str]:
    errs = []
    flat = []
    for k in ("cover_title", "cover_dek", "big_headline", "big_body", "big_stat", "big_stat_l1", "big_stat_l2",
              "pol_headline", "pol_body", "pol_stat", "pol_stat_l1", "pol_stat_l2", "biz_headline", "biz_body",
              "up_headline", "up_body"):
        v = ed.get(k)
        if not isinstance(v, str) or not v.strip():
            errs.append(f"{k} is missing")
            continue
        if len(v) > int(LIMITS[k] * 1.15) + 1:
            errs.append(f"{k} is {len(v)} characters, limit {LIMITS[k]}")
        flat.append(v)
    regs = ed.get("regions") or []
    if len(regs) != 3 or len({r.get("name") for r in regs}) != 3:
        errs.append("regions must be three different regions")
    for r in regs:
        if r.get("name") not in REGIONS_OK:
            errs.append(f"region name {r.get('name')!r} not allowed")
        if len(r.get("text", "")) > int(LIMITS["region_text"] * 1.15):
            errs.append(f"region text too long ({r.get('name')})")
        flat.append(r.get("text", ""))
    stats = ed.get("biz_stats") or []
    if len(stats) != 2:
        errs.append("biz_stats must have two figures")
    for s in stats:
        for f, lim in (("value", "s_value"), ("name", "s_name"), ("note", "s_note")):
            if len(s.get(f, "")) > int(LIMITS[lim] * 1.2) + 1 or not s.get(f):
                errs.append(f"biz_stats {f} missing or too long")
        flat += [s.get("value", ""), s.get("name", ""), s.get("note", "")]
    photos = [ed.get(k) for k in ("cover_photo", "big_photo", "pol_photo", "biz_photo", "up_photo")]
    if any(p not in lib for p in photos):
        errs.append("a photo key is not in the library")
    if len(set(photos)) != 5:
        errs.append("each photo must be used once")
    text = " ".join(flat)
    if INDIA.search(text):
        errs.append("mentions India")
    src_nums = numbers(src_text)
    missing = sorted(n for n in numbers(text) if n not in src_nums and not re.fullmatch(r"20\d\d|[1-9]|1[0-9]|2[0-9]|3[01]", n))
    if missing:
        errs.append("numbers not found in the sources: " + ", ".join(missing[:8]))
    return errs


SHORTEN = """Shorten each text below to AT MOST the given number of characters. Keep the meaning,
keep every number exactly as written, plain words, no new facts. Reply with JSON mapping each id to its new text.
{items}"""


def shorten(ed: dict) -> dict:
    """Fixes over-long fields with one focused call instead of rewriting the edition."""
    todo = {}
    for k, lim in LIMITS.items():
        if isinstance(ed.get(k), str) and len(ed[k]) > lim:
            todo[k] = (ed[k], lim)
    for i, r in enumerate(ed.get("regions") or []):
        if len(r.get("text", "")) > LIMITS["region_text"]:
            todo[f"region{i}"] = (r["text"], LIMITS["region_text"])
    for i, st in enumerate(ed.get("biz_stats") or []):
        for f, lim in (("name", "s_name"), ("note", "s_note")):
            if len(st.get(f, "")) > LIMITS[lim]:
                todo[f"biz{i}_{f}"] = (st[f], LIMITS[lim])
    if not todo:
        return ed
    items = json.dumps({k: {"text": t, "max_characters": n} for k, (t, n) in todo.items()}, ensure_ascii=False, indent=1)
    for _ in range(2):
        try:
            new = parse_json(llm(SHORTEN.format(items=items))[0])
        except Exception:  # noqa: BLE001
            continue
        for k, v in new.items():
            v = v["text"] if isinstance(v, dict) else v
            if not isinstance(v, str) or k not in todo or len(v) > todo[k][1] or numbers(v) - numbers(todo[k][0]):
                continue
            if k in LIMITS:
                ed[k] = v
            elif k.startswith("region"):
                ed["regions"][int(k[6:])]["text"] = v
            elif re.fullmatch(r"biz\d_(name|note)", k):
                i, f = k[3:].split("_", 1)
                ed["biz_stats"][int(i)][f] = v
            else:
                ed[k] = v
        todo = {k: t for k, t in todo.items() if True}
        break
    return ed


def flatten(ed: dict) -> str:
    r = ed["regions"]
    s = ed["biz_stats"]
    return "\n".join([
        f"Cover: {ed['cover_title']}. {ed['cover_dek']}",
        f"Big story: {ed['big_headline']} {ed['big_body']} Figure: {ed['big_stat']} = {ed['big_stat_l1']} {ed['big_stat_l2']}.",
        *[f"{x['name'].title()}: {x['text']}" for x in r],
        f"Money and policy: {ed['pol_headline']}. {ed['pol_body']} Figure: {ed['pol_stat']} = {ed['pol_stat_l1']} {ed['pol_stat_l2']}.",
        f"Business: {ed['biz_headline']}. {ed['biz_body']} " + "; ".join(f"{x['name']} {x['value']} ({x['note']})" for x in s),
        f"Up next: {ed['up_headline']}. {ed['up_body']}",
    ])


# ------------------------------------------------------------------ building
def credit(lib: dict, key: str) -> str:
    p = lib[key]
    lic = p["licence"].replace("Public domain", "public domain")
    return f"File photo: {p['author']}, {lic}"


def fill(ed: dict, day: dt.date, lib: dict, mkt_title: str, mkt: list[dict]) -> dict[str, str]:
    e = lambda s: html.escape(s, quote=False)  # noqa: E731
    sign = lambda v: v.replace("-", "−")  # noqa: E731  a real minus sign
    col = lambda v: RED if v.strip().startswith(("-", "−")) else GREEN  # noqa: E731
    slots = {"BAND_DATE": day.strftime("%a %-d %b %Y").upper(), "DAY_NUM": day.strftime("%d"),
             "DOW": day.strftime("%a").upper(), "MON": day.strftime("%b").upper(), "YEAR": str(day.year),
             "COVER_TITLE": e(ed["cover_title"]), "COVER_DEK": e(ed["cover_dek"]),
             "BIG_HEADLINE": e(ed["big_headline"]), "BIG_BODY": e(ed["big_body"]), "BIG_STAT": e(sign(ed["big_stat"])),
             "BIG_STAT_L1": e(ed["big_stat_l1"]), "BIG_STAT_L2": e(ed["big_stat_l2"]),
             "POL_HEADLINE": e(ed["pol_headline"]), "POL_BODY": e(ed["pol_body"]), "POL_STAT": e(sign(ed["pol_stat"])),
             "POL_STAT_L1": e(ed["pol_stat_l1"]), "POL_STAT_L2": e(ed["pol_stat_l2"]),
             "BIZ_HEADLINE": e(ed["biz_headline"]), "BIZ_BODY": e(ed["biz_body"]),
             "UP_HEADLINE": e(ed["up_headline"]), "UP_BODY": e(ed["up_body"]), "MKT_TITLE": mkt_title}
    for i, r in enumerate(ed["regions"], 1):
        slots[f"R{i}_NAME"], slots[f"R{i}_TEXT"] = e(r["name"]), e(r["text"])
    for i, s in enumerate(ed["biz_stats"], 1):
        slots.update({f"S{i}_VALUE": e(sign(s["value"])), f"S{i}_COLOR": col(s["value"]),
                      f"S{i}_NAME": e(s["name"]), f"S{i}_NOTE": e(s["note"])})
    for i, m in enumerate((mkt + [{"chg": "", "color": GREEN, "text": ""}] * 3)[:3], 1):
        slots.update({f"M{i}_CHG": m["chg"], f"M{i}_COLOR": m["color"], f"M{i}_TEXT": m["text"]})
    for n, k in (("1", "cover_photo"), ("2", "big_photo"), ("4", "pol_photo"), ("5", "biz_photo"), ("7", "up_photo")):
        key = ed[k]
        slots[f"P{n}_FILE"] = f"{key}.jpg"
        slots[f"P{n}_ALT"] = e(lib[key]["subject"])
        slots[f"P{n}_CREDIT"] = e(credit(lib, key))
    return slots


def build(ed: dict, day: dt.date, lib: dict, mkt_title: str, mkt: list[dict], name: str = "") -> tuple[bool, str]:
    name = name or day.isoformat()
    folder = ROOT / "magazine" / "daily" / name / "slides"
    folder.mkdir(parents=True, exist_ok=True)
    slots = fill(ed, day, lib, mkt_title, mkt)
    for t in sorted(TEMPLATE.glob("*.html")):
        s = t.read_text(encoding="utf-8")
        for k, v in slots.items():
            s = s.replace(f"[[{k}]]", v)
        left = re.findall(r"\[\[\w+\]\]", s)
        if left:
            return False, f"{t.name}: unfilled {left}"
        (folder / t.name).write_text(s, encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "magazine" / "render.py"), "daily", name],
                       capture_output=True, text=True)
    return r.returncode == 0, (r.stderr or r.stdout)[-800:]


def caption(ed: dict, day: dt.date, lib: dict) -> str:
    keys = [ed[k] for k in ("cover_photo", "big_photo", "pol_photo", "biz_photo", "up_photo")]
    photos = "; ".join(f"{lib[k]['author']} ({lib[k]['licence']})" for k in keys)
    src = ", ".join(dict.fromkeys(ed.get("sources_used") or []))
    return (f"The Daily, {day.strftime('%A %-d %B')}: {ed['cover_title']}. {ed['cover_dek']}\n\n"
            "Swipe for the big story, three regions in three lines, money and policy, business, markets in one look "
            "and what to watch next. The full story of the week is in The Weekly.\n\n"
            f"Sources: {src}. Market data: Yahoo Finance.\nPhotos via Wikimedia Commons: {photos}.\n\n"
            "Information only, not investment advice.\n"
            f"© {day.year} FinanceHubW. All rights reserved. Share with credit to @financehubw.\n\n"
            "#finance #economy #worldnews #markets #money")


def upsert(path: Path, key: str, entry: dict, field: str = "date", keep: int = 30) -> None:
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {key: []}
    lst = [x for x in data.get(key, []) if x.get(field) != entry[field]] + [entry]
    lst.sort(key=lambda x: x[field])
    data[key] = lst[-keep:]
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


PLAN = """You are the editor of "The Daily", a 7-slide Instagram edition about WORLD finance for ordinary people,
for {day_long}. Pick the stories for each slot from the SOURCES (by #number). Do NOT pick anything about India.
- big: the most important world finance story.
- r1, r2, r3: three stories from three DIFFERENT regions, mixing economy, policy and business (not only share prices).
- pol: a central-bank, government or economy story. biz: one company or deal story that has figures.
- up: a story that mentions a dated upcoming event.
- backups: 6 more good stories, best first.
Every pick must be a different story. Prefer stories reported by several outlets and with clear figures.
Also choose photos (keys from PHOTOS, each used once) whose subject matches: cover (for the big story), big, pol, biz, up.
Reply with JSON only, like:
{{"big": 4, "r1": 9, "r2": 13, "r3": 2, "pol": 7, "biz": 11, "up": 20, "backups": [5, 8, 15, 17, 22, 25],
 "photos": {{"cover": "pumpjack", "big": "tanker", "pol": "fed", "biz": "rocket", "up": "nyse"}}}}

PHOTOS (key: subject):
{photos}

SOURCES:
{sources}"""

SLOT = """You write one slide of "The Daily", a world-finance Instagram edition for ordinary people.
Write it in the same style and at most the same length as the MODEL SLIDE: plain words, short sentences,
every term explained in the same sentence, calm and precise, no hype, no emojis, no advice or predictions.
The big figure fields must be a meaningful amount with a unit (money, percent, tonnes, barrels...), never a year or a count like "12" or "1".
Use ONLY facts and numbers stated in the SOURCE below. Never add background, causes, reactions or
numbers that the source does not state. Copy numbers exactly. Do not mention India.
Hard length limits in characters: {limits}
{extra}
MODEL SLIDE (JSON, same keys you must return):
{sample}

SOURCE ({region}; reported by {outlets}):
{source}

Reply with the JSON only."""

SLOT_FIELDS = {
    "big": ["cover_title", "cover_dek", "big_headline", "big_body", "big_stat", "big_stat_l1", "big_stat_l2"],
    "pol": ["pol_headline", "pol_body", "pol_stat", "pol_stat_l1", "pol_stat_l2"],
    "biz": ["biz_headline", "biz_body", "biz_stats"],
    "up": ["up_headline", "up_body"],
    "r1": ["region"], "r2": ["region"], "r3": ["region"],
}


def slot_sample(slot: str) -> dict:
    if slot.startswith("r"):
        return {"region": SAMPLE["regions"][int(slot[1]) - 1]}
    return {k: SAMPLE[k] for k in SLOT_FIELDS[slot]}


def slot_limits(slot: str) -> dict:
    if slot.startswith("r"):
        return {"region.name": "one of " + ", ".join(REGIONS_OK), "region.text": LIMITS["region_text"]}
    if slot == "biz":
        return {"biz_headline": LIMITS["biz_headline"], "biz_body": LIMITS["biz_body"],
                "biz_stats[].value": LIMITS["s_value"], "biz_stats[].name": LIMITS["s_name"], "biz_stats[].note": LIMITS["s_note"]}
    return {k: LIMITS[k] for k in SLOT_FIELDS[slot]}


def story_text(st: dict) -> str:
    return "\n".join(f"- [{r['publisher']}] {r['title']}. {r['summary']}" for r in st["reports"])


def slot_errors(slot: str, out: dict, st: dict) -> list[str]:
    errs, texts = [], []
    if slot.startswith("r"):
        r = out.get("region") or {}
        if r.get("name") not in REGIONS_OK:
            errs.append(f"region name must be one of {REGIONS_OK}")
        if not r.get("text") or len(r["text"]) > LIMITS["region_text"]:
            errs.append(f"region text must be 1-{LIMITS['region_text']} characters")
        texts.append(r.get("text", ""))
    else:
        for k in SLOT_FIELDS[slot]:
            if k == "biz_stats":
                bs = out.get(k) or []
                if len(bs) != 2:
                    errs.append("biz_stats needs exactly two figures")
                for b in bs:
                    for f, lim in (("value", "s_value"), ("name", "s_name"), ("note", "s_note")):
                        if not b.get(f) or len(b[f]) > LIMITS[lim]:
                            errs.append(f"biz_stats {f} must be 1-{LIMITS[lim]} characters")
                        texts.append(b.get(f, ""))
                continue
            v = out.get(k)
            if not isinstance(v, str) or not v.strip() or len(v) > LIMITS[k]:
                errs.append(f"{k} must be 1-{LIMITS[k]} characters (it is {len(v) if isinstance(v, str) else 0})")
            texts.append(v if isinstance(v, str) else "")
    for k in ("big_stat", "pol_stat"):
        if k in SLOT_FIELDS.get(slot, []) and not good_stat(out.get(k, "")):
            errs.append(f"{k} must be a meaningful figure with a unit, like $100+, 5.24%, €3bn or 1.5 million (not a year or a bare count)")
    if slot == "biz":
        for b in out.get("biz_stats") or []:
            if not good_stat(b.get("value", "")):
                errs.append("each biz_stats value must be a figure with a unit, like -13.3% or $4bn (not a bare count)")
    text = " ".join(texts)
    if TAKEN and slot != "big":
        import bot
        overlap = bot.keywords(text) & TAKEN
        if len(overlap) >= 3:
            errs.append("this repeats the big story (" + ", ".join(sorted(overlap)[:4]) + "); it must be a different story")
    if INDIA.search(text):
        errs.append("do not mention India")
    src = numbers(story_text(st))
    bad = sorted(n for n in numbers(text) if n not in src and not re.fullmatch(r"20\d\d|[1-9]|[12][0-9]|3[01]", n))
    if bad:
        errs.append("these numbers are not in the source: " + ", ".join(bad))
    return errs


TAKEN: set[str] = set()


def good_stat(v: str) -> bool:
    v = v.strip().replace("−", "-")
    if not re.fullmatch(r"[+-]?[$€£¥]?\d[\d,]*(\.\d+)?\s?(%|bn|billion|m|million|tn|trillion|k|K|bp|pts?)?\+?", v):
        return False
    if re.fullmatch(r"(19|20)\d\d", v):
        return False
    return bool(re.search(r"[%$€£¥]|bn|billion|million|tn|trillion|[kK]\b|bp|pt|\.", v)) or int(re.sub(r"\D", "", v) or 0) >= 1000


def slot_check_text(slot: str, out: dict) -> str:
    if slot.startswith("r"):
        return f"{out['region']['name'].title()}: {out['region']['text']}"
    if slot == "biz":
        return f"{out['biz_headline']}. {out['biz_body']} " + "; ".join(f"{b['name']} {b['value']} ({b['note']})" for b in out["biz_stats"])
    parts = [out[k] for k in SLOT_FIELDS[slot]]
    return " ".join(parts)


CHECK = """You are a strict financial fact-checker. Below is the text of one magazine slide and the source
reporting it is based on. Answer PASS only if every factual claim (numbers, names, places, directions like
rise/fall, dates, who said or did what) is supported by the sources. Short plain-English explanations of a
term (for example "a central bank, which sets interest rates") are fine. Answer FAIL if anything is
unsupported, exaggerated, contradicted or phrased as advice or a prediction.

Reply with JSON only: {{"verdict": "PASS" or "FAIL", "reason": "<one short sentence>"}}

SLIDE TEXT:
{post}

SOURCES:
{sources}"""


def write_slot(slot: str, st: dict, writer_skip: list) -> tuple[dict | None, str]:
    extra, fallback = "", None
    for attempt in range(3):
        prompt = SLOT.format(limits=json.dumps(slot_limits(slot)), extra=extra,
                             sample=json.dumps(slot_sample(slot), ensure_ascii=False, indent=1),
                             region=st["region"], outlets=", ".join(st["outlets"]), source=story_text(st))
        reply, writer = llm(prompt)
        try:
            out = parse_json(reply)
        except Exception:  # noqa: BLE001
            print(f"  {slot}: {writer} reply was not JSON: {reply[:160]!r}", file=sys.stderr)
            extra = "\nYour last reply was not valid JSON.\n"
            continue
        errs = slot_errors(slot, out, st)
        if errs:
            print(f"  {slot}: rejected: {'; '.join(errs)[:200]}", file=sys.stderr)
            extra = "\nYour last answer was rejected: " + "; ".join(errs) + ". Last answer: " + json.dumps(out, ensure_ascii=False) + "\n"
            continue
        ok, log = verify.fact_check(slot_check_text(slot, out), st["reports"], skip=writer, limit=10, template=CHECK)  # the writer never checks its own slide
        print(f"  {slot} #{st['id']} draft {attempt + 1}: " + " | ".join(log), file=sys.stderr)
        if ok:
            return out, writer
        fallback = (dict(out, _flag=" ".join(l for l in log if "FAIL" in l)[:300]), writer)
        extra = ("\nYour last answer failed the fact-check: " + " ".join(log) +
                 ". Remove or rewrite only the unsupported claim. Last answer: " + json.dumps(out, ensure_ascii=False) + "\n")
    return fallback if fallback else (None, "")


def publish(day: dt.date) -> None:
    """After review: render the reviewed edition.json and queue it for Instagram."""
    folder = ROOT / "magazine" / "daily" / day.isoformat()
    ed = json.loads((folder / "edition.json").read_text(encoding="utf-8"))
    lib = photo_library()
    for k in ("cover_photo", "big_photo", "pol_photo", "biz_photo", "up_photo"):
        if ed.get(k) not in lib:
            sys.exit(f"{k} is not a library photo")
    ok, log = build(ed, day, lib, ed["market"]["title"], ed["market"]["rows"])
    if not ok:
        sys.exit("layout problem, shorten the named fields and run again:\n" + log)
    ed["status"] = "published"
    (folder / "edition.json").write_text(json.dumps(ed, indent=1, ensure_ascii=False), encoding="utf-8")
    label = day.strftime("%a %-d %b %Y")
    upsert(ROOT / "site" / "daily.json", "editions",
           {"date": day.isoformat(), "label": label, "title": ed["cover_title"], "summary": ed["cover_dek"], "slides": 7})
    upsert(ROOT / "social" / "daily_queue.json", "editions",
           {"date": day.isoformat(), "title": ed["cover_title"], "caption": caption(ed, day, lib)})
    print(f"published The Daily for {day}: {ed['cover_title']}")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--publish" in sys.argv:
        return publish(market_day(args[0] if args else None))
    sample = "--sample" in sys.argv
    day = market_day(args[0] if args else None)
    tag = re.sub(r"[^a-z0-9]+", "", os.environ.get("DAILY_WRITER", "").lower())
    name = day.isoformat() + (("-sample-" + tag if tag else "-sample") if sample else "")
    folder = ROOT / "magazine" / "daily" / name
    if folder.exists() and not sample:
        print(f"The Daily for {day} already exists; nothing to do")
        return
    lib = photo_library()
    news = gather_news(day)
    if len(news) < 8:
        sys.exit(f"only {len(news)} trusted stories found; not enough for an edition")
    by_id = {s["id"]: s for s in news}
    mkt_title, mkt = market_rows(day)
    day_long = day.strftime("%A %-d %B %Y")
    plan = None
    for _ in range(3):
        try:
            plan = parse_json(llm(PLAN.format(
                day_long=day_long, photos="\n".join(f"{k}: {v['subject']}" for k, v in lib.items()),
                sources="\n\n".join(f"#{s['id']} ({s['region']}, {s['category']}; reported by {', '.join(s['outlets'])})\n" + story_text(s)
                                    for s in news)))[0])
            for k in ("big", "r1", "r2", "r3", "pol", "biz", "up"):
                plan[k] = int(str(plan[k]).lstrip("#"))
            plan["backups"] = [int(str(b).lstrip("#")) for b in plan.get("backups", [])]
            ids = [plan[k] for k in ("big", "r1", "r2", "r3", "pol", "biz", "up")]
            ph = plan.get("photos") or {}
            seen = set()
            for k in ("cover", "big", "pol", "biz", "up"):      # repair bad or repeated photo picks
                if ph.get(k) not in lib or ph[k] in seen:
                    ph[k] = next(x for x in lib if x not in seen and x not in ph.values())
                seen.add(ph[k])
            plan["photos"] = ph
            problems = [f"#{i} unknown" for i in ids if i not in by_id] + (["stories repeat"] if len(set(ids)) < 7 else [])
            if not problems:
                break
            print(f"  plan rejected: {problems}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"  plan rejected: {e}", file=sys.stderr)
        plan = None
    if not plan:
        sys.exit("could not plan the edition today; nothing published")
    backups = [b for b in plan.get("backups", []) if b in by_id]
    used, ed, writers, regions = set(), {"regions": [None, None, None], "story_ids": []}, set(), set()
    for slot in ("big", "pol", "biz", "up", "r1", "r2", "r3"):
        tried = 0
        for sid in [plan[slot]] + backups:
            if tried >= 3:
                break
            if sid in used:
                continue
            tried += 1
            t0 = time.time()
            out, w = write_slot(slot, by_id[sid], [])
            print(f"  {slot}: story #{sid} {'ok' if out else 'failed'} in {time.time() - t0:.0f}s", file=sys.stderr)
            if not out:
                continue
            flag = out.pop("_flag", "")
            ed.setdefault("review", []).append({"slot": slot, "story": sid, "free_checkers": flag or "passed"})
            if slot.startswith("r"):
                if out["region"]["name"] in regions:
                    continue
                regions.add(out["region"]["name"])
                ed["regions"][int(slot[1]) - 1] = out["region"]
            else:
                ed.update(out)
            if slot == "big":
                import bot
                TAKEN.update(bot.keywords(slot_check_text("big", out)))
            used.add(sid)
            ed["story_ids"].append(sid)
            writers.add(w)
            break
        if slot.startswith("r") and ed["regions"][int(slot[1]) - 1] is None or not slot.startswith("r") and not ed.get(SLOT_FIELDS[slot][0]):
            sys.exit(f"no story passed the checks for the {slot} slide; nothing published")
    ph = plan["photos"]
    ed.update({"cover_photo": ph["cover"], "big_photo": ph["big"], "pol_photo": ph["pol"],
               "biz_photo": ph["biz"], "up_photo": ph["up"]})
    ed["sources_used"] = sorted({r["publisher"] for i in used for r in by_id[i]["reports"]})[:8]
    for _ in range(3):
        ok, rlog = build(ed, day, lib, mkt_title, mkt, name)
        if ok:
            break
        print("  layout problem, shortening: " + rlog, file=sys.stderr)
        for k in list(LIMITS):
            LIMITS[k] = int(LIMITS[k] * 0.88)
        ed = shorten(ed)
    else:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
        sys.exit("the text would not fit the slides; nothing published")
    writer = "/".join(sorted(writers))
    ed["market"] = {"title": mkt_title, "rows": mkt}
    ed["status"] = "draft"
    (folder / "edition.json").write_text(json.dumps({"writer": writer, **ed}, indent=1, ensure_ascii=False), encoding="utf-8")
    (folder / "sources.json").write_text(json.dumps({str(i): by_id[i]["reports"] for i in used}, indent=1, ensure_ascii=False), encoding="utf-8")
    if not sample:
        print(f"Draft ready for review: magazine/daily/{name}/edition.json (not published)")
        return
    print(f"The Daily for {day}: {ed['cover_title']} (written by {writer}; every slide passed two other models)")
    if sample:
        return
    label = day.strftime("%a %-d %b %Y")
    upsert(ROOT / "site" / "daily.json", "editions",
           {"date": day.isoformat(), "label": label, "title": ed["cover_title"], "summary": ed["cover_dek"], "slides": 7})
    upsert(ROOT / "social" / "daily_queue.json", "editions",
           {"date": day.isoformat(), "title": ed["cover_title"], "caption": caption(ed, day, lib)})


if __name__ == "__main__":
    main()
