from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from gpmlogin_sdk._operations import Operation, parse_none
from gpmlogin_sdk.async_client import AsyncGPMClient
from gpmlogin_sdk.client import GPMClient
from gpmlogin_sdk.errors import GPMConfigurationError
from tests.conftest import json_response

PING = Operation("profiles.stop", "GET", "/profiles/stop/p1", True, parse_none)


class Recorder:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return json_response(None)


@pytest.fixture
def count_calls(monkeypatch: pytest.MonkeyPatch) -> Callable[[type, str], list[int]]:
    def patch(cls: type, name: str) -> list[int]:
        calls: list[int] = []
        original = getattr(cls, name)
        if asyncio.iscoroutinefunction(original):

            async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
                calls.append(1)
                return await original(self, *args, **kwargs)
        else:

            def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:  # type: ignore[misc]
                calls.append(1)
                return original(self, *args, **kwargs)

        monkeypatch.setattr(cls, name, wrapper)
        return calls

    return patch


def test_injected_sync_client_is_never_closed_by_the_sdk() -> None:
    recorder = Recorder()
    external = httpx.Client(transport=httpx.MockTransport(recorder))
    with GPMClient(http_client=external) as client:
        assert client.config.port == 9495
        assert recorder.requests == [], "constructing a client performs no network I/O"
    assert not external.is_closed
    with pytest.raises(GPMConfigurationError):
        client._transport.request(PING)
    assert recorder.requests == []
    external.close()


def test_injected_sync_client_survives_a_failing_with_body() -> None:
    external = httpx.Client(transport=httpx.MockTransport(Recorder()))
    with pytest.raises(RuntimeError), GPMClient(http_client=external):
        raise RuntimeError("task failed")
    assert not external.is_closed
    external.close()


def test_owned_sync_client_is_configured_safely_and_closed_exactly_once(
    count_calls: Callable[[type, str], list[int]],
) -> None:
    closes = count_calls(httpx.Client, "close")
    with GPMClient(port=9001, timeout=7) as client:
        owned = client._http
        assert isinstance(owned, httpx.Client)
        assert owned.trust_env is False
        assert owned.follow_redirects is False
        assert owned.timeout.read == 7
        assert not owned.is_closed
    assert owned.is_closed
    client.close()
    client.close()
    assert len(closes) == 1


def test_owned_client_is_closed_when_the_with_body_fails() -> None:
    holder: list[GPMClient] = []
    with pytest.raises(RuntimeError), GPMClient() as client:
        holder.append(client)
        raise RuntimeError("boom")
    assert holder[0]._http.is_closed


def test_operation_after_close_raises_configuration_error_without_http() -> None:
    recorder = Recorder()
    external = httpx.Client(transport=httpx.MockTransport(recorder))
    client = GPMClient(http_client=external)
    client._transport.request(PING)
    client.close()
    with pytest.raises(GPMConfigurationError):
        client._transport.request(PING)
    assert len(recorder.requests) == 1
    external.close()


def test_externally_closed_injected_client_raises_configuration_error() -> None:
    external = httpx.Client(transport=httpx.MockTransport(Recorder()))
    client = GPMClient(http_client=external)
    external.close()
    with pytest.raises(GPMConfigurationError):
        client._transport.request(PING)


def test_wrong_http_client_kind_is_rejected_before_anything_is_created(
    count_calls: Callable[[type, str], list[int]],
) -> None:
    async_http = httpx.AsyncClient(transport=httpx.MockTransport(Recorder()))
    with pytest.raises(GPMConfigurationError):
        GPMClient(http_client=async_http)  # type: ignore[arg-type]
    with pytest.raises(GPMConfigurationError):
        GPMClient(http_client=object())  # type: ignore[arg-type]
    sync_http = httpx.Client(transport=httpx.MockTransport(Recorder()))
    with pytest.raises(GPMConfigurationError):
        AsyncGPMClient(http_client=sync_http)  # type: ignore[arg-type]
    sync_http.close()


def test_invalid_config_does_not_leak_an_owned_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[int] = []
    original = httpx.Client.__init__

    def tracking(self: httpx.Client, *args: Any, **kwargs: Any) -> None:
        created.append(1)
        original(self, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", tracking)
    with pytest.raises(GPMConfigurationError):
        GPMClient(host="example.com")
    assert created == []


def test_instances_do_not_share_config_and_env_is_read_at_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GPM_API_PORT", raising=False)
    first = GPMClient()
    monkeypatch.setenv("GPM_API_PORT", "9777")
    second = GPMClient()
    assert (first.config.port, second.config.port) == (9495, 9777)
    assert first.config is not second.config
    first.close()
    second.close()


@pytest.mark.asyncio
async def test_async_injected_client_is_never_closed() -> None:
    recorder = Recorder()
    external = httpx.AsyncClient(transport=httpx.MockTransport(recorder))
    async with AsyncGPMClient(http_client=external) as client:
        assert client.config.port == 9495
        await client._transport.request(PING)
    assert not external.is_closed
    with pytest.raises(GPMConfigurationError):
        await client._transport.request(PING)
    assert len(recorder.requests) == 1
    await external.aclose()


@pytest.mark.asyncio
async def test_async_injected_client_survives_task_cancellation() -> None:
    external = httpx.AsyncClient(transport=httpx.MockTransport(Recorder()))
    entered = asyncio.Event()

    async def worker() -> None:
        async with AsyncGPMClient(http_client=external):
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.ensure_future(worker())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not external.is_closed
    await external.aclose()


@pytest.mark.asyncio
async def test_async_owned_client_is_configured_safely_and_closed_exactly_once(
    count_calls: Callable[[type, str], list[int]],
) -> None:
    closes = count_calls(httpx.AsyncClient, "aclose")
    async with AsyncGPMClient(port=9001) as client:
        owned = client._http
        assert isinstance(owned, httpx.AsyncClient)
        assert owned.trust_env is False
        assert owned.follow_redirects is False
    assert owned.is_closed
    await client.aclose()
    await client.aclose()
    assert len(closes) == 1


@pytest.mark.asyncio
async def test_async_client_never_builds_a_sync_httpx_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(self: Any, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("sync httpx.Client must not be created by AsyncGPMClient")

    monkeypatch.setattr(httpx.Client, "__init__", forbidden)
    client = AsyncGPMClient()
    await client.aclose()
