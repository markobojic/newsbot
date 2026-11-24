"""Last close and daily change for one ticker, from Yahoo's chart endpoint. Plain Python, no Claude.

Unofficial endpoint: no key, but it may answer 429 when called too often.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import httpx2

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


class MarketDataError(Exception):
    """Yahoo answered, but without enough prices to compute a daily change."""


def yahoo_symbol(ticker: str) -> str:
    """Ticker as I know it -> Yahoo symbol: 'BRK.B' -> 'BRK-B' ('BRK.B' is a 404 on Yahoo)."""
    return ticker.replace(".", "-")


def get_quote(ticker: str) -> dict:
    """Return {ticker, price, currency, change_pct, as_of} for the last trading day."""
    resp = httpx2.get(
        CHART_URL.format(symbol=yahoo_symbol(ticker)),
        # 5 days, so there are always two closes even after a weekend or holiday.
        params={"range": "5d", "interval": "1d"},
        headers={"User-Agent": "Mozilla/5.0"},  # Yahoo rejects requests without one
        timeout=10,
    )
    resp.raise_for_status()
    result = resp.json()["chart"]["result"][0]
    meta = result["meta"]
    # Daily change = last close vs the close before it. NOT meta.chartPreviousClose:
    # that is the close before the 5-day window, so it gives the wrong number.
    # A day without trading can show up as None.
    closes = [c for c in result["indicators"]["quote"][0]["close"] if c is not None]
    if len(closes) < 2:
        raise MarketDataError(f"{ticker}: fewer than 2 closes in the last 5 days")
    price, previous = closes[-1], closes[-2]
    # Date of the last price in the exchange's own time zone (it closes at 22:00 in Belgrade).
    as_of = datetime.fromtimestamp(
        meta["regularMarketTime"], ZoneInfo(meta.get("exchangeTimezoneName", "America/New_York"))
    ).date()
    return {
        "ticker": ticker,
        "price": round(price, 2),
        "currency": meta["currency"],
        "change_pct": round((price / previous - 1) * 100, 2),
        "as_of": as_of.isoformat(),
    }
