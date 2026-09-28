"""
Every news source the FinanceHubW bot reads, grouped by region.

Two kinds of source:
1. Direct RSS feeds from publishers, exchanges, central banks and regulators.
2. Google News searches per region. Each one pulls from hundreds of outlets
   (big and small), and every item carries its real publisher's name, which
   the bot credits in the tweet.

A dead or blocked feed is skipped automatically, so adding more is always safe.
"""
from urllib.parse import quote_plus

# Region labels shown in tweets
REGIONS = {
    # South Asia
    "india": "🇮🇳 India", "pakistan": "🇵🇰 Pakistan", "bangladesh": "🇧🇩 Bangladesh",
    "srilanka": "🇱🇰 Sri Lanka", "nepal": "🇳🇵 Nepal",
    # East Asia
    "china": "🇨🇳 China", "japan": "🇯🇵 Japan", "korea": "🇰🇷 South Korea",
    "hongkong": "🇭🇰 Hong Kong", "taiwan": "🇹🇼 Taiwan",
    # Southeast Asia & Oceania
    "singapore": "🇸🇬 Singapore", "indonesia": "🇮🇩 Indonesia", "malaysia": "🇲🇾 Malaysia",
    "thailand": "🇹🇭 Thailand", "vietnam": "🇻🇳 Vietnam", "philippines": "🇵🇭 Philippines",
    "australia": "🇦🇺 Australia", "newzealand": "🇳🇿 New Zealand",
    # Americas
    "us": "🇺🇸 US", "canada": "🇨🇦 Canada", "mexico": "🇲🇽 Mexico", "brazil": "🇧🇷 Brazil",
    "argentina": "🇦🇷 Argentina", "chile": "🇨🇱 Chile", "colombia": "🇨🇴 Colombia",
    "latam": "🌎 Latin America",
    # Europe
    "uk": "🇬🇧 UK", "europe": "🇪🇺 Europe", "germany": "🇩🇪 Germany", "france": "🇫🇷 France",
    "italy": "🇮🇹 Italy", "spain": "🇪🇸 Spain", "switzerland": "🇨🇭 Switzerland",
    "nordics": "🇸🇪 Nordics", "russia": "🇷🇺 Russia", "turkey": "🇹🇷 Turkey",
    # Middle East & Africa
    "saudi": "🇸🇦 Saudi Arabia", "uae": "🇦🇪 UAE", "qatar": "🇶🇦 Qatar", "israel": "🇮🇱 Israel",
    "iran": "🇮🇷 Iran", "egypt": "🇪🇬 Egypt", "middleeast": "🌍 Middle East",
    "southafrica": "🇿🇦 South Africa", "nigeria": "🇳🇬 Nigeria", "kenya": "🇰🇪 Kenya",
    "africa": "🌍 Africa",
    # Wider
    "asia": "🌏 Asia", "global": "🌐 Global",
}

