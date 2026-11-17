"""Error classification tests. No network: exceptions are built by hand."""

import httpx2
import pytest

from errors import ToolError, from_http_error

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
