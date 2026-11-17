"""Error classification tests. No network: exceptions are built by hand."""

import httpx2
import pytest

from errors import ToolError, from_http_error, with_retries

REQUEST = httpx2.Request("GET", "https://x.test/feed")


def status_error(status: int) -> httpx2.HTTPStatusError:
    response = httpx2.Response(status, request=REQUEST)
    return httpx2.HTTPStatusError("boom", request=REQUEST, response=response)


@pytest.mark.parametrize(
    "exc, category, retryable",
    [
        (httpx2.ReadTimeout("slow", request=REQUEST), "transient", True),
        (httpx2.ConnectError("dns", request=REQUEST), "transient", True),
        (status_error(500), "transient", True),
        (status_error(503), "transient", True),
        (status_error(429), "transient", True),
        (status_error(403), "permission", False),
        (status_error(401), "permission", False),
        (status_error(404), "permission", False),
    ],
)
def test_classification(exc, category, retryable):
    err = from_http_error(exc, "n1")
    assert (err.category, err.is_retryable, err.source) == (category, retryable, "n1")


def test_to_dict_is_json_ready():
    err = from_http_error(status_error(403), "pink")
    assert err.to_dict() == {
        "category": "permission",
        "is_retryable": False,
        "source": "pink",
        "message": err.message,
    }
    assert "pink" in err.message


def test_tool_error_can_be_raised():
    with pytest.raises(ToolError) as info:
        raise from_http_error(status_error(500), "n1")
    assert info.value.is_retryable


# --- with_retries -------------------------------------------------------------

def flaky(errors, result="ok"):
    """A call that raises the given errors in order, then returns result."""
    calls = []

    def call():
        calls.append(1)
        if len(calls) <= len(errors):
            raise errors[len(calls) - 1]
        return result

    return call, calls


def test_transient_is_retried_then_succeeds():
    call, calls = flaky([from_http_error(status_error(503), "n1")])
    sleeps = []
    assert with_retries(call, sleep=sleeps.append) == "ok"
    assert len(calls) == 2
    assert sleeps == [1.0]


def test_gives_up_after_max_attempts_and_says_do_not_retry():
    timeout = from_http_error(httpx2.ReadTimeout("slow", request=REQUEST), "n1")
    call, calls = flaky([timeout] * 5)
    sleeps = []
    with pytest.raises(ToolError) as info:
        with_retries(call, sleep=sleeps.append)
    assert len(calls) == 3
    assert sleeps == [1.0, 2.0]  # exponential backoff
    err = info.value
    assert (err.category, err.is_retryable) == ("transient", False)  # cause stays, retry used up
    assert "3 attempts" in err.message and "Do not retry" in err.message


def test_permission_is_not_retried():
    call, calls = flaky([from_http_error(status_error(403), "pink")])
    sleeps = []
    with pytest.raises(ToolError):
        with_retries(call, sleep=sleeps.append)
    assert len(calls) == 1
    assert sleeps == []


def test_retry_after_is_respected_but_capped():
    def rate_limited(seconds):
        response = httpx2.Response(429, request=REQUEST, headers={"Retry-After": seconds})
        return from_http_error(
            httpx2.HTTPStatusError("slow down", request=REQUEST, response=response), "yahoo"
        )

    call, _ = flaky([rate_limited("2"), rate_limited("3600")])
    sleeps = []
    with_retries(call, sleep=sleeps.append)
    assert sleeps == [2.0, 5.0]  # server's 2s, then 3600s capped at 5s
