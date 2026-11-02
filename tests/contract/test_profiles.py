from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from gpmlogin_sdk import (
    GPMAPIError,
    GPMProtocolError,
    GPMTimeoutError,
    GPMValidationError,
)
from tests.conftest import Api, json_response
from tests.contract.cases import PROFILE_CASES, Case, run_case


@pytest.mark.parametrize("case", PROFILE_CASES, ids=lambda case: case.id)
def test_wire_contract_and_typed_result(
    api_factory: Callable[..., Api], mode: str, case: Case
) -> None:
    run_case(api_factory, mode, case)


@pytest.mark.parametrize(
    "confirm", [False, None, 1, "yes", "true"], ids=["false", "none", "int", "yes", "true-str"]
)
def test_hard_delete_requires_literal_true_and_makes_no_http_call(
    api_factory: Callable[..., Api], mode: str, confirm: Any
) -> None:
    api = api_factory(mode, lambda request: json_response(None))
    with pytest.raises(GPMValidationError):
        api.call("profiles.hard_delete", "p1", confirm=confirm)
    assert api.requests == []


def test_hard_delete_default_is_not_confirmed(api_factory: Callable[..., Api], mode: str) -> None:
    api = api_factory(mode, lambda request: json_response(None))
    with pytest.raises(GPMValidationError):
        api.call("profiles.hard_delete", "p1")
    assert api.requests == []


@pytest.mark.parametrize("profile_id", ["", ".", "..", None, 5])
@pytest.mark.parametrize(
    "method",
    ["get", "update", "soft_delete", "start", "stop"],
)
def test_bad_ids_fail_before_any_http_call(
    api_factory: Callable[..., Api], mode: str, method: str, profile_id: Any
) -> None:
    api = api_factory(mode, lambda request: json_response(None))
    args: tuple[Any, ...] = (profile_id, {}) if method == "update" else (profile_id,)
    with pytest.raises(GPMValidationError):
        api.call(f"profiles.{method}", *args)
    with pytest.raises(GPMValidationError):
        api.call("profiles.hard_delete", profile_id, confirm=True)
    assert api.requests == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"page": 0},
        {"page": -1},
        {"page": True},
        {"page": "1"},
        {"page_size": 0},
        {"page_size": False},
        {"page_size": 1.5},
        {"search": 5},
        {"sort": 4},
        {"sort": -1},
        {"sort": True},
        {"sort": "0"},
    ],
)
def test_list_rejects_bad_arguments_without_http(
    api_factory: Callable[..., Api], mode: str, kwargs: dict[str, Any]
) -> None:
    api = api_factory(mode, lambda request: json_response(PROFILE_CASES[0].data))
    with pytest.raises(GPMValidationError):
        api.call("profiles.list", **kwargs)
    assert api.requests == []


def test_invalid_bodies_and_options_fail_without_http(
    api_factory: Callable[..., Api], mode: str
) -> None:
    api = api_factory(mode, lambda request: json_response(None))
    with pytest.raises(GPMValidationError):
        api.call("profiles.create", {})
    with pytest.raises(GPMValidationError):
        api.call("profiles.create", {"name": "A", "webrtc_mode": 2})
    with pytest.raises(GPMValidationError):
        api.call("profiles.update", "p1", {"name": None})
    with pytest.raises(GPMValidationError):
        api.call("profiles.start", "p1", {"window_size": "0,0"})
    assert api.requests == []


def test_malformed_launch_after_success_keeps_the_confirmation_marker(
    api_factory: Callable[..., Api], mode: str
) -> None:
    api = api_factory(mode, lambda request: json_response({"profile_id": "p1"}))
    with pytest.raises(GPMProtocolError) as caught:
        api.call("profiles.start", "p1")
    assert caught.value.operation == "profiles.start"
    assert caught.value.success_confirmed is True
    assert len(api.requests) == 1


def test_success_false_is_api_error(api_factory: Callable[..., Api], mode: str) -> None:
    api = api_factory(mode, lambda request: json_response(None, success=False, message="nope"))
    with pytest.raises(GPMAPIError) as caught:
        api.call("profiles.get", "p1")
    assert caught.value.operation == "profiles.get"


MUTATION_CALLS: list[tuple[str, tuple[Any, ...], dict[str, Any], bool]] = [
    ("profiles.list", (), {}, False),
    ("profiles.get", ("p1",), {}, False),
    ("browsers.versions", (), {}, False),
    ("profiles.create", ({"name": "A"},), {}, True),
    ("profiles.update", ("p1", {"name": "A"}), {}, True),
    ("profiles.soft_delete", ("p1",), {}, True),
    ("profiles.hard_delete", ("p1",), {"confirm": True}, True),
    ("profiles.start", ("p1",), {}, True),
    ("profiles.stop", ("p1",), {}, True),
]


@pytest.mark.parametrize(
    ("name", "args", "kwargs", "mutates"), MUTATION_CALLS, ids=[c[0] for c in MUTATION_CALLS]
)
def test_get_is_not_assumed_read_only_and_timeouts_are_never_retried(
    api_factory: Callable[..., Api],
    mode: str,
    name: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    mutates: bool,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    api = api_factory(mode, handler)
    with pytest.raises(GPMTimeoutError) as caught:
        api.call(name, *args, **kwargs)
    assert caught.value.state_uncertain is mutates
    assert len(api.requests) == 1


def test_clients_expose_no_generic_raw_request_shortcut(api_factory: Callable[..., Api]) -> None:
    api = api_factory("sync", lambda request: json_response(None))
    for forbidden in ("request", "raw_request", "get", "post", "send"):
        assert not hasattr(api.client, forbidden)
    for forbidden in ("request", "raw_request", "post", "send"):
        assert not hasattr(api.client.profiles, forbidden)
        assert not hasattr(api.client.browsers, forbidden)
