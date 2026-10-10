"""The Daily, made for free: news from the X bot's sources, words from free AI models,
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
}


# ------------------------------------------------------------------ inputs
def market_day(arg: str | None) -> dt.date:
    if arg:
        return dt.date.fromisoformat(arg)
    d = dt.datetime.utcnow().date() - dt.timedelta(days=1)
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
    bot.MAX_AGE_HOURS = 40
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
        if not closed_today and tick == "^GSPC":
            text = f"<strong>US shares</strong>: markets were shut. Last close {v:,.0f}."
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
- Region names must be one of: {regions}.
- Photos: choose for each *_photo the key from PHOTOS whose subject matches that slide's story; use each key once.
- Length limits (characters, hard maximum): {limits}
- "sources_used": the outlets you took facts from.

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


def llm(prompt: str) -> tuple[str, str]:
    for name, fn in (("Gemini", verify._gemini), ("Groq GPT-OSS", verify._groq_oss), ("OpenRouter", verify._openrouter)):
        env = {"Gemini": "GEMINI_API_KEY", "Groq GPT-OSS": "GROQ_API_KEY", "OpenRouter": "OPENROUTER_API_KEY"}[name]
        if not os.environ.get(env):
            continue
        try:
            return fn(prompt, 4000), name
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
        if len(v) > LIMITS[k]:
            errs.append(f"{k} is {len(v)} characters, limit {LIMITS[k]}")
        flat.append(v)
    regs = ed.get("regions") or []
    if len(regs) != 3 or len({r.get("name") for r in regs}) != 3:
        errs.append("regions must be three different regions")
    for r in regs:
        if r.get("name") not in REGIONS_OK:
            errs.append(f"region name {r.get('name')!r} not allowed")
        if len(r.get("text", "")) > LIMITS["region_text"]:
            errs.append(f"region text too long ({r.get('name')})")
        flat.append(r.get("text", ""))
    stats = ed.get("biz_stats") or []
    if len(stats) != 2:
        errs.append("biz_stats must have two figures")
    for s in stats:
        for f, lim in (("value", "s_value"), ("name", "s_name"), ("note", "s_note")):
            if len(s.get(f, "")) > LIMITS[lim] or not s.get(f):
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


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sample = "--sample" in sys.argv
    day = market_day(args[0] if args else None)
    name = day.isoformat() + ("-sample" if sample else "")
    folder = ROOT / "magazine" / "daily" / name
    if folder.exists() and not sample:
        print(f"The Daily for {day} already exists; nothing to do")
        return
    lib = photo_library()
    news = gather_news(day)
    if len(news) < 8:
        sys.exit(f"only {len(news)} trusted stories found; not enough for an edition")
    src_text = "\n\n".join(f"[{r['publisher']}] {r['title']}\n{r['summary']}" for s in news for r in s["reports"])
    mkt_title, mkt = market_rows(day)
    day_long = day.strftime("%A %-d %B %Y")
    base = PROMPT.format(
        day_long=day_long, regions=", ".join(REGIONS_OK), limits=json.dumps(LIMITS),
        sample=json.dumps(SAMPLE, ensure_ascii=False, indent=1),
        photos="\n".join(f"{k}: {v['subject']}" for k, v in lib.items()),
        sources="\n\n".join(f"#{s['id']} ({s['region']}, {s['category']}; reported by {', '.join(s['outlets'])})\n" +
                            "\n".join(f"- [{r['publisher']}] {r['title']}. {r['summary']}" for r in s["reports"])
                            for s in news),
        extra="{extra}")
    extra, ed, writer = "", None, ""
    for attempt in range(4):
        reply, writer = llm(base.replace("{extra}", extra))
        try:
            ed = parse_json(reply)
        except Exception as e:  # noqa: BLE001
            extra = f"\nYOUR LAST REPLY WAS NOT VALID JSON ({e}). Reply with the JSON only.\n"
            continue
        errs = validate(ed, src_text, lib)
        if errs:
            print(f"  draft {attempt + 1} rejected: {errs}", file=sys.stderr)
            extra = "\nYOUR LAST DRAFT WAS REJECTED. Fix these and send the whole JSON again:\n- " + "\n- ".join(errs) + "\n"
            ed = None
            continue
        ok, log = verify.fact_check(flatten(ed), [r for s in news for r in s["reports"]][:24], skip=writer)
        print("  fact-check: " + " | ".join(log), file=sys.stderr)
        if not ok:
            extra = "\nYOUR LAST DRAFT FAILED THE FACT-CHECK:\n" + "\n".join(log) + "\nRemove or fix anything not supported by the sources.\n"
            ed = None
            continue
        ok, rlog = build(ed, day, lib, mkt_title, mkt, name)
        if ok:
            break
        print("  layout problem: " + rlog, file=sys.stderr)
        extra = "\nTHE TEXT DID NOT FIT THE SLIDES:\n" + rlog + "\nMake the fields named there clearly shorter.\n"
        ed = None
    if not ed:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
        sys.exit("no edition passed every check today; nothing published")
    (folder / "edition.json").write_text(json.dumps({"writer": writer, **ed}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"The Daily for {day}: {ed['cover_title']} (written by {writer}, checked by two other models)")
    if sample:
        return
    label = day.strftime("%a %-d %b %Y")
    upsert(ROOT / "site" / "daily.json", "editions",
           {"date": day.isoformat(), "label": label, "title": ed["cover_title"], "summary": ed["cover_dek"], "slides": 7})
    upsert(ROOT / "social" / "daily_queue.json", "editions",
           {"date": day.isoformat(), "title": ed["cover_title"], "caption": caption(ed, day, lib)})


if __name__ == "__main__":
    main()
