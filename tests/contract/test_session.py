from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx
import pytest
import pytest_asyncio

from gpmlogin_sdk import (
    AsyncGPMClient,
    GPMAPIError,
    GPMCleanupError,
    GPMClient,
    GPMProfileBusyError,
    GPMProtocolError,
    GPMTimeoutError,
    GPMValidationError,
    _ownership,
)
from gpmlogin_sdk.helpers import session as session_module
from tests.conftest import Api, envelope, json_response

SECRET_WS = "ws://127.0.0.1:9222/devtools/browser/SECRET-WS-TOKEN"
START_DATA = {
    "profile_id": "p1",
    "remote_debugging_port": 9222,
    "websocket_debugging_url": SECRET_WS,
}
KEY = ("127.0.0.1", 9495)


class Abort(BaseException):
    pass


class Server:
    def __init__(
        self,
        *,
        start: Callable[[httpx.Request], httpx.Response] | None = None,
        stop: Callable[[httpx.Request], httpx.Response] | None = None,
    ) -> None:
        self.events: list[str] = []
        self.requests: list[httpx.Request] = []
        self._start = start or (lambda request: json_response(START_DATA))
        self._stop = stop or (lambda request: json_response(None))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if "/profiles/start/" in path:
            self.events.append("start")
            return self._start(request)
        if "/profiles/stop/" in path:
            self.events.append("stop")
            return self._stop(request)
        return httpx.Response(500)


@pytest.fixture(autouse=True)
def clean_registry() -> Any:
    assert set() == _ownership._HELD
    yield
    leaked = set(_ownership._HELD)
    _ownership._HELD.clear()
    assert leaked == set(), "a session leaked its profile lease"


def run(api: Api, body: Callable[[Any], Any], *args: Any, **kwargs: Any) -> Any:
    if api.mode == "sync":
        with api.client.profile_session(*args, **kwargs) as session:
            return body(session)

    async def go() -> Any:
        async with api.client.profile_session(*args, **kwargs) as session:
            return body(session)

    return asyncio.run(go())


def assert_lock_is_free(profile_id: str = "p1") -> None:
    _ownership.acquire_profile(KEY, profile_id).release()


def test_success_runs_start_task_stop_once_and_never_deletes(
    api_factory: Callable[..., Api], mode: str
) -> None:
    server = Server()
    api = api_factory(mode, server)

    def body(session: Any) -> str:
        server.events.append("task")
        assert session.profile_id == "p1"
        assert session.launch.remote_debugging_port == 9222
        assert SECRET_WS not in repr(session)
        return "result"

    assert run(api, body, "p1", exclusive=True) == "result"
    assert server.events == ["start", "task", "stop"]
    assert not any("delete" in r.url.path for r in server.requests)
    assert_lock_is_free()


def test_start_options_are_sent_to_start(api_factory: Callable[..., Api], mode: str) -> None:
    server = Server()
    api = api_factory(mode, server)
    run(api, lambda s: None, "p1", exclusive=True, start_options={"window_size": "800,600"})
    assert server.requests[0].url.params["window_size"] == "800,600"


@pytest.mark.parametrize("exclusive", [None, False, 1, "true", "yes"])
def test_exclusive_must_be_literal_true(
    api_factory: Callable[..., Api], mode: str, exclusive: Any
) -> None:
    server = Server()
    api = api_factory(mode, server)
    with pytest.raises(GPMValidationError):
        run(api, lambda s: None, "p1", exclusive=exclusive)
    assert server.requests == []
    assert_lock_is_free()


def test_exclusive_defaults_to_rejected(api_factory: Callable[..., Api], mode: str) -> None:
    server = Server()
    api = api_factory(mode, server)
    with pytest.raises(GPMValidationError):
        run(api, lambda s: None, "p1")
    assert server.requests == []


