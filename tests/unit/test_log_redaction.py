from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

import httpx
import pytest

from gpmlogin_sdk import AsyncGPMClient, GPMClient
from gpmlogin_sdk._logging import install_query_redaction
from tests.conftest import Api, json_response


def empty_page(request: httpx.Request) -> httpx.Response:
    return json_response(
        {"current_page": 1, "per_page": 30, "total": 0, "last_page": 1, "data": []}
    )


def httpx_messages(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(r.getMessage() for r in caplog.records if r.name == "httpx")


def test_httpx_info_logs_never_contain_the_query_string(
    api_factory: Callable[..., Api], mode: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="httpx")
    api = api_factory(mode, empty_page)
    api.call("proxies.list", search="user:pw@10.1.2.3")
    text = httpx_messages(caplog)
    assert "/api/v1/proxies" in text
    assert "pw@10.1.2.3" not in text
    assert "search" not in text


def test_start_options_in_the_query_are_not_logged(
    api_factory: Callable[..., Api], mode: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="httpx")

    def start(request: httpx.Request) -> httpx.Response:
        return json_response({"profile_id": "p1", "remote_debugging_port": 9222})

    api = api_factory(mode, start)
    api.call("profiles.start", "p1", {"addition_args": "--proxy-auth=s3cr3t-pw"})
    text = httpx_messages(caplog)
    assert "/api/v1/profiles/start/p1" in text
    assert "s3cr3t-pw" not in text


def test_urls_that_are_not_the_gpm_api_are_left_alone() -> None:
    record = logging.LogRecord(
        "httpx", logging.INFO, __file__, 1, "%s", (httpx.URL("https://example.com/x?q=1"),), None
    )
    install_query_redaction()
    logger = logging.getLogger("httpx")
    for log_filter in logger.filters:
        log_filter.filter(record)
    assert record.getMessage() == "https://example.com/x?q=1"


def test_the_filter_is_installed_once_however_many_clients_exist() -> None:
    install_query_redaction()
    count = len(logging.getLogger("httpx").filters)
    clients = [GPMClient() for _ in range(3)] + [AsyncGPMClient() for _ in range(3)]
    install_query_redaction()
    assert len(logging.getLogger("httpx").filters) == count
    for client in clients[:3]:
        client.close()
    for async_client in clients[3:]:
        asyncio.run(async_client.aclose())
