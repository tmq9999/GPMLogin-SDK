from __future__ import annotations

import asyncio
import inspect
import subprocess
import sys
import traceback
from collections.abc import Callable
from typing import Any

import pytest
from playwright.sync_api import Error as PWError
from playwright.sync_api import TimeoutError as PWTimeout

from gpmlogin_sdk import (
    BrowserType,
    GPMIntegrationError,
    GPMValidationError,
    StartResult,
)
from gpmlogin_sdk.integrations import playwright as adapter
from tests.fakes import FakePlaywright, install_clock, make_world

WS = "ws://127.0.0.1:9222/devtools/browser/SECRET-WS-TOKEN"
REFUSED = "BrowserType.connect_over_cdp: connect ECONNREFUSED 127.0.0.1:9222"


def launch_result(
    ws: str | None = WS, port: int | None = 9222, profile_id: str = "p1"
) -> StartResult:
    return StartResult(
        profile_id=profile_id, remote_debugging_port=port, websocket_debugging_url=ws
    )


def attach(
    mode: str,
    launch: Any,
    pw: Any,
    body: Callable[[Any], Any] = lambda attachment: attachment,
    *,
    kind: Any = BrowserType.CHROME,
    **kwargs: Any,
) -> Any:
    if mode == "sync":
        with adapter.connect(launch, pw, browser_kind=kind, **kwargs) as attachment:
            return body(attachment)

    async def go() -> Any:
        async with adapter.connect_async(launch, pw, browser_kind=kind, **kwargs) as attachment:
            result = body(attachment)
            return await result if inspect.isawaitable(result) else result

    return asyncio.run(go())


