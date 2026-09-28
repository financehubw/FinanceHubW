"""
News sources for FinanceHubW.
Each entry: (feed url, category). Dead or slow feeds are skipped automatically,
so adding more never breaks a run. Add a line here to add a source.
"""
from urllib.parse import quote_plus


def gnews(query: str, region: str = "IN") -> str:
    """Google News search feed: aggregates thousands of big and small outlets."""
    lang = {"IN": "en-IN", "US": "en-US", "GB": "en-GB"}[region]
    return (f"https://news.google.com/rss/search?q={quote_plus(query)}+when:6h"
            f"&hl={lang}&gl={region}&ceid={region}:en")


FEEDS = [
    # ---------------- Global markets & business (big outlets)
    ("https://www.cnbc.com/id/100003114/device/rss/rss.html", "markets"),
    ("https://www.cnbc.com/id/20910258/device/rss/rss.html", "economy"),
    ("https://www.cnbc.com/id/10000664/device/rss/rss.html", "markets"),       # finance
    ("https://www.cnbc.com/id/15839135/device/rss/rss.html", "markets"),       # earnings
    ("https://feeds.content.dowjones.io/public/rss/mw_topstories", "markets"),
    ("https://feeds.content.dowjones.io/public/rss/mw_marketpulse", "markets"),
    ("https://feeds.content.dowjones.io/public/rss/RSSMarketsMain", "markets"),
    ("https://finance.yahoo.com/news/rssindex", "markets"),
    ("https://feeds.bbci.co.uk/news/business/rss.xml", "economy"),
    ("https://www.theguardian.com/business/rss", "economy"),
    ("https://www.ft.com/markets?format=rss", "markets"),
    ("https://www.economist.com/finance-and-economics/rss.xml", "economy"),
    ("https://www.investing.com/rss/news_25.rss", "markets"),                  # stock market
    ("https://www.investing.com/rss/news_14.rss", "economy"),                  # economy
    ("https://www.investing.com/rss/news_11.rss", "markets"),                  # commodities
    ("https://www.investing.com/rss/news_1.rss", "markets"),                   # forex
    ("https://seekingalpha.com/market_currents.xml", "markets"),
    ("https://www.nasdaq.com/feed/rssoutbound?category=Markets", "markets"),
    ("https://www.fxstreet.com/rss/news", "markets"),
    ("https://oilprice.com/rss/main", "markets"),
    ("https://www.kitco.com/rss/KitcoNews.xml", "markets"),                    # gold
    ("https://www.zerohedge.com/fullrss2.xml", "markets"),
    ("https://www.benzinga.com/feed", "markets"),
    ("https://www.fool.com/a/feeds/partner/google/", "markets"),

    # ---------------- India markets & economy
    ("https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", "india-markets"),
    ("https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms", "india-economy"),
    ("https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms", "india-markets"),
    ("https://www.livemint.com/rss/markets", "india-markets"),
    ("https://www.livemint.com/rss/economy", "india-economy"),
    ("https://www.livemint.com/rss/money", "india-economy"),
    ("https://www.moneycontrol.com/rss/business.xml", "india-markets"),
    ("https://www.moneycontrol.com/rss/marketreports.xml", "india-markets"),
    ("https://www.moneycontrol.com/rss/economy.xml", "india-economy"),
    ("https://www.business-standard.com/rss/markets-106.rss", "india-markets"),
    ("https://www.business-standard.com/rss/economy-102.rss", "india-economy"),
    ("https://www.financialexpress.com/market/feed/", "india-markets"),
    ("https://www.financialexpress.com/economy/feed/", "india-economy"),
    ("https://www.thehindubusinessline.com/markets/feeder/default.rss", "india-markets"),
    ("https://www.thehindubusinessline.com/economy/feeder/default.rss", "india-economy"),
    ("https://www.ndtvprofit.com/feed", "india-markets"),
    ("https://www.businesstoday.in/rssfeeds/?id=home", "india-markets"),
    ("https://www.zeebiz.com/market-news.xml", "india-markets"),
    ("https://www.cnbctv18.com/commonfeeds/v1/cne/rss/market.xml", "india-markets"),
    ("https://www.cnbctv18.com/commonfeeds/v1/cne/rss/economy.xml", "india-economy"),

    # ---------------- Crypto
    ("https://www.coindesk.com/arc/outboundfeeds/rss/", "crypto"),
    ("https://cointelegraph.com/rss", "crypto"),
    ("https://decrypt.co/feed", "crypto"),
    ("https://www.theblock.co/rss.xml", "crypto"),
    ("https://bitcoinmagazine.com/feed", "crypto"),
    ("https://cryptoslate.com/feed/", "crypto"),
    ("https://cryptonews.com/news/feed/", "crypto"),
    ("https://u.today/rss", "crypto"),
    ("https://beincrypto.com/feed/", "crypto"),
    ("https://www.newsbtc.com/feed/", "crypto"),

    # ---------------- Regulators, central banks, governments
    ("https://www.sec.gov/news/pressreleases.rss", "policy"),
    ("https://www.federalreserve.gov/feeds/press_all.xml", "policy"),
    ("https://www.ecb.europa.eu/rss/press.html", "policy"),
    ("https://www.bankofengland.co.uk/rss/news", "policy"),
    ("https://www.imf.org/en/News/RSS", "policy"),
    ("https://www.cftc.gov/RSS/RSSGP/rssgp.xml", "policy"),
    ("https://www.rbi.org.in/pressreleases_rss.xml", "policy"),
    ("https://www.sebi.gov.in/sebirss.xml", "policy"),
    ("https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3", "policy"),     # PIB finance

    # ---------------- Google News sweeps (thousands of smaller outlets)
    (gnews("Sensex OR Nifty"), "india-markets"),
    (gnews("RBI OR SEBI policy"), "policy"),
    (gnews("India budget OR GST OR income tax"), "policy"),
    (gnews("IPO India"), "india-markets"),
    (gnews("rupee dollar forex"), "india-economy"),
    (gnews("stock market", "US"), "markets"),
    (gnews("Federal Reserve OR inflation OR CPI", "US"), "policy"),
    (gnews("earnings results", "US"), "markets"),
    (gnews("bitcoin OR ethereum OR crypto", "US"), "crypto"),
    (gnews("crypto regulation", "US"), "policy"),
    (gnews("oil prices OR gold prices", "US"), "markets"),
    (gnews("FTSE OR Bank of England", "GB"), "markets"),
    (gnews("Nikkei OR Hang Seng OR China stocks", "US"), "markets"),
    (gnews("tariffs trade war", "US"), "economy"),
    (gnews("recession OR GDP growth", "US"), "economy"),
]
