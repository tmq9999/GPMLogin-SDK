from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from gpmlogin_sdk import GPMValidationError
from tests.conftest import Api, json_response
from tests.contract.cases import PROXY_CASES, Case, run_case


@pytest.mark.parametrize("case", PROXY_CASES, ids=lambda case: case.id)
def test_wire_contract_and_typed_result(
    api_factory: Callable[..., Api], mode: str, case: Case
) -> None:
    run_case(api_factory, mode, case)


@pytest.mark.parametrize("confirm", [False, None, 1, "yes"], ids=["false", "none", "int", "str"])
def test_delete_requires_literal_true_and_sends_nothing(
    api_factory: Callable[..., Api], mode: str, confirm: Any
) -> None:
    api = api_factory(mode, lambda request: json_response(None))
    with pytest.raises(GPMValidationError):
        api.call("proxies.delete", "x1", confirm=confirm)
    with pytest.raises(GPMValidationError):
        api.call("proxies.delete", "x1")
    assert api.requests == []


@pytest.mark.parametrize("raw_proxy", ["", "   ", None, 5, b"ip:port"])
def test_raw_proxy_must_be_a_non_blank_string(
    api_factory: Callable[..., Api], mode: str, raw_proxy: Any
) -> None:
    api = api_factory(mode, lambda request: json_response(None))
    with pytest.raises(GPMValidationError):
        api.call("proxies.create", raw_proxy)
    with pytest.raises(GPMValidationError):
        api.call("proxies.update", "x1", raw_proxy)
    assert api.requests == []


def test_proxy_format_is_not_policed_beyond_non_empty(
    api_factory: Callable[..., Api], mode: str
) -> None:
    api = api_factory(mode, lambda request: json_response({"id": "x", "raw_proxy": "whatever"}))
    api.call("proxies.create", "whatever-the-vendor-accepts")
    assert len(api.requests) == 1


@pytest.mark.parametrize("proxy_id", ["", ".", "..", None, 5])
def test_bad_ids_fail_before_http(
    api_factory: Callable[..., Api], mode: str, proxy_id: Any
) -> None:
    api = api_factory(mode, lambda request: json_response(None))
    with pytest.raises(GPMValidationError):
        api.call("proxies.get", proxy_id)
    with pytest.raises(GPMValidationError):
        api.call("proxies.update", proxy_id, "ip:port")
    with pytest.raises(GPMValidationError):
        api.call("proxies.delete", proxy_id, confirm=True)
    assert api.requests == []


def test_profile_bodies_cannot_reference_a_shared_proxy_id(
    api_factory: Callable[..., Api], mode: str
) -> None:
    api = api_factory(mode, lambda request: json_response(None))
    with pytest.raises(GPMValidationError):
        api.call("profiles.create", {"name": "A", "proxy_id": "x1"})
    with pytest.raises(GPMValidationError):
        api.call("profiles.update", "p1", {"proxy_id": "x1"})
    assert api.requests == []
