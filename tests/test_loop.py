"""run_tool tests: every tool_use gets a tool_result, even on failure. No network."""

import json
from types import SimpleNamespace

import loop
from errors import ToolError


def block(name, tool_input=None):
    # Stands in for an SDK ToolUseBlock: run_tool only reads name, input, id.
    return SimpleNamespace(type="tool_use", id="toolu_test", name=name, input=tool_input or {})


def test_success_has_no_is_error(monkeypatch):
    monkeypatch.setitem(loop.HANDLERS, "fake", lambda tool_input: [{"ok": 1}])
    result = loop.run_tool(block("fake"))
    assert "is_error" not in result
    assert json.loads(result["content"]) == [{"ok": 1}]


def test_tool_error_is_sent_as_is(monkeypatch):
    def fail(tool_input):
        raise ToolError("transient", True, "n1 did not answer in time.", "n1")

    monkeypatch.setitem(loop.HANDLERS, "fake", fail)
    result = loop.run_tool(block("fake"))
    assert result["is_error"] is True
    assert result["tool_use_id"] == "toolu_test"
    assert json.loads(result["content"])["category"] == "transient"


def test_unknown_tool_is_validation():
    result = loop.run_tool(block("no_such_tool"))
    error = json.loads(result["content"])
    assert result["is_error"] is True
    assert (error["category"], error["is_retryable"]) == ("validation", False)


def test_bug_becomes_generic_error_without_traceback(monkeypatch):
    def buggy(tool_input):
        raise KeyError("daily")

    monkeypatch.setitem(loop.HANDLERS, "fake", buggy)
    result = loop.run_tool(block("fake"))
    error = json.loads(result["content"])
    assert result["is_error"] is True
    assert error["is_retryable"] is False
    assert "daily" not in error["message"]  # bug details stay in my log
