"""
Market snapshots from live price data (Yahoo Finance via yfinance).
Numbers come straight from market data, not from headlines or AI.
"""
from __future__ import annotations

import yfinance as yf

# (label, ticker, decimals, prefix)
INDIA = [("Sensex", "^BSESN", 0, ""), ("Nifty 50", "^NSEI", 0, ""), ("Bank Nifty", "^NSEBANK", 0, ""),
         ("USD/INR", "INR=X", 2, "₹"), ("Gold", "GC=F", 0, "$"), ("Bitcoin", "BTC-USD", 0, "$")]
GLOBAL = [("S&P 500", "^GSPC", 0, ""), ("Nasdaq", "^IXIC", 0, ""), ("Dow", "^DJI", 0, ""),
          ("FTSE 100", "^FTSE", 0, ""), ("Nikkei", "^N225", 0, ""), ("Brent oil", "BZ=F", 2, "$"),
          ("Bitcoin", "BTC-USD", 0, "$")]


def _quote(ticker: str) -> tuple[float, float] | None:
    hist = yf.Ticker(ticker).history(period="5d", interval="1d", auto_adjust=False)
    closes = hist["Close"].dropna()
    if len(closes) < 2:
        return None
    last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
    return last, (last - prev) / prev * 100


def snapshot(title: str, items: list[tuple]) -> str | None:
    lines = [title, ""]
    for label, ticker, dec, prefix in items:
        try:
            q = _quote(ticker)
        except Exception:  # noqa: BLE001
            q = None
        if not q:
            continue
        price, pct = q
        arrow = "🟢" if pct > 0.05 else "🔴" if pct < -0.05 else "⚪"
        lines.append(f"{arrow} {label}: {prefix}{price:,.{dec}f} ({pct:+.2f}%)")
    if len(lines) < 5:  # need at least 3 working quotes
        return None
    lines += ["", "🟢 up · 🔴 down · vs previous close", "#Markets #StockMarket"]
    return "\n".join(lines)


def india_close() -> str | None:
    return snapshot("📈 INDIA MARKETS AT CLOSE", INDIA)


def global_close() -> str | None:
    return snapshot("🌐 GLOBAL MARKETS OVERNIGHT", GLOBAL)
