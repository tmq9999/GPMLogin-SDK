from __future__ import annotations

import json
import traceback
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from gpmlogin_sdk import (
    GPMHTTPError,
    GPMTimeoutError,
    GPMValidationError,
)
from gpmlogin_sdk.resources.profiles import ProfilesResource
from tests.conftest import Api, envelope

PROXY = "socks5://127.0.0.1:5000"
SECRET_PROXY = "socks5://user:s3cr3t-pw@127.0.0.1:5000"


def profile_server(name: str = "Existing") -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=envelope({"id": "p1", "name": name}))
        return httpx.Response(200, json=envelope(None))

    return handler


def sent(api: Api) -> list[tuple[str, str, Any]]:
    return [
        (r.method, r.url.path, json.loads(r.content) if r.content else None) for r in api.requests
    ]


@pytest.mark.parametrize(
    ("method", "args", "expected_proxy"),
    [("set_proxy", (PROXY,), PROXY), ("clear_proxy", (), "")],
)
def test_with_explicit_name_only_one_post_is_sent(
    api_factory: Callable[..., Api],
    mode: str,
    method: str,
    args: tuple[str, ...],
    expected_proxy: str,
) -> None:
    api = api_factory(mode, profile_server())
    result = api.call(f"profiles.{method}", "p1", *args, name="Given")
    assert result.data is None
    assert sent(api) == [
        ("POST", "/api/v1/profiles/update/p1", {"name": "Given", "raw_proxy": expected_proxy})
    ]


@pytest.mark.parametrize(
    ("method", "args", "expected_proxy"),
    [("set_proxy", (PROXY,), PROXY), ("clear_proxy", (), "")],
)
def test_without_name_one_get_then_one_post_keeping_the_existing_name(
    api_factory: Callable[..., Api],
    mode: str,
    method: str,
    args: tuple[str, ...],
    expected_proxy: str,
) -> None:
    api = api_factory(mode, profile_server("Existing"))
    api.call(f"profiles.{method}", "p1", *args)
    assert sent(api) == [
        ("GET", "/api/v1/profiles/p1", None),
        ("POST", "/api/v1/profiles/update/p1", {"name": "Existing", "raw_proxy": expected_proxy}),
    ]


@pytest.mark.parametrize("method", ["set_proxy", "clear_proxy"])
def test_a_failing_get_means_no_post(
    api_factory: Callable[..., Api], mode: str, method: str
) -> None:
    api = api_factory(mode, lambda request: httpx.Response(500))
    args = (PROXY,) if method == "set_proxy" else ()
    with pytest.raises(GPMHTTPError):
        api.call(f"profiles.{method}", "p1", *args)
    assert [r.method for r in api.requests] == ["GET"]


@pytest.mark.parametrize("with_name", [True, False])
def test_a_failing_update_is_not_retried_and_does_not_leak_the_proxy(
    api_factory: Callable[..., Api], mode: str, with_name: bool
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=envelope({"id": "p1", "name": "Existing"}))
        raise httpx.ReadTimeout(f"{SECRET_PROXY}", request=request)

    api = api_factory(mode, handler)
    kwargs = {"name": "Given"} if with_name else {}
    with pytest.raises(GPMTimeoutError) as caught:
        api.call("profiles.set_proxy", "p1", SECRET_PROXY, **kwargs)
    assert caught.value.state_uncertain is True
    assert len(api.requests) == (1 if with_name else 2)
    assert "s3cr3t-pw" not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize("raw_proxy", ["", "   ", None, 5])
def test_set_proxy_rejects_blank_proxies_and_points_to_clear_proxy(
    api_factory: Callable[..., Api], mode: str, raw_proxy: Any
) -> None:
    api = api_factory(mode, profile_server())
    with pytest.raises(GPMValidationError):
        api.call("profiles.set_proxy", "p1", raw_proxy, name="N")
    assert api.requests == []


@pytest.mark.parametrize("method", ["set_proxy", "clear_proxy"])
@pytest.mark.parametrize("name", ["", "  ", 5])
def test_explicit_name_must_be_a_non_blank_string(
    api_factory: Callable[..., Api], mode: str, method: str, name: Any
) -> None:
    api = api_factory(mode, profile_server())
    args = (PROXY,) if method == "set_proxy" else ()
    with pytest.raises(GPMValidationError):
        api.call(f"profiles.{method}", "p1", *args, name=name)
    assert api.requests == []


@pytest.mark.parametrize("method", ["set_proxy", "clear_proxy"])
@pytest.mark.parametrize("profile_id", ["", ".", None])
def test_bad_profile_id_fails_before_any_request(
    api_factory: Callable[..., Api], mode: str, method: str, profile_id: Any
) -> None:
    api = api_factory(mode, profile_server())
    args = (PROXY,) if method == "set_proxy" else ()
    with pytest.raises(GPMValidationError):
        api.call(f"profiles.{method}", profile_id, *args)
    assert api.requests == []


def test_low_level_update_never_adds_an_implicit_get(
    api_factory: Callable[..., Api], mode: str
) -> None:
    api = api_factory(mode, profile_server())
    api.call("profiles.update", "p1", {"raw_proxy": ""})
    assert [r.method for r in api.requests] == ["POST"]


def test_docstring_warns_about_the_rename_race_and_no_transaction() -> None:
    doc = (ProfilesResource.set_proxy.__doc__ or "").lower()
    assert "race" in doc and "transaction" in doc
    assert "race" in (ProfilesResource.clear_proxy.__doc__ or "").lower()