@pytest.mark.parametrize(
    ("profile_id", "options"),
    [("", None), (".", None), (None, None), ("p1", {"window_size": "bad"}), ("p1", {"nope": 1})],
)
def test_bad_arguments_fail_before_any_request_or_lock(
    api_factory: Callable[..., Api], mode: str, profile_id: Any, options: Any
) -> None:
    server = Server()
    api = api_factory(mode, server)
    with pytest.raises(GPMValidationError):
        run(api, lambda s: None, profile_id, exclusive=True, start_options=options)
    assert server.requests == []
    assert set() == _ownership._HELD


@pytest.mark.parametrize("host", [None, "localhost", "127.0.0.1"])
def test_a_held_profile_is_busy_for_any_loopback_spelling(
    api_factory: Callable[..., Api], mode: str, host: str | None
) -> None:
    server = Server()
    api = api_factory(mode, server, **({"host": host} if host else {}))
    lease = _ownership.acquire_profile(KEY, "p1")
    try:
        with pytest.raises(GPMProfileBusyError):
            run(api, lambda s: None, "p1", exclusive=True)
        assert server.requests == []
    finally:
        lease.release()


def test_sync_and_async_clients_contend_for_the_same_profile() -> None:
    sync_server, async_server = Server(), Server()
    sync_http = httpx.Client(transport=httpx.MockTransport(sync_server))
    async_http = httpx.AsyncClient(transport=httpx.MockTransport(async_server))
    sync_client = GPMClient(http_client=sync_http, host="localhost")
    async_client = AsyncGPMClient(http_client=async_http)

    async def second() -> None:
        async with async_client.profile_session("p1", exclusive=True):
            pass

    try:
        with sync_client.profile_session("p1", exclusive=True):
            with pytest.raises(GPMProfileBusyError):
                asyncio.run(second())
            assert async_server.requests == []
        asyncio.run(second())
        assert async_server.events == ["start", "stop"]
    finally:
        sync_client.close()
        asyncio.run(async_client.aclose())
        sync_http.close()
        asyncio.run(async_http.aclose())


def test_other_profiles_and_ports_do_not_contend(
    api_factory: Callable[..., Api], mode: str
) -> None:
    server = Server()
    api = api_factory(mode, server)
    other_profile = _ownership.acquire_profile(KEY, "other")
    other_port = _ownership.acquire_profile(("127.0.0.1", 9999), "p1")
    try:
        run(api, lambda s: None, "p1", exclusive=True)
        assert server.events == ["start", "stop"]
    finally:
        other_profile.release()
        other_port.release()


def test_task_error_and_stop_error_keep_the_task_error_and_attach_cleanup(
    api_factory: Callable[..., Api], mode: str
) -> None:
    server = Server(stop=lambda request: httpx.Response(500))
    api = api_factory(mode, server)
    original = ValueError("task failed")

    def body(session: Any) -> None:
        raise original

    with pytest.raises(ValueError) as caught:
        run(api, body, "p1", exclusive=True)
    assert caught.value is original
    assert isinstance(caught.value.cleanup_error, GPMCleanupError)  # type: ignore[attr-defined]
    assert server.events == ["start", "stop"]
    assert_lock_is_free()


def test_only_the_stop_failing_raises_cleanup_error(
    api_factory: Callable[..., Api], mode: str
) -> None:
    server = Server(stop=lambda request: json_response(None, success=False))
    api = api_factory(mode, server)
    with pytest.raises(GPMCleanupError) as caught:
        run(api, lambda s: "ok", "p1", exclusive=True)
    assert isinstance(caught.value.stop_error, GPMAPIError)
    assert caught.value.__cause__ is None
    assert server.events == ["start", "stop"]
    assert_lock_is_free()


def test_base_exceptions_still_stop_exactly_once(
    api_factory: Callable[..., Api], mode: str
) -> None:
    server = Server()
    api = api_factory(mode, server)

    def body(session: Any) -> None:
        raise Abort

    with pytest.raises(Abort):
        run(api, body, "p1", exclusive=True)
    assert server.events == ["start", "stop"]
    assert_lock_is_free()


