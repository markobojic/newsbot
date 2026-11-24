"""search_news adapter: matches, partial failures, empty vs failed. No network."""

import pytest

from errors import ToolError
from tools import definitions

FEEDS = {
    "n1": [{"title": "Vukićević polivena jogurtom", "link": "https://n1.test/1", "published": "x"}],
    "rts": [{"title": "Нападнута Лидија Вукићевић", "link": "https://rts.test/1", "published": "x"}],
    "danas": [{"title": "Budžet za 2027", "link": "https://danas.test/1", "published": "x"}],
}


@pytest.fixture
def fake_feeds(monkeypatch):
    """Only n1, rts and danas exist; newsmax fails; every other outlet is empty."""

    def read_feed(source, limit):
        if source == "newsmax":
            raise ToolError("transient", False, "newsmax did not answer.", "newsmax")
        return FEEDS.get(source, [])

    monkeypatch.setattr(definitions, "read_feed", read_feed)


def test_matches_across_scripts_and_keeps_original_title(fake_feeds):
    out = definitions.run_search_news({"query": "vukicevic"})
    titles = {r["source"]: r["title"] for r in out["results"]}
    assert titles == {"n1": "Vukićević polivena jogurtom", "rts": "Нападнута Лидија Вукићевић"}
    assert out["truncated"] is False


def test_failed_is_not_searched(fake_feeds):
    out = definitions.run_search_news({"query": "vukicevic"})
    assert "newsmax" not in out["searched"]  # unknown, not silent
    assert "danas" in out["searched"]  # read, no match = didn't cover it
    assert [f["source"] for f in out["failed_sources"]] == ["newsmax"]


def test_camp_filter(fake_feeds):
    out = definitions.run_search_news({"query": "vukicevic", "camp": "public"})
    assert out["searched"] == ["rts"]
    assert [r["source"] for r in out["results"]] == ["rts"]


def test_all_failed_raises(monkeypatch):
    def read_feed(source, limit):
        raise ToolError("transient", False, "down", source)

    monkeypatch.setattr(definitions, "read_feed", read_feed)
    with pytest.raises(ToolError) as info:
        definitions.run_search_news({"query": "budzet", "camp": "student"})
    assert info.value.is_retryable is False


def test_results_are_capped(monkeypatch):
    many = [{"title": f"budžet {i}", "link": f"https://x.test/{i}", "published": "x"} for i in range(50)]
    monkeypatch.setattr(definitions, "read_feed", lambda source, limit: many if source == "n1" else [])
    out = definitions.run_search_news({"query": "budzet"})
    assert len(out["results"]) == definitions.MAX_SEARCH_RESULTS
    assert out["truncated"] is True


@pytest.mark.parametrize("bad", [{"query": ""}, {"query": "x"}, {"query": "budzet", "camp": "studnet"}])
def test_validation(fake_feeds, bad):
    with pytest.raises(ToolError) as info:
        definitions.run_search_news(bad)
    assert info.value.category == "validation"


def test_every_tool_has_a_handler():
    assert [t["name"] for t in definitions.TOOLS] == list(definitions.HANDLERS)


def test_cap_keeps_every_outlet(monkeypatch):
    # novosti (listed first) has 50 matches, rts has 1: rts must survive the cap.
    many = [{"title": f"budžet {i}", "link": f"https://x.test/{i}", "published": "x"} for i in range(50)]
    feeds = {"novosti": many, "rts": [{"title": "буџет", "link": "https://rts.test/1", "published": "x"}]}
    monkeypatch.setattr(definitions, "read_feed", lambda source, limit: feeds.get(source, []))
    out = definitions.run_search_news({"query": "budzet"})
    assert {r["source"] for r in out["results"]} == {"novosti", "rts"}
