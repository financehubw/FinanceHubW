"""The Weekly: Gemini (free) writes the draft into last week's exact layout; a Claude review only
checks facts, then publishes.

    python magazine/weekly_free.py              # Saturday morning: draft the issue for Mon-Fri just ended
    python magazine/weekly_free.py NN --publish # after review: render issue NN and queue it for Instagram

How it keeps the design: the previous issue's 20 slides are the template. Every visible piece of
text on each slide is a "segment"; Gemini replaces the segments one slide at a time (same count,
similar length), so fonts, colours, layout and chapter rhythm never change. Photos are swapped for
a library photo that fits the new story, tinted in that slide's colour, with its credit.

Draft output: magazine/issues/issue-NN/draft.json  (segments per slide, photos, sources, flags)
Nothing is posted until the review runs --publish.
"""
from __future__ import annotations

import datetime as dt
import html as htmllib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "magazine"), str(ROOT / "xbot")]
import daily_free as D  # noqa: E402  (llm, parse_json, numbers, photo_library, verify)

ISSUES = ROOT / "magazine" / "issues"
TEXT = re.compile(r">([^<>]+)<")
LOCKED = re.compile(r"^(Photo|File photo|The Weekly|SWIPE|@FINANCEHUBW|SAVE THIS POST · SHARE IT|@FINANCEHUBW · \d\d / 20|ISSUE \d\d|.*©.*)$")
CHAPTER_COLOURS = ["2F5BFF", "7C3AED", "00C48C", "FF3D8B", "FABC4D", "FA5B3C"]


# ------------------------------------------------------------------ template
def last_issue() -> int:
    nums = [int(p.name.split("-")[1]) for p in ISSUES.glob("issue-[0-9][0-9]") if (p / "slides").exists()]
    return max(nums) if nums else 0


def body_of(html: str) -> tuple[int, int]:
    a = html.index("<body>")
    return a, html.index("</body>")


def segments(html: str) -> list[tuple[int, int, str]]:
    a, b = body_of(html)
    out = []
    for m in TEXT.finditer(html, a, b):
        t = m.group(1)
        if t.strip():
            out.append((m.start(1), m.end(1), htmllib.unescape(t.strip())))
    return out


def apply(html: str, new: list[str]) -> str:
    segs = segments(html)
    for (s, e, old), val in sorted(zip(segs, new), key=lambda x: -x[0][0]):
        raw = html[s:e]
        lead, trail = raw[: len(raw) - len(raw.lstrip())], raw[len(raw.rstrip()):]
        html = html[:s] + lead + htmllib.escape(val, quote=False) + trail + html[e:]
    return html


def slide_colour(html: str) -> str:
    for c in re.findall(r"#([0-9A-Fa-f]{6})", html):
        if c.upper() in CHAPTER_COLOURS:
            return c.upper()
    return "FA5B3C"


# ------------------------------------------------------------------ inputs
def week_of(today: dt.date) -> tuple[dt.date, dt.date]:
    fri = today - dt.timedelta(days=(today.weekday() - 4) % 7)
    return fri - dt.timedelta(days=4), fri


def week_sources(mon: dt.date, fri: dt.date) -> list[dict]:
    reps = []
    for i in range(5):
        f = ROOT / "magazine" / "daily" / (mon + dt.timedelta(days=i)).isoformat() / "sources.json"
        if f.exists():
            for rs in json.loads(f.read_text(encoding="utf-8")).values():
                reps += rs
    import bot
    bot.MAX_AGE_HOURS = 24 * 8
    items = [i for i in bot.fetch_all() if not D.INDIA.search(i["title"] + " " + i["summary"])]
    stories = sorted((s for s in bot.cluster(items) if bot.trusted(s)), key=bot.score, reverse=True)[:60]
    for s in stories:
        reps += [{"publisher": bot.display_pub(r["publisher"]), "title": r["title"],
                  "summary": r["summary"][:400], "link": r["link"]} for r in s["reports"][:3]]
    seen, out = set(), []
    for r in reps:
        if r["title"] not in seen:
            seen.add(r["title"])
            out.append(r)
    return out[:180]


