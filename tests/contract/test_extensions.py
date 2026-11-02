from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from gpmlogin_sdk import GPMProtocolError, GPMValidationError
from tests.conftest import Api, json_response
from tests.contract.cases import EXTENSION_CASES, EXTENSION_DATA, Case, run_case


@pytest.mark.parametrize("case", EXTENSION_CASES, ids=lambda case: case.id)
def test_wire_contract_and_typed_result(
    api_factory: Callable[..., Api], mode: str, case: Case
) -> None:
    run_case(api_factory, mode, case)


def test_list_is_a_plain_array_not_a_page(api_factory: Callable[..., Api], mode: str) -> None:
    api = api_factory(mode, lambda request: json_response(EXTENSION_DATA))
    listed = api.call("extensions.list")
    assert [item.id for item in listed] == ["e1"]
    paged = {"current_page": 1, "per_page": 30, "total": 1, "last_page": 1, "data": EXTENSION_DATA}
    api = api_factory(mode, lambda request: json_response(paged))
    with pytest.raises(GPMProtocolError):
        api.call("extensions.list")


def test_active_false_is_sent_and_never_collapsed_into_global_scope(
    api_factory: Callable[..., Api], mode: str
) -> None:
    api = api_factory(mode, lambda request: json_response(None))
    api.call("extensions.set_state", "e1", active=False)
    params = dict(api.requests[0].url.params)
    assert params == {"active": "false"}


def test_tuple_scope_is_accepted(api_factory: Callable[..., Api], mode: str) -> None:
    api = api_factory(mode, lambda request: json_response(None))
    api.call("extensions.set_state", "e1", active=True, group_ids=("g1",))
    assert dict(api.requests[0].url.params) == {"active": "true", "applied_group_ids": "g1"}


@pytest.mark.parametrize(
    "group_ids",
    ["g1", b"g1", [], (), [""], ["g1", ""], ["a,b"], [5], [None], {"g1"}, 5],
    ids=["str", "bytes", "empty-list", "empty-tuple", "blank", "one-blank", "comma", "int",
         "none", "set", "scalar"],
)  # fmt: skip
def test_invalid_scope_is_rejected_before_http(
    api_factory: Callable[..., Api], mode: str, group_ids: Any
) -> None:
    api = api_factory(mode, lambda request: json_response(None))
    with pytest.raises(GPMValidationError):
        api.call("extensions.set_state", "e1", active=True, group_ids=group_ids)
    assert api.requests == []


@pytest.mark.parametrize("active", [1, 0, "true", None])
def test_active_must_be_a_real_boolean(
    api_factory: Callable[..., Api], mode: str, active: Any
) -> None:
    api = api_factory(mode, lambda request: json_response(None))
    with pytest.raises(GPMValidationError):
        api.call("extensions.set_state", "e1", active=active)
    assert api.requests == []


@pytest.mark.parametrize("extension_id", ["", ".", "..", None, 5])
def test_bad_extension_id_fails_before_http(
    api_factory: Callable[..., Api], mode: str, extension_id: Any
) -> None:
    api = api_factory(mode, lambda request: json_response(None))
    with pytest.raises(GPMValidationError):
        api.call("extensions.set_state", extension_id, active=True)
    assert api.requests == []
