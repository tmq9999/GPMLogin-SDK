from __future__ import annotations

from collections.abc import Callable

import pytest

from gpmlogin_sdk import GPMProtocolError
from tests.conftest import Api, json_response
from tests.contract.cases import BROWSER_CASES, Case, run_case


@pytest.mark.parametrize("case", BROWSER_CASES, ids=lambda case: case.id)
def test_versions_wire_contract(api_factory: Callable[..., Api], mode: str, case: Case) -> None:
    run_case(api_factory, mode, case)


def test_versions_key_stays_chromium_not_chrome(api_factory: Callable[..., Api], mode: str) -> None:
    api = api_factory(mode, lambda request: json_response({"chrome": ["1"], "firefox": []}))
    with pytest.raises(GPMProtocolError):
        api.call("browsers.versions")
