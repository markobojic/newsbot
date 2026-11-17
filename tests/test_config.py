"""Config loading tests. No network: the YAML files are local."""

import pytest

import config


def test_real_sources_load_with_valid_camps():
    outlets = config.load_sources()
    assert {o["camp"] for o in outlets.values()} == config.CAMPS
    assert "informer" not in outlets  # DECISIONS.md


def test_unknown_camp_raises(tmp_path):
    bad = tmp_path / "sources.yaml"
    bad.write_text(
        "outlets:\n"
        "  n1: {name: N1, camp: studnet, language: sr-Latn, url: https://x.test}\n"
    )
    with pytest.raises(ValueError, match="unknown camp 'studnet'"):
        config.load_sources(bad)


def test_missing_url_raises(tmp_path):
    bad = tmp_path / "sources.yaml"
    bad.write_text("outlets:\n  n1: {name: N1, camp: student, language: sr-Latn}\n")
    with pytest.raises(ValueError, match="missing \\['url'\\]"):
        config.load_sources(bad)


def test_real_holdings_load():
    data = config.load_holdings()
    assert data["notable_move_pct"] == 1.5
    assert [h["ticker"] for h in data["holdings"]] == ["ARKK", "BRK.B", "SPCX"]
