"""Endless supply of fact-safe "what if" Shorts, written by code (no AI, no typing numbers).

Each week it adds up to N new scripts to social/shorts_scripts/ from the bank below, alternating two formats:
  lump   "$1,000 in <company> in <year> is now worth ..."       ({growth:...})
  dca    "$100 a month into <company> since <year> ..."           ({dca:...})
Figures are computed at render time from Yahoo Finance price history (split-adjusted, no dividends).
"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "social" / "shorts_scripts"
BANK = [  # ticker, name, start date (first trading day of that month/year), year, photo, place, what they did then
    ("GOOGL", "Google", "2004-08-19", "2004", "search engine laptop", "Mountain View", "a search engine with ads"),
    ("META", "Facebook", "2012-05-18", "2012", "social media phone", "Menlo Park", "a social network"),
    ("NFLX", "Netflix", "2002-05-23", "2002", "dvd envelope", "Los Gatos", "mailing DVDs"),
    ("COST", "Costco", "2000-01-03", "2000", "warehouse store", "Issaquah", "a warehouse store"),
    ("SBUX", "Starbucks", "1992-06-26", "1992", "coffee shop", "Seattle", "a coffee chain"),
    ("NKE", "Nike", "1990-01-02", "1990", "running shoes", "Beaverton", "a shoe company"),
    ("MCD", "McDonald's", "1990-01-02", "1990", "burger fries", "Chicago", "selling burgers"),
    ("KO", "Coca-Cola", "1990-01-02", "1990", "soda bottles", "Atlanta", "selling soda"),
    ("DIS", "Disney", "1990-01-02", "1990", "theme park castle", "Burbank", "cartoons and theme parks"),
    ("ADBE", "Adobe", "2000-01-03", "2000", "graphic design", "San Jose", "making Photoshop"),
    ("AMD", "AMD", "2016-01-04", "2016", "computer processor", "Santa Clara", "a struggling chipmaker"),
    ("NVDA", "Nvidia", "2010-01-04", "2010", "gaming pc", "Santa Clara", "making gaming chips"),
    ("TSLA", "Tesla", "2013-01-02", "2013", "electric car charging", "Palo Alto", "a small electric car maker"),
    ("AAPL", "Apple", "2007-01-03", "2007", "smartphone", "Cupertino", "about to launch the iPhone"),
    ("MSFT", "Microsoft", "2014-02-04", "2014", "office laptop", "Redmond", "getting a new CEO"),
    ("AMZN", "Amazon", "2008-01-02", "2008", "cardboard boxes", "Seattle", "selling online in a recession"),
    ("V", "Visa", "2008-03-19", "2008", "credit card payment", "San Francisco", "listing in a crisis"),
    ("MA", "Mastercard", "2006-05-25", "2006", "card payment terminal", "New York", "a card network"),
    ("BRK-B", "Berkshire Hathaway", "1996-05-09", "1996", "omaha city", "Omaha", "Warren Buffett's company"),
    ("SPY", "the S&P 500", "1993-01-29", "1993", "wall street", "New York", "the first US index ETF"),
    ("QQQ", "the Nasdaq 100", "1999-03-10", "1999", "nasdaq screen", "New York", "tech stocks, just before the crash"),
    ("GLD", "gold", "2004-11-18", "2004", "gold bars", "New York", "the first big gold ETF"),
    ("BTC-USD", "Bitcoin", "2015-01-01", "2015", "bitcoin coin", "the internet", "a niche internet money"),
    ("ETH-USD", "Ethereum", "2017-11-09", "2017", "ethereum coin", "the internet", "a new crypto network"),
    ("NVO", "Novo Nordisk", "2015-01-02", "2015", "pharmacy medicine", "Copenhagen", "a diabetes drug maker"),
    ("TSM", "TSMC", "2010-01-04", "2010", "chip factory", "Taiwan", "making other companies' chips"),
    ("ASML", "ASML", "2010-01-04", "2010", "semiconductor machine", "the Netherlands", "making chip machines"),
    ("LLY", "Eli Lilly", "2015-01-02", "2015", "medicine pills", "Indianapolis", "an old drug maker"),
    ("WMT", "Walmart", "1990-01-02", "1990", "supermarket", "Bentonville", "a discount store"),
    ("HD", "Home Depot", "1990-01-02", "1990", "hardware tools", "Atlanta", "a hardware store"),
    ("NFLX", "Netflix", "2012-01-03", "2012", "streaming tv", "Los Gatos", "recovering from a stock crash"),
    ("AAPL", "Apple", "2003-01-02", "2003", "music player", "Cupertino", "selling iPods"),
    ("MSFT", "Microsoft", "2000-01-03", "2000", "office computer", "Redmond", "at the dot-com peak"),
    ("AMZN", "Amazon", "2001-01-02", "2001", "cardboard boxes", "Seattle", "surviving the dot-com crash"),
    ("GOOGL", "Google", "2009-03-02", "2009", "search laptop", "Mountain View", "at the bottom of the financial crisis"),
    ("JPM", "JPMorgan", "2009-03-02", "2009", "bank building", "New York", "a bank in the financial crisis"),
    ("BKNG", "Booking.com", "2003-01-02", "2003", "hotel travel", "Norwalk", "selling travel online"),
    ("INTU", "Intuit", "2000-01-03", "2000", "tax forms", "Mountain View", "making tax software"),
    ("CMG", "Chipotle", "2006-01-26", "2006", "burrito", "Denver", "a burrito chain"),
    ("MNST", "Monster Beverage", "2003-01-02", "2003", "energy drink", "Corona", "a small drink company"),
    ("ISRG", "Intuitive Surgical", "2005-01-03", "2005", "surgery robot", "Sunnyvale", "making surgical robots"),
    ("REGN", "Regeneron", "2010-01-04", "2010", "laboratory", "Tarrytown", "a biotech company"),
    ("NOW", "ServiceNow", "2012-06-29", "2012", "office software", "Santa Clara", "a new software company"),
    ("SHOP", "Shopify", "2015-05-21", "2015", "online shop", "Ottawa", "helping small shops sell online"),
    ("MELI", "MercadoLibre", "2008-01-02", "2008", "online shopping", "Buenos Aires", "Latin America's eBay"),
    ("AVGO", "Broadcom", "2010-01-04", "2010", "circuit board", "San Jose", "a chip company"),
    ("ORCL", "Oracle", "2015-01-02", "2015", "server room", "Austin", "a database company"),
    ("CAT", "Caterpillar", "2009-03-02", "2009", "bulldozer", "Texas", "making machines in a recession"),
    ("PEP", "PepsiCo", "1990-01-02", "1990", "snacks", "Purchase, NY", "selling soda and snacks"),
    ("PG", "Procter & Gamble", "1990-01-02", "1990", "household products", "Cincinnati", "selling soap and toothpaste"),
    ("JNJ", "Johnson & Johnson", "1990-01-02", "1990", "bandage", "New Jersey", "selling healthcare products"),
    ("XOM", "ExxonMobil", "2020-04-01", "2020", "oil rig", "Houston", "an oil giant during the 2020 crash"),
    ("UBER", "Uber", "2019-05-10", "2019", "taxi city night", "San Francisco", "a ride app, just listed"),
    ("PLTR", "Palantir", "2020-09-30", "2020", "data analytics", "Denver", "a data company, just listed"),
    ("SOL-USD", "Solana", "2021-01-01", "2021", "crypto coins", "the internet", "a young crypto network"),
    ("BNB-USD", "BNB", "2019-01-01", "2019", "crypto exchange", "the internet", "an exchange's coin"),
    ("VTI", "the whole US stock market", "2001-06-15", "2001", "american flag wall street", "Valley Forge", "one fund for every US stock"),
    ("EEM", "emerging markets", "2003-04-14", "2003", "world map", "New York", "one fund for fast-growing countries"),
    ("SLV", "silver", "2006-04-28", "2006", "silver coins", "New York", "the first big silver ETF"),
    ("TLT", "long-term US bonds", "2002-07-30", "2002", "government bonds", "New York", "a safe bond fund"),
]


def lump(t):
    tick, name, start, yr, photo, place, then = t
    g = "{growth:%s:%s}" % (tick, start)
    sid = f"whatif_{tick.lower().replace('-', '')}_{yr}"
    return sid, {
        "id": sid, "title": f"$1,000 in {name} in {yr} is now worth this",
        "thumb": f"$1,000 in {name} {yr} = *{g}*", "thumb_photo": photo, "thumb_tag": "WHAT IF",
        "caption": f"In {yr}, {name} was {then}.\n$1,000 in it then would be worth about {g} today (price growth only, no dividends).",
        "comment": f"What would you have done with {name} in {yr}? 👇",
        "tags": ["#investing", "#stocks", "#money", "#whatif", "#finance", "#compounding"],
        "sources": [f"{name} price history, Yahoo Finance (split-adjusted), at render time"],
        "scenes": [
            {"say": f"In {yr}, {name} was {then}.", "photo": photo, "clip": {"kicker": place, "year": yr, "text": f"{name}: {then}"}},
            {"say": "Say you put in one thousand dollars.", "photo": "dollar bills", "big": "$1,000", "sub": yr},
            {"say": f"Watch what it turns into. Today, it would be worth about {g}.",
             "growth": {"tick": tick, "name": name, "start": start}},
            {"say": "Time in the market does the heavy lifting.", "photo": "hourglass", "big": "Time", "sub": "the real ingredient"},
        ]}


def dca(t):
    tick, name, start, yr, photo, place, then = t
    g = "{dca:%s:%s}" % (tick, start)
    sid = f"monthly_{tick.lower().replace('-', '')}_{yr}"
    return sid, {
        "id": sid, "title": f"$100 a month into {name} since {yr} is now worth this",
        "thumb": f"$100/month in {name} since {yr} = *{g}*", "thumb_photo": photo, "thumb_tag": "MONTHLY HABIT",
        "caption": f"$100 every month into {name} since {yr}.\nToday that would be worth about {g} (price growth only, no dividends).",
        "comment": "Could you put away $100 a month? 👇",
        "tags": ["#investing", "#sip", "#money", "#stocks", "#finance", "#habits"],
        "sources": [f"{name} price history, Yahoo Finance (split-adjusted), at render time"],
        "scenes": [
            {"say": f"One hundred dollars a month, into {name}, starting in {yr}.", "photo": photo, "big": "$100", "sub": f"every month since {yr}"},
            {"say": f"Back then, {name} was {then}.", "photo": photo, "clip": {"kicker": place, "year": yr, "text": f"{name}: {then}"}},
            {"say": f"Today, those monthly payments would be worth about {g}.", "photo": "piggy bank coins", "big": g, "sub": "$100 a month, every month"},
            {"say": "Small, boring, every month. That's how wealth is built.", "photo": "calendar", "big": "Every month", "sub": "the habit that compounds"},
        ]}


def main(n: int) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    have = {p.stem for p in OUT.glob("*.json")}
    made = 0
    for i, t in enumerate(BANK):
        for fn in ((lump, dca) if i % 4 == 0 else (lump,)):        # monthly-habit format: weakest views, ~1 in 4
            sid, spec = fn(t)
            if sid in have or made >= n:
                continue
            (OUT / f"{sid}.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False), encoding="utf-8")
            have.add(sid); made += 1
            print("script:", sid)
            break
    print(f"{made} new scripts")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8)
