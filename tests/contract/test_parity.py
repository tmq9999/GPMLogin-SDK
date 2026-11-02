from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from gpmlogin_sdk import GPMError, GPMOperationError
from tests.conftest import Api, json_response
from tests.contract.cases import ALL_CASES, DOCUMENTED_ENDPOINTS, MUTATING_APIS, Case


def test_matrix_covers_exactly_the_20_documented_endpoints() -> None:
    templates = {case.template for case in ALL_CASES}
    assert len(DOCUMENTED_ENDPOINTS) == 20
    assert templates == DOCUMENTED_ENDPOINTS
    assert len({case.id for case in ALL_CASES}) == len(ALL_CASES), "case ids must be stable/unique"


def test_soft_and_hard_delete_are_one_endpoint_not_two() -> None:
    delete_templates = [c.template for c in ALL_CASES if c.template[1] == "/profiles/delete/{id}"]
    assert len(delete_templates) == 2 and len(set(delete_templates)) == 1


def _fingerprint(api: Api) -> list[tuple[str, str, bytes]]:
    return [(r.method, str(r.url), r.content) for r in api.requests]


@pytest.mark.parametrize("case", ALL_CASES, ids=lambda case: case.id)
def test_sync_and_async_send_identical_requests_and_return_equal_results(
    api_factory: Callable[..., Api], case: Case
) -> None:
    outcomes = []
    for mode in ("sync", "async"):
        api = api_factory(mode, lambda request: json_response(case.data))
        result = api.call(case.api, *case.args, **case.kwargs)
        outcomes.append((_fingerprint(api), result))
    assert outcomes[0][0] == outcomes[1][0]
    assert outcomes[0][1] == outcomes[1][1]


def _failure_handlers() -> dict[str, Callable[[httpx.Request], httpx.Response]]:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("t", request=request)

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("c", request=request)

    return {
        "success-false": lambda request: json_response(None, success=False, message="no"),
        "http-500": lambda request: httpx.Response(500),
        "redirect": lambda request: httpx.Response(302, headers={"Location": "http://x.example"}),
        "not-json": lambda request: httpx.Response(200, text="<html>"),
        "wrong-envelope": lambda request: httpx.Response(200, json=[1]),
        "timeout": timeout,
        "refused": refused,
    }


@pytest.mark.parametrize("case", ALL_CASES, ids=lambda case: case.id)
@pytest.mark.parametrize("failure", sorted(_failure_handlers()))
def test_sync_and_async_fail_identically_and_never_retry(
    api_factory: Callable[..., Api], case: Case, failure: str
) -> None:
    handler = _failure_handlers()[failure]
    errors: list[GPMOperationError] = []
    for mode in ("sync", "async"):
        api = api_factory(mode, handler)
        with pytest.raises(GPMError) as caught:
            api.call(case.api, *case.args, **case.kwargs)
        assert len(api.requests) == 1, "exactly one attempt, even for reads"
        assert isinstance(caught.value, GPMOperationError)
        errors.append(caught.value)

    sync_error, async_error = errors
    assert type(sync_error) is type(async_error)
    assert str(sync_error) == str(async_error)
    assert sync_error.operation == async_error.operation
    assert sync_error.status_code == async_error.status_code
    assert sync_error.state_uncertain == async_error.state_uncertain

    mutates = case.api in MUTATING_APIS
    if failure in {"http-500", "redirect", "timeout", "refused", "wrong-envelope", "not-json"}:
        assert sync_error.state_uncertain is mutates
    if failure == "success-false":
        assert sync_error.state_uncertain is False


def test_every_mutating_api_name_exists_in_the_matrix() -> None:
    names: set[Any] = {case.api for case in ALL_CASES}
    assert names >= MUTATING_APIS