def week_markets(mon: dt.date, fri: dt.date) -> str:
    import yfinance as yf
    rows = [("S&P 500", "^GSPC"), ("Dow Jones", "^DJI"), ("Nasdaq", "^IXIC"), ("Russell 2000", "^RUT"),
            ("STOXX 600", "^STOXX"), ("DAX", "^GDAXI"), ("FTSE 100", "^FTSE"), ("CAC 40", "^FCHI"),
            ("Nikkei 225", "^N225"), ("Hang Seng", "^HSI"), ("Brent oil $", "BZ=F"), ("Gold $/oz", "GC=F"),
            ("Bitcoin $", "BTC-USD"), ("Ether $", "ETH-USD"), ("US 10-year yield %", "^TNX")]
    lines = []
    for name, t in rows:
        try:
            h = yf.Ticker(t).history(start=(mon - dt.timedelta(days=5)).isoformat(),
                                     end=(fri + dt.timedelta(days=1)).isoformat())["Close"].dropna()
            before = h[[i.date() < mon for i in h.index]]
            inweek = h[[mon <= i.date() <= fri for i in h.index]]
            if len(before) and len(inweek):
                a, z = float(before.iloc[-1]), float(inweek.iloc[-1])
                lines.append(f"{name}: Friday close {z:,.2f}; week change {(z - a) / a * 100:+.2f}%; "
                             f"Friday change {(z - float(h.iloc[-2])) / float(h.iloc[-2]) * 100:+.2f}%; "
                             f"week high {float(inweek.max()):,.2f}")
        except Exception:  # noqa: BLE001
            continue
    return "\n".join(lines)


# ------------------------------------------------------------------ writing
PLAN = """You edit "The Weekly", a 20-slide Instagram magazine about WORLD finance (never India) for ordinary people.
Plan this week's issue ({week}) from the SOURCES and MARKET DATA. Last week's issue is the model: same 20-slide
rhythm, same kind of chapter for each slide (oil/energy, interest rates, Wall Street, deal of the week, world
markets, banks/jobs, money on the move, crypto, gold, dates to watch) but use what actually mattered THIS week.
Find ONE thread that ties the week together and name the issue after it (like "The $100 week").
Return JSON: {{"title": "...", "thread": "one sentence", "summary": "two sentences for the website",
"sections": [{{"h": "Oil", "p": "one or two sentences"}}, ... 5 or 6],
"slides": {{"01": "what slide 1 says this week", ..., "20": "..."}} }}
Use only facts in the SOURCES or MARKET DATA. Plain words.

LAST WEEK'S SLIDES (text only):
{old}

MARKET DATA (computed, exact):
{markets}

SOURCES:
{sources}
Reply with JSON only."""

SLIDE = """Rewrite one slide of "The Weekly" for this week. The slide's text pieces are listed in order; return a JSON
list with EXACTLY {n} strings, one replacement per piece, in the same order. Keep each piece about the same
length as the original (never more than {more} characters longer) so the layout fits. Keep labels like
"CHAPTER ONE · OIL" in the same style; keep teasers like "NEXT: ... →" (max 30 characters, capitals) pointing at
the next slide's topic. Pieces marked [KEEP] must be returned unchanged.
Plain words, short sentences, every term explained, no hype, no advice, no India. Use ONLY facts and numbers from
the SOURCES and MARKET DATA; never invent or round differently.

ISSUE: {title} — {thread}
THIS SLIDE SHOULD SAY: {brief}
NEXT SLIDE IS ABOUT: {nxt}
{photo_note}
ORIGINAL PIECES:
{pieces}

MARKET DATA:
{markets}

SOURCES:
{sources}
{extra}Reply with the JSON list only."""


