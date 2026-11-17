"""Structured tool errors (2.2): what failed, why, and what the model should do next.

Raised by the adapters in tools/definitions.py, caught by the loop and sent back to
the model as a tool_result with is_error: true. The category says who can fix it:
  transient  -> time (retry)
  validation -> the model (send different input)
  permission -> a human (access, or a wrong URL in config)
  business   -> nobody (a valid "no" from the domain: accept it and report it)
"""

import sys
import time
from typing import Callable, Literal, TypeVar

import httpx2

Category = Literal["transient", "validation", "permission", "business"]
T = TypeVar("T")

# Retry policy for transient errors. Worst case for a feed that never answers:
# 3 x 10s timeout + 1s + 2s pauses = ~33s, acceptable for a brief at 08:30.
MAX_ATTEMPTS = 3        # 1 try + 2 retries
BASE_DELAY_S = 1.0      # pause doubles each time: 1s, 2s
MAX_DELAY_S = 5.0       # cap, also for a server asking Retry-After: 3600


class ToolError(Exception):
    """A classified tool failure. Raise it inside a tool; send to_dict() to the model."""

    def __init__(
        self,
        category: Category,
        is_retryable: bool,
        message: str,
        source: str,
        retry_after: float | None = None,
    ):
        super().__init__(message)
        self.category = category
        self.is_retryable = is_retryable
        self.message = message
        self.source = source  # which outlet / ticker failed, so the gap can be named
        self.retry_after = retry_after  # seconds the server asked us to wait (429); for my code only

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "is_retryable": self.is_retryable,
            "source": self.source,
            "message": self.message,
        }


def from_http_error(exc: httpx2.HTTPError, source: str) -> ToolError:
    """Classify an httpx2 exception for one source (see the table in PHASE2_PLAN.md)."""
    if isinstance(exc, httpx2.TimeoutException):
        return ToolError(
            "transient", True,
            f"{source} did not answer in time (timeout).",
            source,
        )
    if isinstance(exc, httpx2.HTTPStatusError):
        status = exc.response.status_code
        # 429 = "slow down": the input is fine, so it is transient, never validation.
        if status == 429 or status >= 500:
            return ToolError(
                "transient", True,
                f"{source} answered with HTTP {status} (temporary server problem).",
                source,
                retry_after=_retry_after(exc.response),
            )
        if status in (401, 403):
            return ToolError(
                "permission", False,
                f"{source} refused access (HTTP {status}). Not temporary; do not retry. "
                "Do not substitute another outlet. Report it as a coverage gap.",
                source,
            )
        # 404 and other 4xx: the model sent a valid source, the URL in config is wrong.
        # Only a human can fix it, so it is not validation.
        return ToolError(
            "permission", False,
            f"{source} feed not found or rejected (HTTP {status}); the config probably "
            "needs updating. Do not retry. Report it as a coverage gap.",
            source,
        )
    # Connection failures (DNS, refused connection, dropped connection): usually temporary.
    return ToolError(
        "transient", True,
        f"Could not connect to {source} ({type(exc).__name__}).",
        source,
    )


def _retry_after(response: httpx2.Response) -> float | None:
    # Retry-After can also be an HTTP date; seconds is the common case, ignore the rest.
    value = response.headers.get("Retry-After", "")
    return float(value) if value.isdigit() else None


def with_retries(call: Callable[[], T], attempts: int = MAX_ATTEMPTS, sleep=time.sleep) -> T:
    """Run call(); retry it only on a retryable ToolError, with exponential backoff.

    Lives with the adapters, not the loop, so it still works when the same tools run
    through MCP (Phase 3) or the Agent SDK (Phase 4). `sleep` is injectable for tests.
    """
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except ToolError as err:
            if not err.is_retryable:
                raise  # 403, 404, validation: the same call fails again, don't wait
            if attempt == attempts:
                # Whoever retries says so: the category stays transient (the cause),
                # but is_retryable becomes False, or the model retries 3 more times.
                raise ToolError(
                    err.category, False,
                    f"{err.message} Failed {attempts} attempts in a row. "
                    "Do not retry. Report it as a coverage gap.",
                    err.source,
                ) from err
            delay = min(err.retry_after or BASE_DELAY_S * 2 ** (attempt - 1), MAX_DELAY_S)
            print(
                f"[retry] {err.source}: attempt {attempt}/{attempts} failed "
                f"({err.message}); waiting {delay:g}s",
                file=sys.stderr,
            )
            sleep(delay)
    raise AssertionError("unreachable")  # the loop always returns or raises
