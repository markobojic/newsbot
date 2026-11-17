"""Structured tool errors (2.2): what failed, why, and what the model should do next.

Raised by the adapters in tools/definitions.py, caught by the loop and sent back to
the model as a tool_result with is_error: true. The category says who can fix it:
  transient  -> time (retry)
  validation -> the model (send different input)
  permission -> a human (access, or a wrong URL in config)
  business   -> nobody (a valid "no" from the domain: accept it and report it)
"""

from typing import Literal

import httpx2

Category = Literal["transient", "validation", "permission", "business"]


class ToolError(Exception):
    """A classified tool failure. Raise it inside a tool; send to_dict() to the model."""

    def __init__(self, category: Category, is_retryable: bool, message: str, source: str):
        super().__init__(message)
        self.category = category
        self.is_retryable = is_retryable
        self.message = message
        self.source = source  # which outlet / ticker failed, so the gap can be named

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
            f"{source} did not answer in time. Temporary; may work if retried.",
            source,
        )
    if isinstance(exc, httpx2.HTTPStatusError):
        status = exc.response.status_code
        # 429 = "slow down": the input is fine, so it is transient, never validation.
        if status == 429 or status >= 500:
            return ToolError(
                "transient", True,
                f"{source} is temporarily unavailable (HTTP {status}). May work if retried.",
                source,
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
        f"Could not connect to {source} ({type(exc).__name__}). May work if retried.",
        source,
    )
