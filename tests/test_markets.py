"""Yahoo quote plumbing. No network: httpx2.get is replaced with a fake."""

import pytest

from tools import markets


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def chart(closes, previous_window_close=71.55):
    return {"chart": {"result": [{
        "meta": {
            "currency": "USD",
            "regularMarketTime": 1795467600,  # 2026-11-23 16:00 New York
            "exchangeTimezoneName": "America/New_York",
            "chartPreviousClose": previous_window_close,
        },
        "indicators": {"quote": [{"close": closes}]},
    }]}}


def test_symbol_conversion():
    assert markets.yahoo_symbol("BRK.B") == "BRK-B"
    assert markets.yahoo_symbol("ARKK") == "ARKK"


def test_change_uses_last_two_closes_not_chart_previous_close(monkeypatch):
    seen = {}

    def fake_get(url, **kw):
        seen["url"] = url
        return FakeResponse(chart([70.84, 71.06, 68.93, 64.22, 69.36]))

    monkeypatch.setattr(markets.httpx2, "get", fake_get)
    quote = markets.get_quote("BRK.B")
    assert seen["url"].endswith("/BRK-B")
    assert quote == {
        "ticker": "BRK.B", "price": 69.36, "currency": "USD",
        "change_pct": 8.0,  # 64.22 -> 69.36; chartPreviousClose would give -3.06
        "as_of": "2026-11-23",
    }


def test_skips_missing_closes(monkeypatch):
    monkeypatch.setattr(markets.httpx2, "get", lambda *a, **kw: FakeResponse(chart([100.0, None, 110.0, None])))
    assert markets.get_quote("ARKK")["change_pct"] == 10.0


def test_too_few_closes_raises(monkeypatch):
    monkeypatch.setattr(markets.httpx2, "get", lambda *a, **kw: FakeResponse(chart([None, 50.0])))
    with pytest.raises(markets.MarketDataError):
        markets.get_quote("SPCX")
