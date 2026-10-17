"""New Short formats, written by code from live market data (no AI, no typed numbers).

Research (Oct 2026) on what gets the most views for faceless finance Shorts:
  - bar-chart races (rankings that reorder over time hold attention to the end)
  - head-to-head comparisons ("Apple vs Microsoft": drives comments and shares)
  - "guess first" quizzes (people comment their answer before the reveal)
  - top-5 countdowns (the #1 reveal at the end keeps people watching)
  - quick explainers with a clear voiceover (high watch-through)
This writes scripts in those formats into social/shorts_scripts/; shorts_factory.py renders them.

    python social/formats.py 6     -> up to 6 new scripts, rotating formats
"""
from __future__ import annotations
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "social" / "shorts_scripts"

RACES = [
    ("race_btc_sp_gold_cash", "2015-01-02", "2015", [("BTC-USD", "Bitcoin"), ("SPY", "S&P 500"), ("GLD", "Gold"), ("CASH", "Cash")],
     "Bitcoin, stocks, gold or cash?", "bitcoin gold"),
    ("race_big_tech_2015", "2015-01-02", "2015", [("NVDA", "Nvidia"), ("AAPL", "Apple"), ("MSFT", "Microsoft"), ("AMZN", "Amazon"), ("GOOGL", "Google")],
     "Big Tech race since 2015", "technology"),
    ("race_crypto_2018", "2018-01-02", "2018", [("BTC-USD", "Bitcoin"), ("ETH-USD", "Ethereum"), ("BNB-USD", "BNB"), ("XRP-USD", "XRP")],
     "Crypto race since 2018", "cryptocurrency"),
    ("race_safe_havens_2008", "2008-01-02", "2008", [("GLD", "Gold"), ("SPY", "S&P 500"), ("TLT", "US bonds"), ("CASH", "Cash")],
     "Since the 2008 crash", "gold bars"),
    ("race_brands_2010", "2010-01-04", "2010", [("NKE", "Nike"), ("SBUX", "Starbucks"), ("MCD", "McDonald's"), ("KO", "Coca-Cola"), ("DIS", "Disney")],
     "Famous brands race since 2010", "shopping street"),
    ("race_chips_2016", "2016-01-04", "2016", [("NVDA", "Nvidia"), ("AMD", "AMD"), ("TSM", "TSMC"), ("INTC", "Intel")],
     "Chip makers since 2016", "computer chip"),
]
PAIRS = [
    ("AAPL", "Apple", "MSFT", "Microsoft", "2015-01-02"), ("KO", "Coca-Cola", "PEP", "Pepsi", "2010-01-04"),
    ("V", "Visa", "MA", "Mastercard", "2010-01-04"), ("GLD", "Gold", "SPY", "the S&P 500", "2000-01-03"),
    ("BTC-USD", "Bitcoin", "GLD", "Gold", "2016-01-01"), ("AMZN", "Amazon", "WMT", "Walmart", "2010-01-04"),
    ("MCD", "McDonald's", "SBUX", "Starbucks", "2010-01-04"), ("NVDA", "Nvidia", "AMD", "AMD", "2016-01-04"),
    ("GOOGL", "Google", "META", "Meta", "2013-01-02"), ("HD", "Home Depot", "LOW", "Lowe's", "2010-01-04"),
    ("TSLA", "Tesla", "TM", "Toyota", "2015-01-02"), ("NFLX", "Netflix", "DIS", "Disney", "2015-01-02"),
    ("NKE", "Nike", "LULU", "Lululemon", "2012-01-03"), ("COST", "Costco", "TGT", "Target", "2010-01-04"),
]
GIANTS = ["NVDA", "MSFT", "AAPL", "GOOGL", "AMZN", "META", "AVGO", "TSM", "BRK-B", "TSLA", "LLY", "JPM", "WMT", "V"]
NAMES = {"NVDA": "Nvidia", "MSFT": "Microsoft", "AAPL": "Apple", "GOOGL": "Alphabet (Google)", "AMZN": "Amazon",
         "META": "Meta", "AVGO": "Broadcom", "TSM": "TSMC", "BRK-B": "Berkshire Hathaway", "TSLA": "Tesla",
         "LLY": "Eli Lilly", "JPM": "JPMorgan", "WMT": "Walmart", "V": "Visa"}
PHOTO = {"NVDA": "computer chip", "MSFT": "office laptop", "AAPL": "smartphone", "GOOGL": "search engine laptop",
         "AMZN": "cardboard boxes", "META": "social media phone", "AVGO": "circuit board", "TSM": "chip factory",
         "BRK-B": "omaha", "TSLA": "electric car", "LLY": "medicine", "JPM": "bank building", "WMT": "supermarket", "V": "credit card"}


def growth_now(tick: str, start: str) -> float:
    if tick == "CASH":
        return 1000.0
    import yfinance as yf
    h = yf.Ticker(tick).history(start=start, auto_adjust=False)["Close"].dropna()
    return 1000 * float(h.iloc[-1]) / float(h.iloc[0])


def g(tick, start):
    return "$1,000" if tick == "CASH" else "{growth:%s:%s}" % (tick, start)


