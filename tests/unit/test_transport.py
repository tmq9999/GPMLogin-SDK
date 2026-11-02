from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from gpmlogin_sdk._async_transport import AsyncTransport
from gpmlogin_sdk._operations import Operation, parse_none
from gpmlogin_sdk.config import resolve_config
from gpmlogin_sdk.errors import (
    GPMAPIError,
    GPMHTTPError,
    GPMProtocolError,
    GPMTimeoutError,
    GPMTransportError,
)
from gpmlogin_sdk.models import parse_profile_created, parse_profile_updated
from tests.conftest import envelope, json_response

CREATE = Operation("profiles.create", "POST", "/profiles/create", True, parse_profile_created)
GET_SOMETHING = Operation("profiles.get", "GET", "/profiles/p1", False, parse_profile_created)
STOP = Operation("profiles.stop", "GET", "/profiles/stop/p1", True, parse_none)
UPDATE = Operation("profiles.update", "POST", "/profiles/update/p1", True, parse_profile_updated)

CREATED = {"id": "p1", "name": "A"}


def test_success_is_unwrapped_and_request_is_exact(make_harness: Any, mode: str) -> None:
    harness = make_harness(mode, lambda request: json_response(CREATED))
    result = harness.request(CREATE, body={"name": "A", "note": None})
    assert result.id == "p1"
    assert len(harness.requests) == 1
    request = harness.requests[0]
    assert request.method == "POST"
    assert request.url.path == "/api/v1/profiles/create"
    assert request.url.host == "127.0.0.1" and request.url.port == 9495
    assert request.headers["content-type"] == "application/json"
    assert request.read() == b'{"name":"A","note":null}'


def test_get_without_body_has_no_content_type_and_false_is_lowercase(
    make_harness: Any, mode: str
) -> None:
    harness = make_harness(mode, lambda request: json_response(CREATED))
    harness.request(GET_SOMETHING, query={"skip_proxy_check": False, "page": 0, "x": None})
    request = harness.requests[0]
    assert "content-type" not in request.headers
    assert dict(request.url.params) == {"skip_proxy_check": "false", "page": "0"}
    assert request.url.path.count("/api/v1") == 1


def test_injected_client_base_url_cannot_redirect_the_request(make_harness: Any, mode: str) -> None:
    harness = make_harness(
        mode, lambda request: json_response(CREATED), base_url="http://other.example:1/x/"
    )
    harness.request(GET_SOMETHING)
    assert str(harness.requests[0].url) == "http://127.0.0.1:9495/api/v1/profiles/p1"


def test_encoded_id_keeps_raw_path(make_harness: Any, mode: str) -> None:
    operation = Operation(
        "profiles.get", "GET", "/profiles/a%2Fb%20%3F", False, parse_profile_created
    )
    harness = make_harness(mode, lambda request: json_response(CREATED))
    harness.request(operation)
    assert harness.requests[0].url.raw_path == b"/api/v1/profiles/a%2Fb%20%3F"


def test_timeout_default_and_override(make_harness: Any, mode: str) -> None:
    config = resolve_config(timeout=12.0)
    harness = make_harness(mode, lambda request: json_response(CREATED), config=config)
    harness.request(GET_SOMETHING)
    harness.request(GET_SOMETHING, timeout=5.0)
    assert harness.requests[0].extensions["timeout"]["read"] == 12.0
    assert harness.requests[1].extensions["timeout"]["read"] == 5.0
    assert harness.requests[1].extensions["timeout"]["connect"] == 5.0


def test_success_false_is_api_error_with_no_vendor_text(make_harness: Any, mode: str) -> None:
    harness = make_harness(
        mode, lambda request: json_response(None, success=False, message="SECRET vendor text")
    )
    with pytest.raises(GPMAPIError) as caught:
        harness.request(CREATE, body={"name": "A"})
    assert caught.value.operation == "profiles.create"
    assert caught.value.status_code == 200
    assert caught.value.state_uncertain is False
    assert "SECRET" not in str(caught.value)
    assert len(harness.requests) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"success": "true", "data": CREATED},
        {"success": 1, "data": CREATED},
        {"success": None, "data": CREATED},
        {"success": "false", "data": None},
        {"data": CREATED},
        {},
        [CREATED],
        "ok",
        None,
    ],
)
def test_bad_envelope_is_protocol_error_without_success_confirmation(
    make_harness: Any, mode: str, payload: object
) -> None:
    harness = make_harness(mode, lambda request: httpx.Response(200, json=payload))
    with pytest.raises(GPMProtocolError) as caught:
        harness.request(CREATE, body={"name": "A"})
    assert caught.value.success_confirmed is False
    assert caught.value.operation == "profiles.create"
    assert caught.value.state_uncertain is True, "mutation with unconfirmed outcome"
    assert len(harness.requests) == 1


