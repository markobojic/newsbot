"""Fake outages on demand, to see what Claude does with tool errors. Plain Python.

Usage:  CHAOS="n1:timeout,pink:403,open-meteo:503" .venv/bin/python loop.py
Modes:  timeout | connect | any HTTP status code (403, 404, 429, 500, ...)

Raises the same httpx2 exceptions a real outage would, so the whole real chain runs:
classification -> retries -> run_tool -> is_error -> Claude. Off when CHAOS is unset.
"""

import os
import sys

import httpx2


def _parse(spec: str) -> dict[str, str]:
    """'n1:timeout,pink:403' -> {'n1': 'timeout', 'pink': '403'}; bad spec raises."""
    faults = {}
    for item in filter(None, (part.strip() for part in spec.split(","))):
        source, sep, mode = item.partition(":")
        if not sep or not (mode in ("timeout", "connect") or (mode.isdigit() and len(mode) == 3)):
            # A typo here is my mistake, not an outage: crash instead of running
            # a "chaos test" that silently fakes nothing.
            raise ValueError(f"Bad CHAOS entry {item!r}; expected source:timeout|connect|<status>")
        faults[source] = mode
    return faults


def maybe_fail(source: str) -> None:
    """Raise the faked failure configured for `source`, if any. Read on every call."""
    mode = _parse(os.environ.get("CHAOS", "")).get(source)
    if mode is None:
        return
    print(f"[chaos] faking {mode} for {source}", file=sys.stderr)
    request = httpx2.Request("GET", f"https://chaos.invalid/{source}")
    if mode == "timeout":
        raise httpx2.ReadTimeout("chaos: faked timeout", request=request)
    if mode == "connect":
        raise httpx2.ConnectError("chaos: faked connection failure", request=request)
    response = httpx2.Response(int(mode), request=request)
    raise httpx2.HTTPStatusError(f"chaos: faked HTTP {mode}", request=request, response=response)
