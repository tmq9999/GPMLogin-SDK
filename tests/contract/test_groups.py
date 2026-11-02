from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from gpmlogin_sdk import GPMValidationError
from tests.conftest import Api, json_response
from tests.contract.cases import GROUP_CASES, Case, run_case


@pytest.mark.parametrize("case", GROUP_CASES, ids=lambda case: case.id)
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
        api.call("groups.delete", "g1", confirm=confirm)
    with pytest.raises(GPMValidationError):
        api.call("groups.delete", "g1")
    assert api.requests == []


@pytest.mark.parametrize("name", ["", "  ", None, 5, b"x"])
def test_names_must_be_non_blank_strings(
    api_factory: Callable[..., Api], mode: str, name: Any
) -> None:
    api = api_factory(mode, lambda request: json_response(None))
    with pytest.raises(GPMValidationError):
        api.call("groups.create", name)
    with pytest.raises(GPMValidationError):
        api.call("groups.update", "g1", name=name)
    assert api.requests == []


@pytest.mark.parametrize("sort_order", [True, False, "1", 1.5, [1]])
def test_sort_order_must_be_an_int_when_given(
    api_factory: Callable[..., Api], mode: str, sort_order: Any
) -> None:
    api = api_factory(mode, lambda request: json_response(None))
    with pytest.raises(GPMValidationError):
        api.call("groups.create", "G", sort_order=sort_order)
    with pytest.raises(GPMValidationError):
        api.call("groups.update", "g1", name="G", sort_order=sort_order)
    assert api.requests == []


@pytest.mark.parametrize("group_id", ["", ".", "..", None, 5])
def test_bad_ids_fail_before_http(
    api_factory: Callable[..., Api], mode: str, group_id: Any
) -> None:
    api = api_factory(mode, lambda request: json_response(None))
    with pytest.raises(GPMValidationError):
        api.call("groups.get", group_id)
    with pytest.raises(GPMValidationError):
        api.call("groups.update", group_id, name="N")
    with pytest.raises(GPMValidationError):
        api.call("groups.delete", group_id, confirm=True)
    assert api.requests == []


def test_list_uses_the_shared_pagination_validation(
    api_factory: Callable[..., Api], mode: str
) -> None:
    api = api_factory(mode, lambda request: json_response(None))
    for kwargs in ({"page": 0}, {"page_size": True}, {"sort": 9}):
        with pytest.raises(GPMValidationError):
            api.call("groups.list", **kwargs)
    assert api.requests == []