def test_confirmed_success_with_malformed_data_stops_once_then_raises_protocol_error(
    api_factory: Callable[..., Api], mode: str
) -> None:
    server = Server(start=lambda request: json_response({"profile_id": "p1"}))
    api = api_factory(mode, server)
    ran: list[str] = []
    with pytest.raises(GPMProtocolError) as caught:
        run(api, lambda s: ran.append("task"), "p1", exclusive=True)
    assert caught.value.success_confirmed is True
    assert caught.value.cleanup_error is None
    assert ran == []
    assert server.events == ["start", "stop"]
    assert_lock_is_free()


def test_malformed_start_with_failing_stop_keeps_the_protocol_error(
    api_factory: Callable[..., Api], mode: str
) -> None:
    server = Server(
        start=lambda request: json_response({"profile_id": "p1"}),
        stop=lambda request: httpx.Response(500),
    )
    api = api_factory(mode, server)
    with pytest.raises(GPMProtocolError) as caught:
        run(api, lambda s: None, "p1", exclusive=True)
    assert isinstance(caught.value.cleanup_error, GPMCleanupError)
    assert server.events == ["start", "stop"]
    assert_lock_is_free()


def raise_timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("slow", request=request)


@pytest.mark.parametrize(
    ("start", "error"),
    [
        (lambda request: json_response(None, success=False), GPMAPIError),
        (raise_timeout, GPMTimeoutError),
        (lambda request: httpx.Response(200, content=b"not json"), GPMProtocolError),
        (lambda request: httpx.Response(200, json={"data": START_DATA}), GPMProtocolError),
    ],
    ids=["api-failure", "timeout", "non-json", "no-success-flag"],
)
def test_unconfirmed_start_failures_never_stop_or_retry(
    api_factory: Callable[..., Api], mode: str, start: Any, error: type[Exception]
) -> None:
    server = Server(start=start)
    api = api_factory(mode, server)
    with pytest.raises(error) as caught:
        run(api, lambda s: None, "p1", exclusive=True)
    assert server.events == ["start"]
    if error is GPMTimeoutError:
        assert caught.value.state_uncertain is True  # type: ignore[attr-defined]
    assert_lock_is_free()


def test_stop_uses_a_timeout_of_at_most_ten_seconds_even_with_a_long_client_timeout(
    api_factory: Callable[..., Api], mode: str
) -> None:
    server = Server()
    api = api_factory(mode, server, timeout=30)
    run(api, lambda s: None, "p1", exclusive=True)
    start_request, stop_request = server.requests
    assert start_request.extensions["timeout"]["read"] == 30
    assert stop_request.extensions["timeout"]["read"] <= 10


def test_a_short_client_timeout_is_kept_for_stop(
    api_factory: Callable[..., Api], mode: str
) -> None:
    server = Server()
    api = api_factory(mode, server, timeout=2)
    run(api, lambda s: None, "p1", exclusive=True)
    assert server.requests[1].extensions["timeout"]["read"] == 2


def test_error_text_and_traceback_never_leak_the_vendor_message(
    api_factory: Callable[..., Api], mode: str
) -> None:
    import traceback

    server = Server(
        stop=lambda request: httpx.Response(
            200, json=envelope(None, success=False, message="vendor-secret")
        )
    )
    api = api_factory(mode, server)
    with pytest.raises(GPMCleanupError) as caught:
        run(api, lambda s: None, "p1", exclusive=True)
    assert "vendor-secret" not in "".join(traceback.format_exception(caught.value))


class AsyncServer:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.start_gate: asyncio.Event | None = None
        self.stop_gate: asyncio.Event | None = None
        self.stop_finished = False

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/profiles/start/" in path:
            self.events.append("start")
            if self.start_gate is not None:
                await self.start_gate.wait()
            return json_response(START_DATA)
        if "/profiles/stop/" in path:
            self.events.append("stop")
            if self.stop_gate is not None:
                await self.stop_gate.wait()
            self.stop_finished = True
            return json_response(None)
        return httpx.Response(500)