def write_slide(num: str, html: str, plan: dict, markets: str, src_text: str, lib: dict) -> dict:
    segs = segments(html)
    old = [s for _, _, s in segs]
    has_img = "<img" in html
    pieces = "\n".join(f"{i + 1}. {'[KEEP] ' if LOCKED.match(t) else ''}{t}" for i, t in enumerate(old))
    nxt = plan["slides"].get(f"{int(num) + 1:02d}", "end of issue")
    photo_note = ("Also choose a photo: add a final extra item to the list, the KEY of the library photo that best fits "
                  "this slide's story, from: " + ", ".join(lib) + ". Use the word none if nothing fits."
                  ) if has_img else ""
    extra, best = "", None
    for attempt in range(3):
        reply, writer = D.llm(SLIDE.format(n=len(old) + (1 if has_img else 0), more=12, title=plan["title"],
                                          thread=plan["thread"], brief=plan["slides"].get(num, ""), nxt=nxt,
                                          photo_note=photo_note, pieces=pieces, markets=markets,
                                          sources=src_text, extra=extra))
        try:
            new = json.loads(re.search(r"\[.*\]", re.sub(r"<think>.*?</think>", "", reply, flags=re.S), re.S).group(0))
        except Exception:  # noqa: BLE001
            extra = "Your last reply was not a valid JSON list.\n"
            continue
        photo = new.pop() if has_img and len(new) == len(old) + 1 else None
        if len(new) != len(old):
            extra = f"Your last list had {len(new)} items; it must have exactly {len(old) + (1 if has_img else 0)}.\n"
            continue
        new = [o if LOCKED.match(o) else str(n) for o, n in zip(old, new)]
        errs = [f"piece {i + 1} too long" for i, (o, n) in enumerate(zip(old, new)) if len(n) > len(o) + 12 and len(o) > 3]
        bad = sorted(D.numbers(" ".join(new)) - D.numbers(src_text + markets + " ".join(old[:0])) -
                     {str(x) for x in range(32)} - {str(y) for y in range(2020, 2031)})
        if bad:
            errs.append("numbers not in the sources: " + ", ".join(bad[:6]))
        best = {"segments": new, "photo": photo if photo in lib else None, "writer": writer, "flags": errs}
        if not errs:
            break
        extra = "Fix these and send the whole list again: " + "; ".join(errs) + "\n"
    return best or {"segments": old, "photo": None, "writer": "", "flags": ["could not rewrite; kept last week's text"]}


# ------------------------------------------------------------------ build
def build(n: int, draft: dict, lib: dict) -> tuple[bool, str]:
    tpl = ISSUES / f"issue-{draft['template']:02d}" / "slides"
    out = ISSUES / f"issue-{n:02d}" / "slides"
    out.mkdir(parents=True, exist_ok=True)
    for f in sorted(tpl.glob("[0-9][0-9].html")):
        html = f.read_text(encoding="utf-8")
        sl = draft["slides"][f.stem]
        segs = list(sl["segments"])
        segs = [re.sub(r"ISSUE \d\d", f"ISSUE {n:02d}", s) for s in segs]
        if sl.get("photo") and "<img" in html:
            colour = slide_colour(html)
            subprocess.run([sys.executable, str(ROOT / "magazine" / "tint.py"), sl["photo"], "#" + colour],
                           check=True, capture_output=True)
            html = re.sub(r'src="\.\./\.\./\.\./photos/[^"]+"', f'src="../../../photos/tinted/{sl["photo"]}-{colour}.jpg"', html, count=1)
            p = lib[sl["photo"]]
            segs = [f"File photo: {p['author']}, {p['licence']}, tinted" if s.startswith(("Photo", "File photo")) else s for s in segs]
        html = apply(html, segs)
        html = re.sub(r"© \d{4}", f"© {draft['year']}", html)
        (out / f.name).write_text(html, encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "magazine" / "render.py"), str(n)], capture_output=True, text=True)
    return r.returncode == 0, (r.stderr or r.stdout)[-1200:]


