"""NBS scraper and get_rsd_rate adapter. No network: parses a trimmed copy of the real page."""

from datetime import date

import pytest

from errors import ToolError
from tools import definitions, fx

# Trimmed from the real page for 22.11.2026 (a Saturday -> Friday's list), Cyrillic as entities.
SATURDAY_PAGE = """
<h4>&#x41A;&#x423;&#x420;&#x421;&#x41D;&#x410; &#x41B;&#x418;&#x421;&#x422;&#x410; &#x411;&#x420;. 222
&#x417;&#x410; &#x417;&#x412;&#x410;&#x41D;&#x418;&#x427;&#x41D;&#x418; &#x421;&#x420;&#x415;&#x414;&#x40A;&#x418; &#x41A;&#x423;&#x420;&#x421;
&#x424;&#x41E;&#x420;&#x41C;&#x418;&#x420;&#x410;&#x41D;&#x410; &#x41D;&#x410; &#x414;&#x410;&#x41D; 20.11.2026. &#x413;&#x41E;&#x414;&#x418;&#x41D;&#x415;</h4>
<table><tr><td>EUR</td><td>978</td><td>&#x415;&#x41C;&#x423;</td><td>1</td><td>117,6412</td></tr>
<tr><td>AUD</td><td>036</td><td>&#x410;&#x443;&#x441;&#x442;&#x440;&#x430;&#x43B;&#x438;&#x458;&#x430;</td><td>1</td><td>76,1234</td></tr></table>
"""


def test_parse_takes_list_date_not_requested_date():
    assert fx.parse_list(SATURDAY_PAGE) == {
        "rate": 117.6412,  # decimal comma -> float
        "list_date": "2026-11-20",  # Friday's list, although Saturday was asked
        "list_number": 222,
    }


def test_layout_change_raises():
    with pytest.raises(fx.FxParseError):
        fx.parse_list("<html><body>Maintenance</body></html>")


# --- get_rsd_rate adapter -----------------------------------------------------

@pytest.fixture
def saturday(monkeypatch):
    monkeypatch.setattr(definitions, "today_in_belgrade", lambda: date(2026, 11, 22))
    monkeypatch.setattr("errors.time.sleep", lambda seconds: None)


def list_from(list_date):
    return lambda on: {"rate": 117.6412, "list_date": list_date, "list_number": 222}


def test_weekend_returns_fridays_list(saturday, monkeypatch):
    monkeypatch.setattr(fx, "get_eur_rsd", list_from("2026-11-20"))
    assert definitions.run_get_rsd_rate({})["list_date"] == "2026-11-20"


def test_list_older_than_a_week_is_an_error(saturday, monkeypatch):
    monkeypatch.setattr(fx, "get_eur_rsd", list_from("2026-11-10"))
    with pytest.raises(ToolError) as info:
        definitions.run_get_rsd_rate({})
    assert (info.value.category, info.value.is_retryable) == ("permission", False)
    assert "12 days old" in info.value.message


def test_layout_change_is_permission(saturday, monkeypatch):
    def broken(on):
        raise fx.FxParseError("no EUR row")

    monkeypatch.setattr(fx, "get_eur_rsd", broken)
    with pytest.raises(ToolError) as info:
        definitions.run_get_rsd_rate({})
    assert (info.value.category, info.value.is_retryable) == ("permission", False)


def test_nbs_timeout_is_retried(saturday, monkeypatch):
    monkeypatch.setenv("CHAOS", "nbs:timeout")
    with pytest.raises(ToolError) as info:
        definitions.run_get_rsd_rate({})
    assert "3 attempts" in info.value.message
