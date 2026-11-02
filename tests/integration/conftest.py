"""Opt-in live tests against a real GPM Login. Collected, then skipped unless enabled.

GPM_RUN_LIVE=1                  read-only checks
GPM_RUN_LIVE_MUTATIONS=1        also create/update/soft-delete a profile this test creates
GPM_RUN_LIVE_START=1            also start/stop that profile (needs a working Chrome profile)
GPM_RUN_LIVE_SHARED_MUTATIONS=1 also create/update/delete a group and a proxy it creates
GPM_API_PORT must be set explicitly; the live tests never guess a port.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from gpmlogin_sdk import GPMClient

HERE = Path(__file__).resolve().parent
GATES = {
    "live": "GPM_RUN_LIVE",
    "live_mutations": "GPM_RUN_LIVE_MUTATIONS",
    "live_start": "GPM_RUN_LIVE_START",
    "live_shared_mutations": "GPM_RUN_LIVE_SHARED_MUTATIONS",
}


def enabled(name: str) -> bool:
    return os.environ.get(name) == "1"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if HERE not in Path(str(item.path)).parents:
            continue
        if not enabled(GATES["live"]):
            item.add_marker(pytest.mark.skip(reason="live tests need GPM_RUN_LIVE=1"))
            continue
        for marker, variable in GATES.items():
            if item.get_closest_marker(marker) and not enabled(variable):
                item.add_marker(pytest.mark.skip(reason=f"needs {variable}=1"))


@pytest.fixture
def live_client() -> Iterator[GPMClient]:
    port = os.environ.get("GPM_API_PORT")
    if not port:
        pytest.skip("set GPM_API_PORT explicitly for live tests")
    with GPMClient(port=int(port)) as client:
        yield client