def draft_issue() -> None:
    today = dt.datetime.utcnow().date()
    mon, fri = week_of(today)
    prev = last_issue()
    n = prev + 1
    folder = ISSUES / f"issue-{n:02d}"
    if (folder / "draft.json").exists():
        print(f"Issue {n} draft already exists; nothing to do")
        return
    lib = D.photo_library()
    reps = week_sources(mon, fri)
    src_text = "\n".join(f"- [{r['publisher']}] {r['title']}. {r.get('summary', '')}" for r in reps)
    markets = week_markets(mon, fri)
    tpl = ISSUES / f"issue-{prev:02d}" / "slides"
    slides_html = {f.stem: f.read_text(encoding="utf-8") for f in sorted(tpl.glob("[0-9][0-9].html"))}
    old_text = "\n".join(f"{k}: " + " | ".join(s for _, _, s in segments(h)) for k, h in slides_html.items())
    week = f"{mon.day}–{fri.day} {fri.strftime('%b %Y')}" if mon.month == fri.month else f"{mon.strftime('%-d %b')}–{fri.strftime('%-d %b %Y')}"
    plan = None
    for _ in range(3):
        try:
            plan = D.parse_json(D.llm(PLAN.format(week=week, old=old_text, markets=markets, sources=src_text))[0])
            if plan.get("title") and len(plan.get("slides", {})) >= 18:
                break
        except Exception as e:  # noqa: BLE001
            print(f"  plan rejected: {e}", file=sys.stderr)
        plan = None
    if not plan:
        sys.exit("could not plan the issue; nothing drafted")
    draft = {"issue": n, "template": prev, "week": week, "year": fri.year, "status": "draft",
             "title": plan["title"], "thread": plan.get("thread", ""), "summary": plan.get("summary", ""),
             "sections": plan.get("sections", [])[:6], "slides": {}, "sources": reps, "markets": markets}
    for num, html in slides_html.items():
        draft["slides"][num] = write_slide(num, html, plan, markets, src_text, lib)
        print(f"  slide {num}: {'ok' if not draft['slides'][num]['flags'] else draft['slides'][num]['flags']}", file=sys.stderr)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "draft.json").write_text(json.dumps(draft, indent=1, ensure_ascii=False), encoding="utf-8")
    ok, log = build(n, draft, lib)
    print(f"Issue {n} draft ready for review ({'renders cleanly' if ok else 'LAYOUT PROBLEMS: ' + log})")


def publish(n: int) -> None:
    folder = ISSUES / f"issue-{n:02d}"
    draft = json.loads((folder / "draft.json").read_text(encoding="utf-8"))
    lib = D.photo_library()
    ok, log = build(n, draft, lib)
    if not ok:
        sys.exit("layout problem, shorten the pieces on the slides named and run again:\n" + log)
    draft["status"] = "published"
    (folder / "draft.json").write_text(json.dumps(draft, indent=1, ensure_ascii=False), encoding="utf-8")
    D.upsert(ROOT / "site" / "magazine.json", "issues",
             {"issue": n, "week": draft["week"], "title": draft["title"], "summary": draft["summary"],
              "sections": draft["sections"], "slides": 20}, field="issue")
    pubs = sorted({r["publisher"] for r in draft["sources"]})[:8]
    photos = sorted({f"{lib[s['photo']]['author']} ({lib[s['photo']]['licence']})" for s in draft["slides"].values() if s.get("photo")})
    cap = (f"{draft['title']}. {draft['thread']}\n\nSwipe through the week in world finance, {draft['week']}.\n\n"
           f"Sources: {', '.join(pubs)}. Market data: Yahoo Finance.\n"
           + (f"Photos via Wikimedia Commons: {'; '.join(photos)}.\n" if photos else "")
           + "\nInformation only, not investment advice.\n"
           f"© {draft['year']} FinanceHubW. All rights reserved. Share with credit to @financehubw.\n\n"
           "#finance #economy #markets #worldnews #money")
    D.upsert(ROOT / "social" / "magazine_queue.json", "issues",
             {"issue": n, "date": dt.datetime.utcnow().date().isoformat(), "title": draft["title"],
              "caption": cap[:2200], "short": [1, 2, 3, 4, 7, 8, 10, 13, 18, 20]}, field="issue")
    print(f"published The Weekly #{n}: {draft['title']}")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    if "--publish" in sys.argv:
        publish(int(a[0]) if a else last_issue())
    else:
        draft_issue()