def race(r):
    sid, start, yr, items, title, photo = r
    win = max(items, key=lambda it: growth_now(it[0], start))
    last = min(items, key=lambda it: growth_now(it[0], start))
    return sid, {
        "id": sid, "title": f"$1,000 in each since {yr}: who wins?",
        "thumb": f"$1,000 since {yr}: *who wins?*", "thumb_photo": photo, "thumb_tag": "RACE",
        "caption": f"{title}. $1,000 in each in {yr}.\nWinner: {win[1]}, now about {g(win[0], start)}.\nLast: {last[1]}, about {g(last[0], start)}.\n(Price growth only, no dividends.)",
        "comment": "Did you guess the winner? 👇",
        "tags": ["#investing", "#stocks", "#money", "#finance", "#race", "#dataviz"],
        "sources": ["Yahoo Finance price history (split-adjusted), at render time"],
        "scenes": [
            {"say": f"One thousand dollars in each, back in {yr}. Guess the winner.", "photo": photo,
             "quiz": {"q": "Which grew the most?", "a": items[0][1], "b": items[1][1]}},
            {"say": "Watch the race.", "race": {"start": start, "items": [list(i) for i in items]}},
            {"say": f"{win[1]} wins, at about {g(win[0], start)}. {last[1]} comes last, at about {g(last[0], start)}.",
             "race": {"start": start, "items": [list(i) for i in items], "hold": True}},
            {"say": "Which one would you have picked?", "photo": "thinking person", "big": "Your pick?", "sub": "tell us in the comments"},
        ]}


def versus(p):
    ta, na, tb, nb, start = p
    yr = start[:4]
    sid = f"vs_{ta.lower().replace('-', '')}_{tb.lower().replace('-', '')}_{yr}"
    ga, gb = growth_now(ta, start), growth_now(tb, start)
    win, lose = ((na, ta), (nb, tb)) if ga >= gb else ((nb, tb), (na, ta))
    return sid, {
        "id": sid, "title": f"{na} vs {nb}: $1,000 in {yr}, who wins?",
        "thumb": f"{na} vs {nb}: *who won?*", "thumb_photo": PHOTO.get(ta, "stock market"), "thumb_tag": "VS",
        "caption": f"$1,000 in {na} or {nb} in {yr}?\n{win[0]}: about {g(win[1], start)}\n{lose[0]}: about {g(lose[1], start)}\n(Price growth only, no dividends.)",
        "comment": f"Team {na} or team {nb}? 👇",
        "tags": ["#investing", "#stocks", "#money", "#finance", "#versus", f"#{na.lower().replace(' ', '').replace(chr(39), '')}"],
        "sources": ["Yahoo Finance price history (split-adjusted), at render time"],
        "scenes": [
            {"say": f"{na} or {nb}? One thousand dollars each, in {yr}. Pick one before the reveal.",
             "photo": PHOTO.get(ta, "stock market"), "quiz": {"q": "Which is worth more today?", "a": f"{na}", "b": f"{nb}"}},
            {"say": "Here's how it played out.", "versus": {"start": start, "a": [ta, na], "b": [tb, nb]}},
            {"say": f"{win[0]} wins, at about {g(win[1], start)}, against {g(lose[1], start)}.",
             "versus": {"start": start, "a": [ta, na], "b": [tb, nb], "hold": True}},
            {"say": "Did you pick the winner?", "photo": "trophy", "big": "Your pick?", "sub": "comment A or B"},
        ]}


def countdown():
    import yfinance as yf
    caps = []
    for t in GIANTS:
        try:
            caps.append((float(yf.Ticker(t).fast_info["market_cap"]), t))
        except Exception:  # noqa: BLE001
            pass
    top = sorted(caps, reverse=True)[:5]
    month = dt.date.today().strftime("%B %Y")
    sid = "top5_companies_" + dt.date.today().strftime("%Y_%m")
    scenes = [{"say": "The five most valuable companies on Earth, right now. Number one might surprise you.",
               "photo": "city skyline night", "big": "Top 5", "sub": f"by market value, {month}"}]
    for rank, (_, t) in zip(range(5, 0, -1), reversed(top)):
        scenes.append({"say": f"Number {rank}. {NAMES[t]}, worth about {{cap:{t}*1}}.", "photo": PHOTO[t],
                       "big": f"#{rank} {NAMES[t]}", "sub": f"about {{cap:{t}*1}}"})
    scenes.append({"say": "Who will be number one next year?", "photo": "trophy", "big": "Next #1?", "sub": "comment your guess"})
    return sid, {
        "id": sid, "title": f"The 5 most valuable companies in the world ({month})",
        "thumb": "World's *TOP 5* companies", "thumb_photo": "city skyline night", "thumb_tag": "COUNTDOWN",
        "caption": "The 5 most valuable companies in the world right now, by market value:\n" +
                   "\n".join(f"#{i} {NAMES[t]}: about {{cap:{t}*1}}" for i, (_, t) in enumerate(top, 1)),
        "comment": "Who will be #1 a year from now? 👇",
        "tags": ["#stocks", "#business", "#investing", "#money", "#top5", "#companies"],
        "sources": ["Market values: Yahoo Finance, at render time"],
        "scenes": scenes}


def main(n: int) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    have = {p.stem for p in OUT.glob("*.json")}
    plan = []
    month_id = "top5_companies_" + dt.date.today().strftime("%Y_%m")
    if month_id not in have:
        plan.append(countdown)
    races = [lambda r=r: race(r) for r in RACES if r[0] not in have]
    pairs = [lambda p=p: versus(p) for p in PAIRS
             if f"vs_{p[0].lower().replace('-', '')}_{p[2].lower().replace('-', '')}_{p[4][:4]}" not in have]
    while len(plan) < n and (races or pairs):            # alternate: versus, race, versus, ...
        if pairs:
            plan.append(pairs.pop(0))
        if races and len(plan) < n:
            plan.append(races.pop(0))
    for mk in plan[:n]:
        try:
            sid, spec = mk()
        except Exception as e:  # noqa: BLE001  a missing ticker never stops the batch
            print("skipped:", e); continue
        (OUT / f"{sid}.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False), encoding="utf-8")
        print("script:", sid)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 6)
