"""Plumbing for search_news: normalization and parallel fetching. No network."""

import pytest

from errors import ToolError
from tools.parallel import fetch_all
from tools.text import normalize


@pytest.mark.parametrize("text", ["Вукићевић", "VUKIĆEVIĆ", "Vukićević", "vukicevic"])
def test_all_scripts_and_spellings_match(text):
    assert normalize(text) == "vukicevic"


def test_digraphs():
    assert normalize("Љубав њега џеп") == "ljubav njega dzep"
    assert normalize("Đoković") == "djokovic"


def test_fetch_all_separates_results_and_failures():
    def fetch(source):
        if source == "newsmax":
            raise ToolError("transient", False, "timeout", source)
        return [source]

    results, failures = fetch_all(["n1", "newsmax", "danas"], fetch)
    assert results == {"n1": ["n1"], "danas": ["danas"]}
    assert list(failures) == ["newsmax"]


def test_fetch_all_raises_bugs():
    def buggy(source):
        raise KeyError("oops")

    with pytest.raises(KeyError):
        fetch_all(["n1"], buggy)