def test_core_import_never_imports_playwright() -> None:
    code = (
        "import sys, gpmlogin_sdk, gpmlogin_sdk.integrations, gpmlogin_sdk.integrations.playwright;"
        "bad = [m for m in sys.modules if m == 'playwright' or m.startswith('playwright.')];"
        "assert not bad, bad"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("mode_name", ["sync", "async"])
def test_missing_dependency_gives_install_guidance(
    monkeypatch: pytest.MonkeyPatch, mode_name: str
) -> None:
    for name in ("playwright", "playwright.sync_api", "playwright.async_api"):
        monkeypatch.setitem(sys.modules, name, None)
    pw, *_ = make_world(mode_name)
    factory = adapter.connect if mode_name == "sync" else adapter.connect_async
    with pytest.raises(GPMIntegrationError) as caught:
        factory(launch_result(), pw, browser_kind=BrowserType.CHROME)
    assert "gpmlogin-sdk[playwright]" in str(caught.value)
    assert pw.chromium.calls == []


def test_connects_to_the_given_websocket_and_reuses_context_and_page(mode: str) -> None:
    pw, browser, context, events = make_world(mode)
    existing_page = context.pages[0]
    seen: dict[str, Any] = {}

    def body(attachment: Any) -> Any:
        seen["browser"] = attachment.browser
        seen["context"] = attachment.context
        return attachment.get_or_create_page()

    page = attach(mode, launch_result(), pw, body)
    assert pw.chromium.calls[0][0] == WS
    assert seen["browser"] is browser
    assert seen["context"] is context
    assert page is existing_page
    assert context.new_page_calls == 0
    assert events == ["detach"]
    assert browser.close_calls == 1
    assert pw.stop_calls == 0


def test_an_empty_context_gets_a_page_on_that_same_context(mode: str) -> None:
    pw, browser, context, events = make_world(mode, pages=0)
    page = attach(mode, launch_result(), pw, lambda attachment: attachment.get_or_create_page())
    assert page is context.pages[0]
    assert context.new_page_calls == 1


def test_no_context_detaches_then_raises(mode: str) -> None:
    pw, browser, context, events = make_world(mode, has_context=False)
    with pytest.raises(GPMIntegrationError):
        attach(mode, launch_result(), pw)
    assert events == ["detach"]
    assert browser.close_calls == 1


def test_falls_back_to_the_http_endpoint_only_when_the_websocket_is_missing(mode: str) -> None:
    pw, *_ = make_world(mode)
    attach(mode, launch_result(ws=None, port=9333), pw)
    assert pw.chromium.calls[0][0] == "http://127.0.0.1:9333"


@pytest.mark.parametrize(
    "ws",
    [
        "ws://localhost:9222/devtools/browser/x",
        "ws://127.0.0.1:9222/devtools/browser/x",
        "WS://LOCALHOST:9222/devtools/browser/x",
    ],
)
def test_loopback_websockets_are_accepted(mode: str, ws: str) -> None:
    pw, *_ = make_world(mode)
    attach(mode, launch_result(ws=ws), pw)
    assert pw.chromium.calls[0][0] == ws


@pytest.mark.parametrize(
    "ws",
    [
        "wss://127.0.0.1:9222/devtools/browser/x",
        "http://127.0.0.1:9222/devtools/browser/x",
        "ws://example.com:9222/devtools/browser/x",
        "ws://localhost.evil.com:9222/devtools/browser/x",
        "ws://127.0.0.2:9222/devtools/browser/x",
        "ws://[::1]:9222/devtools/browser/x",
        "ws://user:pw@127.0.0.1:9222/devtools/browser/x",
        "ws://user@127.0.0.1:9222/devtools/browser/x",
        "ws://127.0.0.1:9222@evil.com/devtools/browser/x",
        "ws://127.0.0.1:9222/devtools/browser/x#frag",
        "ws://127.0.0.1:99999/devtools/browser/x",
        "ws://127.0.0.1:0/devtools/browser/x",
        "ws://127.0.0.1/devtools/browser/x",
        "ws://127.0.0.1:abc/devtools/browser/x",
        "ws://127.0.0.1:9222/devtools/browser/x y",
        "ws://127.0.0.1:9222/devtools/browser/x\n",
        "",
        "not a url",
    ],
)
def test_bad_websockets_fail_without_falling_back_to_the_port(mode: str, ws: str) -> None:
    pw, *_ = make_world(mode)
    with pytest.raises(GPMIntegrationError) as caught:
        attach(mode, launch_result(ws=ws, port=9222), pw)
    assert pw.chromium.calls == []
    assert "evil.com" not in str(caught.value)


@pytest.mark.parametrize("port", [None, 0, -1, 70000, True, "9222", 9222.0])
def test_unusable_port_without_websocket_fails(mode: str, port: Any) -> None:
    pw, *_ = make_world(mode)
    with pytest.raises(GPMIntegrationError):
        attach(mode, launch_result(ws=None, port=port), pw)
    assert pw.chromium.calls == []


def test_firefox_is_rejected_before_any_connect(mode: str) -> None:
    pw, *_ = make_world(mode)
    with pytest.raises(GPMIntegrationError):
        attach(mode, launch_result(), pw, kind=BrowserType.FIREFOX)
    assert pw.chromium.calls == []


@pytest.mark.parametrize("kind", [1, 2, "chrome", None, BrowserType])
def test_browser_kind_must_be_a_browser_type_member(mode: str, kind: Any) -> None:
    pw, *_ = make_world(mode)
    with pytest.raises(GPMValidationError):
        attach(mode, launch_result(), pw, kind=kind)
    assert pw.chromium.calls == []


@pytest.mark.parametrize("timeout_ms", [0, -1, True, 1.5, "10", None])
def test_timeout_must_be_a_positive_int(mode: str, timeout_ms: Any) -> None:
    pw, *_ = make_world(mode)
    with pytest.raises(GPMValidationError):
        attach(mode, launch_result(), pw, timeout_ms=timeout_ms)
    assert pw.chromium.calls == []


@pytest.mark.parametrize("launch", [None, {"profile_id": "p1"}, "ws://127.0.0.1:9222/x"])
def test_launch_must_be_a_start_result(mode: str, launch: Any) -> None:
    pw, *_ = make_world(mode)
    with pytest.raises(GPMValidationError):
        attach(mode, launch, pw)


def test_connect_is_deferred_until_the_context_is_entered(mode: str) -> None:
    pw, *_ = make_world(mode)
    factory = adapter.connect if mode == "sync" else adapter.connect_async
    factory(launch_result(), pw, browser_kind=BrowserType.CHROME)
    assert pw.chromium.calls == []


def test_the_default_deadline_is_ten_seconds(mode: str, monkeypatch: pytest.MonkeyPatch) -> None:
    install_clock(monkeypatch, adapter)
    pw, *_ = make_world(mode)
    attach(mode, launch_result(), pw)
    assert pw.chromium.calls[0][1] == 10000


def refusing_world(mode: str, failures: int) -> tuple[FakePlaywright, list[str]]:
    pw, browser, _, events = make_world(mode)
    pw.chromium.outcomes = [PWError(REFUSED)] * failures + [browser]
    return pw, events


def test_retries_only_connection_refused_every_250_ms_then_connects(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = install_clock(monkeypatch, adapter)
    pw, events = refusing_world(mode, 3)
    attach(mode, launch_result(), pw)
    assert len(pw.chromium.calls) == 4
    assert clock.sleeps == [0.25, 0.25, 0.25]
    assert [timeout for _, timeout in pw.chromium.calls] == [10000, 9750, 9500, 9250]
    assert events == ["detach"]


def test_gives_up_when_the_total_deadline_is_spent(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = install_clock(monkeypatch, adapter)
    pw, _ = refusing_world(mode, 10_000)
    with pytest.raises(GPMIntegrationError) as caught:
        attach(mode, launch_result(), pw, timeout_ms=1000)
    assert len(pw.chromium.calls) == 4
    assert clock.sleeps == [0.25] * 4
    for index, (_, timeout) in enumerate(pw.chromium.calls):
        assert timeout <= 1000 - index * 250
    assert caught.value.__cause__ is None
    assert "SECRET-WS-TOKEN" not in "".join(traceback.format_exception(caught.value))


def test_the_last_wait_never_overshoots_the_deadline(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = install_clock(monkeypatch, adapter)
    pw, _ = refusing_world(mode, 10_000)
    with pytest.raises(GPMIntegrationError):
        attach(mode, launch_result(), pw, timeout_ms=600)
    assert sum(clock.sleeps) == pytest.approx(0.6)
    assert len(pw.chromium.calls) == 3


@pytest.mark.parametrize(
    "error",
    [
        PWError("Target page, context or browser has been closed"),
        PWError("BrowserType.connect_over_cdp: 401 Unauthorized"),
        PWError("net::ERR_CONNECTION_REFUSED"),
        PWTimeout("Timeout 10000ms exceeded while connect ECONNREFUSED"),
        PWError("Protocol error (Browser.getVersion): invalid"),
    ],
    ids=["closed", "auth", "chromium-style-refused", "timeout", "protocol"],
)
def test_other_failures_fail_at_once_without_retry(
    mode: str, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    clock = install_clock(monkeypatch, adapter)
    pw, *_ = make_world(mode)
    pw.chromium.outcomes = [error]
    with pytest.raises(GPMIntegrationError) as caught:
        attach(mode, launch_result(), pw)
    assert len(pw.chromium.calls) == 1
    assert clock.sleeps == []
    assert caught.value.__cause__ is None and caught.value.__context__ is None


def test_non_playwright_exceptions_propagate_unchanged(mode: str) -> None:
    pw, *_ = make_world(mode)
    boom = RuntimeError("bug")
    pw.chromium.outcomes = [boom]
    with pytest.raises(RuntimeError) as caught:
        attach(mode, launch_result(), pw)
    assert caught.value is boom


def test_a_task_error_survives_and_detach_still_happens(mode: str) -> None:
    pw, browser, _, events = make_world(mode)
    original = ValueError("task")

    def body(attachment: Any) -> None:
        raise original

    with pytest.raises(ValueError) as caught:
        attach(mode, launch_result(), pw, body)
    assert caught.value is original
    assert events == ["detach"]


def test_a_detach_failure_alone_raises_a_safe_integration_error(mode: str) -> None:
    pw, *_ = make_world(mode, close_error=RuntimeError("raw-close-secret"))
    with pytest.raises(GPMIntegrationError) as caught:
        attach(mode, launch_result(), pw)
    assert "raw-close-secret" not in "".join(traceback.format_exception(caught.value))


def test_a_detach_failure_never_replaces_the_task_error(mode: str) -> None:
    pw, *_ = make_world(mode, close_error=RuntimeError("raw-close-secret"))
    original = ValueError("task")

    def body(attachment: Any) -> None:
        raise original

    with pytest.raises(ValueError) as caught:
        attach(mode, launch_result(), pw, body)
    assert caught.value is original
    assert any("detach" in note.lower() for note in caught.value.__notes__)


def test_an_attachment_context_is_single_use() -> None:
    pw, *_ = make_world("sync")
    manager = adapter.connect(launch_result(), pw, browser_kind=BrowserType.CHROME)
    with manager:
        pass
    with pytest.raises(GPMIntegrationError):
        manager.__enter__()


@pytest.mark.asyncio
async def test_cancellation_inside_the_body_still_detaches_then_re_raises() -> None:
    pw, browser, _, events = make_world("async")
    inside = asyncio.Event()

    async def runner() -> None:
        async with adapter.connect_async(launch_result(), pw, browser_kind=BrowserType.CHROME):
            inside.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(runner())
    await inside.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert events == ["detach"]


@pytest.mark.asyncio
async def test_a_hanging_async_detach_is_bounded_and_awaited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pw, browser, _, events = make_world("async")
    cancelled: list[str] = []

    async def hanging_close() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.append("cancelled")
            raise

    browser.close = hanging_close
    monkeypatch.setattr(adapter, "DETACH_TIMEOUT_SECONDS", 0.05)
    with pytest.raises(GPMIntegrationError):
        async with adapter.connect_async(launch_result(), pw, browser_kind=BrowserType.CHROME):
            pass
    assert cancelled == ["cancelled"]
    assert [t for t in asyncio.all_tasks() if t is not asyncio.current_task()] == []