@pytest.mark.parametrize("content", [b"not json", b"", b"\xff\xfe", b"<html>SECRET</html>"])
def test_non_json_body_is_protocol_error(make_harness: Any, mode: str, content: bytes) -> None:
    harness = make_harness(mode, lambda request: httpx.Response(200, content=content))
    with pytest.raises(GPMProtocolError) as caught:
        harness.request(GET_SOMETHING)
    assert caught.value.success_confirmed is False
    assert caught.value.state_uncertain is False, "reads are never uncertain"
    assert "SECRET" not in str(caught.value)


def test_success_true_but_bad_data_confirms_success_and_names_operation(
    make_harness: Any, mode: str
) -> None:
    start = Operation("profiles.start", "GET", "/profiles/start/p1", True, parse_profile_created)
    harness = make_harness(mode, lambda request: json_response({"id": 5}))
    with pytest.raises(GPMProtocolError) as caught:
        harness.request(start)
    assert caught.value.operation == "profiles.start"
    assert caught.value.success_confirmed is True
    assert caught.value.state_uncertain is False


def test_success_true_without_data_key_confirms_success(make_harness: Any, mode: str) -> None:
    harness = make_harness(mode, lambda request: httpx.Response(200, json={"success": True}))
    with pytest.raises(GPMProtocolError) as caught:
        harness.request(CREATE, body={"name": "A"})
    assert caught.value.success_confirmed is True


def test_null_data_only_valid_for_none_like_parsers(make_harness: Any, mode: str) -> None:
    harness = make_harness(mode, lambda request: json_response(None))
    assert harness.request(STOP) is None
    assert harness.request(UPDATE, body={"name": "A"}).data is None
    with pytest.raises(GPMProtocolError):
        harness.request(CREATE, body={"name": "A"})


def test_non_null_data_for_none_parser_is_protocol_error(make_harness: Any, mode: str) -> None:
    harness = make_harness(mode, lambda request: json_response({"unexpected": 1}))
    with pytest.raises(GPMProtocolError) as caught:
        harness.request(STOP)
    assert caught.value.success_confirmed is True


@pytest.mark.parametrize("status", [500, 404, 302, 301, 199, 300])
def test_non_2xx_is_http_error_and_redirects_are_not_followed(
    make_harness: Any, mode: str, status: int
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status, headers={"Location": "http://remote.example/steal"}, text="SECRET body"
        )

    harness = make_harness(mode, handler, follow_redirects=True)
    with pytest.raises(GPMHTTPError) as caught:
        harness.request(CREATE, body={"name": "A"})
    assert caught.value.status_code == status
    assert len(harness.requests) == 1
    assert "remote.example" not in str(caught.value)
    assert "SECRET" not in str(caught.value)
    assert caught.value.state_uncertain is True


def test_http_error_on_read_is_not_uncertain(make_harness: Any, mode: str) -> None:
    harness = make_harness(mode, lambda request: httpx.Response(500))
    with pytest.raises(GPMHTTPError) as caught:
        harness.request(GET_SOMETHING)
    assert caught.value.state_uncertain is False


@pytest.mark.parametrize(
    ("exc_type", "expected", "timeout"),
    [
        (httpx.ConnectError, GPMTransportError, False),
        (httpx.ReadError, GPMTransportError, False),
        (httpx.ReadTimeout, GPMTimeoutError, True),
        (httpx.ConnectTimeout, GPMTimeoutError, True),
    ],
)
def test_transport_failures_are_typed_and_never_retried(
    make_harness: Any,
    mode: str,
    exc_type: type[httpx.TransportError],
    expected: type,
    timeout: bool,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc_type("SECRET", request=request)

    harness = make_harness(mode, handler)
    for operation, uncertain in ((CREATE, True), (STOP, True), (GET_SOMETHING, False)):
        harness.requests.clear()
        with pytest.raises(expected) as caught:
            harness.request(operation, body={"name": "A"} if operation is CREATE else None)
        assert len(harness.requests) == 1, "no automatic retry"
        assert caught.value.operation == operation.name
        assert caught.value.state_uncertain is uncertain
        assert isinstance(caught.value, GPMTimeoutError) is timeout
        assert issubclass(GPMTimeoutError, GPMTransportError)


def test_operation_rejects_urls_and_queries_in_path() -> None:
    for bad in ("http://evil.example/x", "profiles", "/profiles?x=1", "//evil", "/p#frag", ""):
        with pytest.raises(ValueError):
            Operation("x", "GET", bad, False, parse_none)


def test_parse_none_only_accepts_none() -> None:
    assert parse_none(None) is None
    for bad in ({}, [], 0, "", False):
        with pytest.raises(GPMProtocolError):
            parse_none(bad)


@pytest.mark.asyncio
async def test_async_cancellation_is_not_swallowed_or_wrapped() -> None:
    started = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        started.set()
        await asyncio.Event().wait()
        return httpx.Response(200, json=envelope(CREATED))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        transport = AsyncTransport(resolve_config(), http)
        task = asyncio.ensure_future(transport.request(CREATE, body={"name": "A"}))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