async def spin(times: int = 5) -> None:
    for _ in range(times):
        await asyncio.sleep(0)


@pytest_asyncio.fixture
async def async_world() -> Any:
    server = AsyncServer()
    http = httpx.AsyncClient(transport=httpx.MockTransport(server))
    client = AsyncGPMClient(http_client=http)
    yield server, client
    await client.aclose()
    await http.aclose()


@pytest.mark.asyncio
async def test_cancel_during_the_task_waits_for_stop_then_re_raises(async_world: Any) -> None:
    server, client = async_world
    server.stop_gate = asyncio.Event()
    in_task = asyncio.Event()

    async def runner() -> None:
        async with client.profile_session("p1", exclusive=True):
            in_task.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(runner())
    await in_task.wait()
    task.cancel()
    await spin()
    assert not task.done()
    assert server.events == ["start", "stop"]
    server.stop_gate.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert server.stop_finished is True
    assert server.events == ["start", "stop"]
    assert_lock_is_free()


@pytest.mark.asyncio
async def test_cancel_before_start_is_confirmed_never_stops(async_world: Any) -> None:
    server, client = async_world
    server.start_gate = asyncio.Event()

    async def runner() -> None:
        async with client.profile_session("p1", exclusive=True):
            raise AssertionError("body must not run")

    task = asyncio.create_task(runner())
    await spin()
    assert server.events == ["start"]
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert server.events == ["start"]
    assert_lock_is_free()


@pytest.mark.asyncio
async def test_repeated_cancels_during_cleanup_do_not_create_a_second_stop(
    async_world: Any,
) -> None:
    server, client = async_world
    server.stop_gate = asyncio.Event()
    in_task = asyncio.Event()

    async def runner() -> None:
        async with client.profile_session("p1", exclusive=True):
            in_task.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(runner())
    await in_task.wait()
    task.cancel()
    await spin()
    task.cancel()
    await spin()
    task.cancel()
    await spin()
    assert not task.done()
    assert server.events.count("stop") == 1
    with pytest.raises(_ownership.GPMProfileBusyError):
        _ownership.acquire_profile(KEY, "p1")
    server.stop_gate.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert server.events.count("stop") == 1
    assert server.stop_finished is True
    assert_lock_is_free()


@pytest.mark.asyncio
async def test_cleanup_that_outlives_the_deadline_is_cancelled_and_awaited(
    async_world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, client = async_world
    server.stop_gate = asyncio.Event()
    monkeypatch.setattr(session_module, "CLEANUP_TIMEOUT_SECONDS", 0.05)
    with pytest.raises(GPMCleanupError):
        async with client.profile_session("p1", exclusive=True):
            pass
    assert server.stop_finished is False
    assert server.events == ["start", "stop"]
    assert_lock_is_free()
    assert [t for t in asyncio.all_tasks() if t is not asyncio.current_task()] == []


@pytest.mark.asyncio
async def test_cancel_while_start_returns_malformed_data_still_stops_then_cancels(
    async_world: Any,
) -> None:
    server, client = async_world
    server.stop_gate = asyncio.Event()

    async def bad_start(request: httpx.Request) -> httpx.Response:
        if "/profiles/start/" in request.url.path:
            server.events.append("start")
            return json_response({"profile_id": "p1"})
        return await AsyncServer.__call__(server, request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(bad_start))
    other = AsyncGPMClient(http_client=http)

    async def runner() -> None:
        async with other.profile_session("p1", exclusive=True):
            raise AssertionError("body must not run")

    task = asyncio.create_task(runner())
    await spin()
    assert server.events == ["start", "stop"]
    task.cancel()
    await spin()
    server.stop_gate.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert server.events.count("stop") == 1
    await other.aclose()
    await http.aclose()
    assert_lock_is_free()


def test_documentation_states_the_lock_is_process_local() -> None:
    doc = (GPMClient.profile_session.__doc__ or "").lower()
    assert "process" in doc
    assert "not" in doc and "distributed" in doc
