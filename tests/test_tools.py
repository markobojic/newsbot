"""Plumbing tests for tools/. No network: httpx2.get is replaced with a fake."""

import pytest

from tools import rss, weather

RSS_XML = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>T</title>
<item><title> First </title><link>https://x.test/1</link>
<pubDate>Mon, 16 Nov 2026 07:00:00 GMT</pubDate></item>
<item><title>Second</title><link>https://x.test/2</link></item>
</channel></rss>"""


class FakeResponse:
    def __init__(self, content=b"", json_data=None):
        self.content = content
        self._json = json_data

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


def test_fetch_feed_returns_trimmed_items(monkeypatch):
    monkeypatch.setattr(rss.httpx2, "get", lambda *a, **kw: FakeResponse(RSS_XML))
    items = rss.fetch_feed("https://x.test/feed", limit=5)
    assert items[0] == {
        "title": "First",
        "link": "https://x.test/1",
        "published": "Mon, 16 Nov 2026 07:00:00 GMT",
    }
    assert items[1]["published"] == "unknown"


def test_fetch_feed_respects_limit(monkeypatch):
    monkeypatch.setattr(rss.httpx2, "get", lambda *a, **kw: FakeResponse(RSS_XML))
    assert len(rss.fetch_feed("https://x.test/feed", limit=1)) == 1


def test_fetch_feed_raises_on_garbage(monkeypatch):
    monkeypatch.setattr(rss.httpx2, "get", lambda *a, **kw: FakeResponse(b"not xml <<<"))
    with pytest.raises(rss.FeedParseError):
        rss.fetch_feed("https://x.test/feed")


def test_get_forecast_flattens_daily_arrays(monkeypatch):
    data = {"daily": {
        "time": ["2026-11-16", "2026-11-17"],
        "temperature_2m_min": [5.6, 4.0],
        "temperature_2m_max": [11.5, 9.0],
        "precipitation_probability_max": [100, 20],
        "snowfall_sum": [0.0, 0.0],
    }}
    monkeypatch.setattr(weather.httpx2, "get", lambda *a, **kw: FakeResponse(json_data=data))
    days = weather.get_forecast(days=2)
    assert days[1] == {"date": "2026-11-17", "min_c": 4.0, "max_c": 9.0,
                       "precip_chance_pct": 20, "snowfall_cm": 0.0}
