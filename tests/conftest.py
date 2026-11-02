"""Shared test helpers. Every HTTP request in the suite goes through ``httpx.MockTransport``."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest

Handler = Callable[[httpx.Request], httpx.Response]


def envelope(data: object = None, *, success: bool = True, message: str = "OK") -> dict[str, Any]:
    return {"success": success, "data": data, "message": message, "sender": "GPMLogin Test"}


def json_response(data: object = None, *, status: int = 200, **kwargs: Any) -> httpx.Response:
    return httpx.Response(status, json=envelope(data, **kwargs))


class TransportHarness:
    """Drives the sync or async transport through one interface and records requests."""

    def __init__(self, mode: str, handler: Handler, config: Any, client_kwargs: dict[str, Any]):
        from gpmlogin_sdk._async_transport import AsyncTransport
        from gpmlogin_sdk._transport import Transport

        self.mode = mode
        self.requests: list[httpx.Request] = []

        def recording(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return handler(request)

        mock = httpx.MockTransport(recording)
        self.http: httpx.Client | httpx.AsyncClient
        if mode == "sync":
            self.http = httpx.Client(transport=mock, **client_kwargs)
            self.transport: Any = Transport(config, self.http)
        else:
            self.http = httpx.AsyncClient(transport=mock, **client_kwargs)
            self.transport = AsyncTransport(config, self.http)

    def request(self, operation: Any, **kwargs: Any) -> Any:
        if self.mode == "sync":
            return self.transport.request(operation, **kwargs)
        return asyncio.run(self.transport.request(operation, **kwargs))

    def close(self) -> None:
        if isinstance(self.http, httpx.AsyncClient):
            asyncio.run(self.http.aclose())
        else:
            self.http.close()


@pytest.fixture(params=["sync", "async"])
def mode(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.fixture
def make_harness() -> Iterator[Callable[..., TransportHarness]]:
    from gpmlogin_sdk.config import resolve_config

    created: list[TransportHarness] = []

    def make(
        mode: str, handler: Handler, *, config: Any = None, **client_kwargs: Any
    ) -> TransportHarness:
        harness = TransportHarness(mode, handler, config or resolve_config(), client_kwargs)
        created.append(harness)
        return harness

    yield make
    for harness in created:
        harness.close()


class Api:
    """A real SDK client (sync or async) wired to a mock transport, called through one interface."""

    def __init__(self, mode: str, client: Any, http: Any, requests: list[httpx.Request]) -> None:
        self.mode = mode
        self.client = client
        self.http = http
        self.requests = requests

    def call(self, dotted: str, *args: Any, **kwargs: Any) -> Any:
        target: Any = self.client
        for part in dotted.split("."):
            target = getattr(target, part)
        result = target(*args, **kwargs)
        if inspect.isawaitable(result):
            return asyncio.run(_await(result))
        return result

    def close(self) -> None:
        if self.mode == "async":
            asyncio.run(self.client.aclose())
            asyncio.run(self.http.aclose())
        else:
            self.client.close()
            self.http.close()


async def _await(awaitable: Any) -> Any:
    return await awaitable


@pytest.fixture
def api_factory() -> Iterator[Callable[..., Api]]:
    from gpmlogin_sdk import AsyncGPMClient, GPMClient

    created: list[Api] = []

    def make(mode: str, handler: Handler, **client_options: Any) -> Api:
        requests: list[httpx.Request] = []

        def recording(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return handler(request)

        mock = httpx.MockTransport(recording)
        if mode == "sync":
            http: Any = httpx.Client(transport=mock)
            client: Any = GPMClient(http_client=http, **client_options)
        else:
            http = httpx.AsyncClient(transport=mock)
            client = AsyncGPMClient(http_client=http, **client_options)
        api = Api(mode, client, http, requests)
        created.append(api)
        return api

    yield make
    for api in created:
        api.close()