# (url, region, category, official)  official = central bank / regulator / exchange
DIRECT_FEEDS = [
    # ---------- Global / wires
    ("https://feeds.bbci.co.uk/news/business/rss.xml", "global", "economy", False),
    ("https://www.cnbc.com/id/100727362/device/rss/rss.html", "global", "markets", False),
    ("https://www.aljazeera.com/xml/rss/all.xml", "global", "economy", False),
    ("https://www.ft.com/markets?format=rss", "global", "markets", False),
    ("https://www.economist.com/finance-and-economics/rss.xml", "global", "economy", False),
    ("https://www.imf.org/en/News/RSS?Language=ENG", "global", "policy", True),
    ("https://www.worldbank.org/en/news/all?format=rss", "global", "policy", True),
    ("https://www.bis.org/doclist/all_pressrels.rss", "global", "policy", True),
    # ---------- US
    ("https://www.cnbc.com/id/100003114/device/rss/rss.html", "us", "markets", False),
    ("https://www.cnbc.com/id/20910258/device/rss/rss.html", "us", "economy", False),
    ("https://www.cnbc.com/id/10000664/device/rss/rss.html", "us", "finance", False),
    ("https://feeds.content.dowjones.io/public/rss/mw_topstories", "us", "markets", False),
    ("https://feeds.content.dowjones.io/public/rss/mw_marketpulse", "us", "markets", False),
    ("https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "us", "markets", False),
    ("https://finance.yahoo.com/news/rssindex", "us", "markets", False),
    ("https://www.investing.com/rss/news.rss", "us", "markets", False),
    ("https://seekingalpha.com/market_currents.xml", "us", "markets", False),
    ("https://www.nasdaq.com/feed/rssoutbound?category=Markets", "us", "markets", False),
    ("https://fortune.com/section/finance/feed/", "us", "finance", False),
    ("https://www.businessinsider.com/sai/rss", "us", "markets", False),
    ("https://www.federalreserve.gov/feeds/press_all.xml", "us", "policy", True),
    ("https://www.sec.gov/news/pressreleases.rss", "us", "policy", True),
    ("https://home.treasury.gov/system/files/126/ofac.xml", "us", "policy", True),
    ("https://www.cftc.gov/RSS/RSSGP/rssgp.xml", "us", "policy", True),
    # ---------- India
    ("https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", "india", "markets", False),
    ("https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms", "india", "economy", False),
    ("https://www.livemint.com/rss/markets", "india", "markets", False),
    ("https://www.livemint.com/rss/money", "india", "finance", False),
    ("https://www.livemint.com/rss/economy", "india", "economy", False),
    ("https://www.moneycontrol.com/rss/business.xml", "india", "markets", False),
    ("https://www.moneycontrol.com/rss/marketreports.xml", "india", "markets", False),
    ("https://www.moneycontrol.com/rss/economy.xml", "india", "economy", False),
    ("https://www.business-standard.com/rss/markets-106.rss", "india", "markets", False),
    ("https://www.business-standard.com/rss/economy-102.rss", "india", "economy", False),
    ("https://www.thehindubusinessline.com/markets/feeder/default.rss", "india", "markets", False),
    ("https://www.financialexpress.com/market/feed/", "india", "markets", False),
    ("https://www.ndtvprofit.com/feed", "india", "markets", False),
    ("https://www.zeebiz.com/latest.xml/feed", "india", "markets", False),
    ("https://www.rbi.org.in/pressreleases_rss.xml", "india", "policy", True),
    ("https://www.rbi.org.in/notifications_rss.xml", "india", "policy", True),
    ("https://www.sebi.gov.in/sebirss.xml", "india", "policy", True),
    ("https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3", "india", "policy", True),
    # ---------- UK / Europe
    ("https://www.theguardian.com/uk/business/rss", "uk", "economy", False),
    ("https://www.cityam.com/feed/", "uk", "markets", False),
    ("https://www.bankofengland.co.uk/rss/news", "uk", "policy", True),
    ("https://www.fca.org.uk/news/rss.xml", "uk", "policy", True),
    ("https://www.ecb.europa.eu/rss/press.html", "europe", "policy", True),
    ("https://www.esma.europa.eu/rss.xml", "europe", "policy", True),
    ("https://www.euronews.com/rss?level=vertical&name=business", "europe", "economy", False),
    ("https://www.dw.com/rss/rss-en-bus", "europe", "economy", False),
    # ---------- Asia-Pacific
    ("https://www.scmp.com/rss/92/feed", "china", "economy", False),
    ("https://www.scmp.com/rss/10/feed", "hongkong", "markets", False),
    ("https://asia.nikkei.com/rss/feed/nar", "japan", "markets", False),
    ("https://www.japantimes.co.jp/feed/business/", "japan", "economy", False),
    ("https://www.boj.or.jp/en/rss/whatsnew.xml", "japan", "policy", True),
    ("https://www.straitstimes.com/news/business/rss.xml", "singapore", "economy", False),
    ("https://www.businesstimes.com.sg/rss/top-stories", "singapore", "markets", False),
    ("https://www.mas.gov.sg/rss/news", "singapore", "policy", True),
    ("https://www.abc.net.au/news/feed/51892/rss.xml", "australia", "economy", False),
    ("https://www.rba.gov.au/rss/rss-cb-media-releases.xml", "australia", "policy", True),
    ("https://www.koreaherald.com/rss/020000000000.xml", "korea", "economy", False),
    # ---------- Americas
    ("https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/business/", "canada", "economy", False),
    ("https://www.bankofcanada.ca/content_type/press-releases/feed/", "canada", "policy", True),
    ("https://www.batimes.com.ar/feed", "latam", "economy", False),
    ("https://mercopress.com/rss/economy", "latam", "economy", False),
    # ---------- Middle East / Africa
    ("https://www.arabianbusiness.com/feed", "middleeast", "economy", False),
    ("https://gulfnews.com/rss/business", "middleeast", "economy", False),
    ("https://www.zawya.com/sitemaps/en/rss", "middleeast", "markets", False),
    ("https://businessday.ng/feed/", "africa", "economy", False),
    ("https://www.moneyweb.co.za/feed/", "africa", "markets", False),
    ("https://www.businessdailyafrica.com/rss", "africa", "economy", False),
    # ---------- Crypto
    ("https://www.coindesk.com/arc/outboundfeeds/rss/", "global", "crypto", False),
    ("https://cointelegraph.com/rss", "global", "crypto", False),
    ("https://decrypt.co/feed", "global", "crypto", False),
    ("https://www.theblock.co/rss.xml", "global", "crypto", False),
    ("https://bitcoinmagazine.com/.rss/full/", "global", "crypto", False),
    ("https://cryptoslate.com/feed/", "global", "crypto", False),
    ("https://cryptonews.com/news/feed/", "global", "crypto", False),
    ("https://www.dlnews.com/arc/outboundfeeds/rss/", "global", "crypto", False),
    # ---------- Commodities / FX
    ("https://oilprice.com/rss/main", "global", "commodities", False),
    ("https://www.fxstreet.com/rss/news", "global", "forex", False),
    ("https://www.kitco.com/rss/news.xml", "global", "commodities", False),
]

# Google News searches: (region, country code, language, [queries])
_GN = [
    # South Asia
    ("india", "IN", "en-IN", ["Sensex Nifty", "RBI policy", "SEBI", "Indian rupee", "India GDP inflation",
                              "India IPO", "India budget tax GST", "India crypto", "India banks results"]),
    ("pakistan", "PK", "en-US", ["Pakistan economy PSX rupee", "State Bank of Pakistan IMF"]),
    ("bangladesh", "BD", "en-US", ["Bangladesh economy taka"]),
    ("srilanka", "LK", "en-US", ["Sri Lanka economy central bank"]),
    ("nepal", "NP", "en-US", ["Nepal economy Nepal Rastra Bank"]),
    # East Asia
    ("china", "HK", "en-US", ["China economy PBOC", "yuan", "Shanghai Shenzhen stocks", "China property"]),
    ("japan", "JP", "en-US", ["Nikkei stocks", "Bank of Japan", "yen"]),
    ("korea", "KR", "en-US", ["KOSPI", "Bank of Korea won"]),
    ("hongkong", "HK", "en-US", ["Hang Seng"]),
    ("taiwan", "TW", "en-US", ["Taiwan stocks TAIEX", "Taiwan economy"]),
    # Southeast Asia & Oceania
    ("singapore", "SG", "en-SG", ["Singapore economy MAS", "STI stocks"]),
    ("indonesia", "ID", "en-ID", ["Indonesia economy rupiah Bank Indonesia"]),
    ("malaysia", "MY", "en-MY", ["Malaysia economy ringgit Bursa"]),
    ("thailand", "TH", "en-US", ["Thailand economy baht SET index"]),
    ("vietnam", "VN", "en-US", ["Vietnam economy VN-Index dong"]),
    ("philippines", "PH", "en-PH", ["Philippines economy peso PSEi BSP"]),
    ("australia", "AU", "en-AU", ["ASX stocks", "Reserve Bank of Australia"]),
    ("newzealand", "NZ", "en-NZ", ["Reserve Bank of New Zealand NZX"]),
    # Americas
    ("us", "US", "en-US", ["stock market Dow S&P 500 Nasdaq", "Federal Reserve rates", "US inflation CPI jobs",
                           "Treasury yields", "earnings results", "SEC crypto", "IPO Wall Street",
                           "US tariffs trade", "US banks"]),
    ("canada", "CA", "en-CA", ["TSX stocks", "Bank of Canada"]),
    ("mexico", "MX", "en-US", ["Mexico economy peso Banxico"]),
    ("brazil", "BR", "en-US", ["Brazil economy Bovespa real"]),
    ("argentina", "AR", "en-US", ["Argentina economy peso inflation"]),
    ("chile", "CL", "en-US", ["Chile economy copper peso"]),
    ("colombia", "CO", "en-US", ["Colombia economy peso"]),
    # Europe
    ("uk", "GB", "en-GB", ["FTSE 100", "Bank of England", "UK economy inflation", "pound sterling"]),
    ("europe", "IE", "en-IE", ["ECB interest rates", "European stocks STOXX", "euro zone economy", "EU regulation finance"]),
    ("germany", "DE", "en-US", ["Germany economy DAX"]),
    ("france", "FR", "en-US", ["France economy CAC 40"]),
    ("italy", "IT", "en-US", ["Italy economy FTSE MIB"]),
    ("spain", "ES", "en-US", ["Spain economy IBEX"]),
    ("switzerland", "CH", "en-US", ["Swiss franc SNB"]),
    ("nordics", "SE", "en-US", ["Riksbank Sweden Norway Denmark economy"]),
    ("russia", "US", "en-US", ["Russia economy ruble sanctions"]),
    ("turkey", "TR", "en-US", ["Turkey lira central bank"]),
    # Middle East & Africa
    ("saudi", "SA", "en-US", ["Saudi Arabia economy Tadawul Aramco"]),
    ("uae", "AE", "en-AE", ["UAE Dubai Abu Dhabi economy markets"]),
    ("qatar", "QA", "en-US", ["Qatar economy"]),
    ("israel", "IL", "en-US", ["Israel economy shekel Tel Aviv stocks"]),
    ("iran", "US", "en-US", ["Iran economy rial"]),
    ("egypt", "EG", "en-US", ["Egypt economy pound central bank"]),
    ("middleeast", "AE", "en-AE", ["Gulf markets", "OPEC oil"]),
    ("southafrica", "ZA", "en-ZA", ["JSE stocks rand SARB"]),
    ("nigeria", "NG", "en-NG", ["Nigeria economy naira CBN"]),
    ("kenya", "KE", "en-KE", ["Kenya economy shilling"]),
    ("africa", "ZA", "en-ZA", ["Africa economy markets"]),
    # Global
    ("global", "US", "en-US", ["global markets", "IMF World Bank economy", "gold price", "oil prices",
                               "bitcoin ethereum", "crypto regulation", "forex dollar index",
                               "global trade shipping", "commodities wheat copper"]),
]

GOOGLE_NEWS = [
    (f"https://news.google.com/rss/search?q={quote_plus(q + ' when:2h')}"
     f"&hl={hl}&gl={gl}&ceid={gl}:{hl.split('-')[0]}", region, "markets", False)
    for region, gl, hl, qs in _GN for q in qs
]

FEEDS = DIRECT_FEEDS + GOOGLE_NEWS

# Outlets with strong editorial fact-checking. A story from one of these (or an
# official body) can be posted from a single report; anything else needs a
# second independent outlet reporting the same story.
TIER1 = {
    "reuters", "bloomberg", "associated press", "ap news", "financial times", "wall street journal",
    "the economist", "bbc", "cnbc", "marketwatch", "barron's", "nikkei", "the guardian",
    "economic times", "mint", "livemint", "business standard", "moneycontrol", "the hindu businessline",
    "financial express", "ndtv profit", "south china morning post", "straits times", "business times",
    "globe and mail", "abc news", "abc", "al jazeera", "coindesk", "the block", "yahoo finance",
    "forbes", "fortune", "business insider", "axios", "cnn", "new york times", "washington post",
    "nikkei asia", "japan times", "dw", "euronews", "gulf news", "arabian business", "moneyweb",
}
