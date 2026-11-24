"""get_holdings_quotes adapter: notable, partial failures, chaos. No network."""

import pytest

from errors import ToolError
from tools import definitions, markets

QUOTES = {
    "ARKK": {"ticker": "ARKK", "price": 69.36, "currency": "USD", "change_pct": 8.0, "as_of": "2026-11-23"},
    "BRK.B": {"ticker": "BRK.B", "price": 572.36, "currency": "USD", "change_pct": -1.5, "as_of": "2026-11-23"},
    "SPCX": {"ticker": "SPCX", "price": 133.35, "currency": "USD", "change_pct": -3.0, "as_of": "2026-11-23"},
}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("errors.time.sleep", lambda seconds: None)


@pytest.fixture
def fake_yahoo(monkeypatch):
    monkeypatch.setattr(markets, "get_quote", lambda ticker: QUOTES[ticker])


def test_notable_uses_absolute_move_above_threshold(fake_yahoo):
    out = definitions.run_get_holdings_quotes({})
    notable = {q["ticker"]: q["notable"] for q in out["quotes"]}
    # +8.0 yes; -1.5 is not ABOVE 1.5; -3.0 yes (a drop counts too)
    assert notable == {"ARKK": True, "BRK.B": False, "SPCX": True}
    assert {q["name"] for q in out["quotes"]} == {"ARK Innovation ETF", "Berkshire Hathaway", "SpaceX"}
    assert out["notable_move_pct"] == 1.5
    assert out["failed"] == []


def test_one_ticker_down_keeps_the_others(fake_yahoo, monkeypatch):
    monkeypatch.setenv("CHAOS", "SPCX:429")
    out = definitions.run_get_holdings_quotes({})
    assert [q["ticker"] for q in out["quotes"]] == ["ARKK", "BRK.B"]
    assert out["failed"][0]["source"] == "SPCX"
    assert out["failed"][0]["category"] == "transient"


def test_too_little_data_is_business(monkeypatch):
    def get_quote(ticker):
        if ticker == "SPCX":
            raise markets.MarketDataError("fewer than 2 closes")
        return QUOTES[ticker]

    monkeypatch.setattr(markets, "get_quote", get_quote)
    out = definitions.run_get_holdings_quotes({})
    assert len(out["quotes"]) == 2
    assert (out["failed"][0]["source"], out["failed"][0]["category"]) == ("SPCX", "business")


def test_all_failed_raises(fake_yahoo, monkeypatch):
    monkeypatch.setenv("CHAOS", "ARKK:503,BRK.B:503,SPCX:503")
    with pytest.raises(ToolError) as info:
        definitions.run_get_holdings_quotes({})
    assert (info.value.category, info.value.is_retryable) == ("transient", False)
