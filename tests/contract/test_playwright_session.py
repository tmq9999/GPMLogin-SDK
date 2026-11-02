from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from gpmlogin_sdk import (
    AsyncGPMClient,
    BrowserType,
    GPMCleanupError,
    GPMClient,
    GPMIntegrationError,
    GPMProtocolError,
    _ownership,
)
from gpmlogin_sdk.integrations import playwright as adapter
from tests.conftest import json_response
from tests.fakes import install_clock, make_world

WS = "ws://127.0.0.1:9222/devtools/browser/abc"
START_DATA = {
    "profile_id": "p1",
    "remote_debugging_port": 9222,
    "websocket_debugging_url": WS,
}


@pytest.fixture(autouse=True)
def clean_registry() -> Any:
    assert set() == _ownership._HELD
    yield
    leaked = set(_ownership._HELD)
    _ownership._HELD.clear()
    assert leaked == set()


def server(events: list[str], *, start: Any = None) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/profiles/start/" in request.url.path:
            events.append("start")
            return start(request) if start else json_response(START_DATA)
        if "/profiles/stop/" in request.url.path:
            events.append("stop")
            return json_response(None)
        return httpx.Response(500)

    return handler


def run(mode: str, events: list[str], pw: Any, body: Any, *, start: Any = None) -> Any:
    handler = server(events, start=start)
    if mode == "sync":
        with httpx.Client(transport=httpx.MockTransport(handler)) as http:
            client = GPMClient(http_client=http)
            with client.profile_session("p1", exclusive=True) as session:
                with adapter.connect(
                    session.launch, pw, browser_kind=BrowserType.CHROME
                ) as attachment:
                    return body(attachment)

    async def go() -> Any:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = AsyncGPMClient(http_client=http)
            async with client.profile_session("p1", exclusive=True) as session:
                async with adapter.connect_async(
                    session.launch, pw, browser_kind=BrowserType.CHROME
                ) as attachment:
                    result = body(attachment)
                    return await result if asyncio.iscoroutine(result) else result

    return asyncio.run(go())


def test_detach_happens_before_stop_and_the_page_is_the_existing_one(mode: str) -> None:
    events: list[str] = []
    pw, browser, context, _ = make_world(mode, events=events)
    existing = context.pages[0]
    page = run(mode, events, pw, lambda attachment: attachment.get_or_create_page())
    assert pw.chromium.calls[0][0] == WS
    assert page is existing
    assert events == ["start", "detach", "stop"]
    assert pw.stop_calls == 0


def test_a_task_error_detaches_then_stops_and_keeps_its_identity(mode: str) -> None:
    events: list[str] = []
    pw, *_ = make_world(mode, events=events)
    original = ValueError("task")

    def body(attachment: Any) -> None:
        raise original

    with pytest.raises(ValueError) as caught:
        run(mode, events, pw, body)
    assert caught.value is original
    assert events == ["start", "detach", "stop"]


def test_a_connect_failure_leaves_the_session_to_stop_the_profile(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from playwright.sync_api import Error as PWError

    events: list[str] = []
    install_clock(monkeypatch, adapter)
    pw, *_ = make_world(mode, events=events)
    pw.chromium.outcomes = [PWError("connect ECONNREFUSED 127.0.0.1:9222")]
    with pytest.raises(GPMIntegrationError):
        run(mode, events, pw, lambda attachment: None)
    assert events == ["start", "stop"]
    assert len(pw.chromium.calls) == 40


def test_a_detach_failure_is_reported_and_the_session_still_stops(mode: str) -> None:
    events: list[str] = []
    pw, *_ = make_world(mode, events=events, close_error=RuntimeError("raw"))
    with pytest.raises(GPMIntegrationError):
        run(mode, events, pw, lambda attachment: None)
    assert events == ["start", "detach", "stop"]


def test_the_adapter_never_restarts_gpm_on_retry(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from playwright.sync_api import Error as PWError

    events: list[str] = []
    install_clock(monkeypatch, adapter)
    pw, browser, *_ = make_world(mode, events=events)
    pw.chromium.outcomes = [PWError("connect ECONNREFUSED 127.0.0.1:9222")] * 3 + [browser]
    run(mode, events, pw, lambda attachment: None)
    assert events == ["start", "detach", "stop"]
    assert len(pw.chromium.calls) == 4


def test_a_malformed_start_never_reaches_the_adapter(mode: str) -> None:
    events: list[str] = []
    pw, *_ = make_world(mode, events=events)
    with pytest.raises(GPMProtocolError):
        run(
            mode,
            events,
            pw,
            lambda attachment: None,
            start=lambda request: json_response({"profile_id": "p1"}),
        )
    assert pw.chromium.calls == []
    assert events == ["start", "stop"]


@pytest.mark.asyncio
async def test_cancel_inside_the_attachment_detaches_then_stops_then_cancels() -> None:
    events: list[str] = []
    stop_gate = asyncio.Event()
    inside = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        if "/profiles/start/" in request.url.path:
            events.append("start")
            return json_response(START_DATA)
        events.append("stop")
        await stop_gate.wait()
        events.append("stopped")
        return json_response(None)

    pw, *_ = make_world("async", events=events)

    async def runner() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = AsyncGPMClient(http_client=http)
            async with client.profile_session("p1", exclusive=True) as session:
                async with adapter.connect_async(
                    session.launch, pw, browser_kind=BrowserType.CHROME
                ):
                    inside.set()
                    await asyncio.Event().wait()

    task = asyncio.create_task(runner())
    await inside.wait()
    task.cancel()
    for _ in range(10):
        await asyncio.sleep(0)
    assert events == ["start", "detach", "stop"]
    assert not task.done()
    stop_gate.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert events == ["start", "detach", "stop", "stopped"]


def test_a_stop_failure_after_a_clean_attachment_is_a_cleanup_error() -> None:
    events: list[str] = []
    pw, *_ = make_world("sync", events=events)

    def handler(request: httpx.Request) -> httpx.Response:
        if "/profiles/start/" in request.url.path:
            events.append("start")
            return json_response(START_DATA)
        events.append("stop")
        return httpx.Response(500)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = GPMClient(http_client=http)
        with pytest.raises(GPMCleanupError):
            with client.profile_session("p1", exclusive=True) as session:
                with adapter.connect(session.launch, pw, browser_kind=BrowserType.CHROME):
                    pass
    assert events == ["start", "detach", "stop"]
