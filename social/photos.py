"""Topic photo for a news card.

Source order (both free, both allow commercial use with no attribution required):
  1. Pexels      if PEXELS_API_KEY is set (free key at pexels.com/api)
  2. Pixabay     if PIXABAY_API_KEY is set (free key at pixabay.com/api/docs)
  3. Openverse   public-domain / CC0 images only, no key needed
The search uses a safe topic phrase picked from the story (never a person's name), so the photo
illustrates the subject rather than claiming to show the event. Returns a PIL image or None.
"""
from __future__ import annotations
import hashlib, io, os, re
import requests
from PIL import Image

UA = {"User-Agent": "FinanceHubW-news-cards/1.0 (+https://financehubw-site.vercel.app)"}
TOPICS = [  # first match wins
    (r"\b(bitcoin|btc)\b", "bitcoin coin"),
    (r"\b(ethereum|eth|solana|xrp|crypto|token|stablecoin|blockchain)", "cryptocurrency"),
    (r"\b(gold)\b", "gold bars"), (r"\b(silver)\b", "silver bullion"),
    (r"\b(oil|opec|crude|brent)\b", "oil refinery"), (r"\b(gas|lng)\b", "natural gas pipeline"),
    (r"\b(rbi|rupee|sensex|nifty|india)\b", "mumbai skyline"),
    (r"\b(fed|federal reserve|powell)\b", "federal reserve building"),
    (r"\b(wall street|s&p|nasdaq|dow|us stocks|nyse)\b", "wall street new york"),
    (r"\b(treasury|bond|yield)", "bonds finance"),
    (r"\b(ecb|euro|eurozone)\b", "euro banknotes"), (r"\b(esma|eu|europe|brussels)\b", "european union flags"),
    (r"\b(boe|uk|britain|london|pound|fca)\b", "london city skyline"),
    (r"\b(china|yuan|beijing|shanghai)\b", "shanghai skyline"), (r"\b(japan|yen|tokyo|nikkei)\b", "tokyo skyline"),
    (r"\b(inflation|cpi|prices)\b", "supermarket prices"),
    (r"\b(rate|rates|repo|interest|loan|mortgage)\b", "bank building"),
    (r"\b(earnings|profit|revenue|results)\b", "stock market chart"),
    (r"\b(ipo|listing|shares)\b", "stock exchange"),
    (r"\b(funds?|etf|investor)", "investment chart"),
    (r"\b(tariff|trade|export|import|shipping)\b", "container ship port"),
    (r"\b(ai|chip|semiconductor|tech)\b", "semiconductor chip"),
    (r"\b(collectible|cards?)\b", "collectible trading cards"),
    (r"\b(regulator|watchdog|rules?|law)\b", "government building columns"),
]
DEFAULT = "stock market"
# Fallback: the credited Wikimedia library the magazine already uses (magazine/photos/color).
LIBRARY = {"bitcoin coin": "bitcoin", "cryptocurrency": "bitcoin", "gold bars": "gold", "silver bullion": "mine",
           "oil refinery": "refinery", "natural gas pipeline": "tanker", "mumbai skyline": "atm",
           "federal reserve building": "fed", "wall street new york": "nyse", "bonds finance": "tradingfloor",
           "euro banknotes": "euro", "european union flags": "eu", "london city skyline": "london",
           "shanghai skyline": "shanghai", "tokyo skyline": "tokyo", "supermarket prices": "supermarket",
           "bank building": "atm", "stock market chart": "tradingfloor", "stock exchange": "nyse",
           "investment chart": "tradingfloor", "container ship port": "containership",
           "semiconductor chip": "chips", "collectible trading cards": "dollars",
           "government building columns": "eu", "stock market": "nyse"}
LIB_DIR = __import__("pathlib").Path(__file__).resolve().parent.parent / "magazine" / "photos" / "color"


def _library(q: str):
    name = LIBRARY.get(q, "nyse")
    path = LIB_DIR / f"{name}.jpg"
    if not path.exists():
        return None
    credit = ""
    for line in (LIB_DIR.parent / "CREDITS.md").read_text(encoding="utf-8").splitlines():
        m = re.match(rf"\|\s*color/{name}\.jpg\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|", line)
        if m:
            lic = m.group(3)
            credit = "" if lic.lower() in ("public domain", "cc0") else f"Photo: {m.group(2)} / {lic}"
    img = Image.open(path).convert("RGB")
    img.info["credit"] = credit
    return img


def query_for(text: str) -> str:
    low = text.lower()
    for pat, q in TOPICS:
        if re.search(pat, low):
            return q
    return DEFAULT


def _pick(urls: list[str], seed: str) -> str | None:
    if not urls:
        return None
    return urls[int(hashlib.sha1(seed.encode()).hexdigest(), 16) % len(urls)]


def _pexels(q: str, seed: str) -> str | None:
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return None
    r = requests.get("https://api.pexels.com/v1/search", timeout=20, headers={"Authorization": key},
                     params={"query": q, "per_page": 15, "orientation": "landscape"}).json()
    return _pick([p["src"]["large2x"] for p in r.get("photos", [])], seed)


def _pixabay(q: str, seed: str) -> str | None:
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        return None
    r = requests.get("https://pixabay.com/api/", timeout=20, params={
        "key": key, "q": q, "image_type": "photo", "orientation": "horizontal", "safesearch": "true",
        "min_width": 1200, "per_page": 20}).json()
    return _pick([h["largeImageURL"] for h in r.get("hits", [])], seed)


def _openverse(q: str, seed: str) -> str | None:
    r = requests.get("https://api.openverse.org/v1/images/", timeout=20, headers=UA,
                     params={"q": q, "license": "cc0,pdm", "page_size": 15, "mature": "false",
                             "aspect_ratio": "wide,square"}).json()
    good = [i["url"] for i in r.get("results", []) if (i.get("width") or 0) >= 1000]
    return _pick(good, seed)


def photo(text: str, seed: str) -> Image.Image | None:
    q = query_for(text)
    for src in (_pexels, _pixabay, _openverse):
        try:
            url = src(q, seed)
            if not url:
                continue
            raw = requests.get(url, timeout=30, headers=UA).content
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            if img.width >= 600:
                return img
        except Exception as e:  # noqa: BLE001  a missing photo never blocks a post
            print(f"photo ({src.__name__}, {q}): {e}")
    return _library(q)


def cover_fit(img: Image.Image, w: int, h: int) -> Image.Image:
    s = max(w / img.width, h / img.height)
    img = img.resize((int(img.width * s) + 1, int(img.height * s) + 1), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))
