"""Chaos switch tests: faked outages flow through the real adapter. No network."""

import pytest

from errors import ToolError
from tools import chaos, definitions


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    # Retries would really sleep 1s + 2s; skip the waiting, keep the counting.
    monkeypatch.setattr("errors.time.sleep", lambda seconds: None)


def test_off_when_unset(monkeypatch):
    monkeypatch.delenv("CHAOS", raising=False)
    chaos.maybe_fail("n1")  # does nothing


def test_timeout_is_transient_and_retried_then_given_up(monkeypatch):
    monkeypatch.setenv("CHAOS", "n1:timeout")
    with pytest.raises(ToolError) as info:
        definitions.run_fetch_feed({"source": "n1"})
    err = info.value
    assert (err.category, err.is_retryable, err.source) == ("transient", False, "n1")
    assert "3 attempts" in err.message


def test_403_is_permission_and_not_retried(monkeypatch, capsys):
    monkeypatch.setenv("CHAOS", "pink:403")
    with pytest.raises(ToolError) as info:
        definitions.run_fetch_feed({"source": "pink"})
    assert (info.value.category, info.value.is_retryable) == ("permission", False)
    assert capsys.readouterr().err.count("[chaos]") == 1  # one attempt, no retries


def test_only_the_named_source_fails(monkeypatch):
    monkeypatch.setenv("CHAOS", "n1:timeout")
    chaos.maybe_fail("danas")  # not listed: does nothing


def test_bad_spec_crashes(monkeypatch):
    monkeypatch.setenv("CHAOS", "n1:slow")
    with pytest.raises(ValueError, match="Bad CHAOS entry"):
        chaos.maybe_fail("n1")
