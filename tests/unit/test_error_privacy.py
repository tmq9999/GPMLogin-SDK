from __future__ import annotations

import logging
import traceback
from typing import Any

import httpx
import pytest

from gpmlogin_sdk._operations import Operation, parse_none
from gpmlogin_sdk.errors import GPMError, GPMOperationError
from gpmlogin_sdk.models import parse_profile_created
from tests.conftest import json_response

SECRET = "SECRET"
CREATE = Operation("profiles.create", "POST", "/profiles/create", True, parse_profile_created)
READ = Operation("profiles.get", "GET", "/profiles/p1", False, parse_profile_created)
STOP = Operation("profiles.stop", "GET", "/profiles/stop/p1", True, parse_none)


def _raise(exc_type: type[httpx.TransportError]) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc_type(f"{SECRET} {request.url}", request=request)

    return handler


SCENARIOS: dict[str, Any] = {
    "vendor-message": lambda request: json_response(None, success=False, message=SECRET),
    "vendor-message-with-unknown-data": lambda request: json_response(
        {"leak": SECRET}, success=False, message=SECRET
    ),
    "http-500-body": lambda request: httpx.Response(500, text=SECRET),
    "redirect-location": lambda request: httpx.Response(
        302, headers={"Location": f"http://{SECRET}.example/"}
    ),
    "bad-data-shape": lambda request: json_response({"id": 5, "name": SECRET, "x": SECRET}),
    "non-json": lambda request: httpx.Response(200, text=SECRET),
    "connect-error": _raise(httpx.ConnectError),
    "read-timeout": _raise(httpx.ReadTimeout),
    "connect-timeout": _raise(httpx.ConnectTimeout),
}


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_secret_never_reaches_public_error_surfaces(
    make_harness: Any, mode: str, scenario: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="gpmlogin_sdk")
    harness = make_harness(mode, SCENARIOS[scenario])
    body = {"name": SECRET, "raw_proxy": f"socks5://user:{SECRET}@127.0.0.1:1"}
    query = {"search": SECRET, "raw_proxy": f"http://u:{SECRET}@h:1"}

    with pytest.raises(GPMError) as caught:
        harness.request(CREATE, query=query, body=body)

    error = caught.value
    rendered = "".join(traceback.format_exception(error))
    assert SECRET not in str(error)
    assert SECRET not in repr(error)
    assert SECRET not in rendered
    assert SECRET not in caplog.text
    assert not [r for r in caplog.records if r.name.startswith("gpmlogin_sdk")], "SDK stays silent"
    assert error.__cause__ is None
    assert error.__context__ is None, "raw HTTPX exceptions must not be chained"
    assert "httpx" not in rendered.replace("gpmlogin_sdk", "")
    if isinstance(error, GPMOperationError):
        for value in vars(error).values():
            assert value is None or isinstance(value, str | int | bool), "no raw objects stored"


def test_unknown_response_keys_stay_out_of_repr(make_harness: Any, mode: str) -> None:
    harness = make_harness(
        mode, lambda request: json_response({"id": "p1", "name": "A", "meta": {"k": SECRET}})
    )
    created = harness.request(CREATE, body={"name": "A"})
    assert SECRET not in repr(created)
    assert created.extra["meta"] == {"k": SECRET}
