"""Optional Playwright adapter: attach to a started profile over CDP, detach on exit.

The adapter never starts or stops the profile and never stops the caller's Playwright instance.
Use it inside ``profile_session`` so the detach happens before the session stops the profile.
Only Chromium-based profiles are supported; Playwright is imported lazily when a function is
called, so the core SDK works without it.
"""

from __future__ import annotations

import asyncio
import time
from types import TracebackType
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from .._ownership import run_bounded_cleanup
from ..enums import BrowserType
from ..errors import GPMIntegrationError, GPMValidationError
from ..models import StartResult

if TYPE_CHECKING:
    from playwright.async_api import Browser as AsyncBrowser
    from playwright.async_api import BrowserContext as AsyncContext
    from playwright.async_api import Page as AsyncPage
    from playwright.async_api import Playwright as AsyncPlaywright
    from playwright.sync_api import Browser as SyncBrowser
    from playwright.sync_api import BrowserContext as SyncContext
    from playwright.sync_api import Page as SyncPage
    from playwright.sync_api import Playwright as SyncPlaywright

DETACH_TIMEOUT_SECONDS = 10.0
RETRY_INTERVAL_SECONDS = 0.25
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1"})
_REFUSED_MARK = "ECONNREFUSED"

_monotonic = time.monotonic
_sleep = time.sleep
_async_sleep = asyncio.sleep

_MISSING = 'Playwright is not installed. Install the extra: pip install "gpmlogin-sdk[playwright]".'
_FIREFOX = "Only Chromium-based profiles can be attached over CDP; Firefox is not supported."
_BAD_ENDPOINT = "The launch result has no usable local debugging endpoint."
_UNREACHABLE = "The browser debugging endpoint did not accept a connection in time."
_FAILED = "Playwright could not attach to the browser debugging endpoint."
_NO_CONTEXT = "The attached browser has no default context to reuse."
_DETACH_FAILED = "Playwright could not cleanly detach from the browser."
_DETACH_NOTE = "Playwright detach also failed."
_REUSED = "An attachment context can only be entered once."

ErrorTypes = tuple[type[Exception], type[Exception]]


def _playwright_error_types(*, use_async: bool) -> ErrorTypes:
    found: ErrorTypes | None = None
    try:
        if use_async:
            from playwright.async_api import Error, TimeoutError
        else:
            from playwright.sync_api import Error, TimeoutError
        found = (Error, TimeoutError)
    except ImportError:
        found = None
    if found is None:
        raise GPMIntegrationError(_MISSING)
    return found


def _check_inputs(launch: object, browser_kind: object, timeout_ms: object) -> None:
    if not isinstance(launch, StartResult):
        raise GPMValidationError("launch must be a StartResult.", field="launch")
    if not isinstance(browser_kind, BrowserType):
        raise GPMValidationError("browser_kind must be a BrowserType.", field="browser_kind")
    if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int) or timeout_ms <= 0:
        raise GPMValidationError("timeout_ms must be a positive integer.", field="timeout_ms")
    if browser_kind is not BrowserType.CHROME:
        raise GPMIntegrationError(_FIREFOX)


def _valid_port(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 65535


def _websocket_is_usable(url: str) -> bool:
    if any(ord(char) <= 0x20 or ord(char) == 0x7F for char in url) or "#" in url:
        return False
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    return (
        parts.scheme == "ws"
        and parts.hostname in _LOOPBACK_HOSTS
        and parts.username is None
        and parts.password is None
        and "@" not in parts.netloc
        and not parts.fragment
        and port is not None
        and 1 <= port <= 65535
    )


def _endpoint(launch: StartResult) -> str:
    url = launch.websocket_debugging_url
    if url is not None:
        if not _websocket_is_usable(url):
            raise GPMIntegrationError(_BAD_ENDPOINT)
        return url
    if not _valid_port(launch.remote_debugging_port):
        raise GPMIntegrationError(_BAD_ENDPOINT)
    return f"http://127.0.0.1:{launch.remote_debugging_port}"


def _is_refused(error: Exception, timeout_type: type[Exception]) -> bool:
    return not isinstance(error, timeout_type) and _REFUSED_MARK in str(error)


def _close_quietly(browser: Any) -> None:
    try:
        browser.close()
    except Exception:
        return


async def _aclose_quietly(browser: Any) -> None:
    try:
        await browser.close()
    except Exception:
        return


class PlaywrightAttachment:
    """A CDP connection: the existing default context and a way to get its first page."""

    def __init__(self, browser: SyncBrowser, context: SyncContext) -> None:
        self.browser = browser
        self.context = context

    def get_or_create_page(self) -> SyncPage:
        """The context's first page, or a new page in that same context when it has none."""
        pages = self.context.pages
        return pages[0] if pages else self.context.new_page()


class AsyncPlaywrightAttachment:
    def __init__(self, browser: AsyncBrowser, context: AsyncContext) -> None:
        self.browser = browser
        self.context = context

    async def get_or_create_page(self) -> AsyncPage:
        """The context's first page, or a new page in that same context when it has none."""
        pages = self.context.pages
        return pages[0] if pages else await self.context.new_page()


class _SyncAttachmentContext:
    def __init__(
        self, playwright: SyncPlaywright, endpoint: str, timeout_ms: int, error_types: ErrorTypes
    ) -> None:
        self._playwright = playwright
        self._endpoint = endpoint
        self._timeout_ms = timeout_ms
        self._error_type, self._timeout_type = error_types
        self._used = False
        self._browser: SyncBrowser | None = None

    def _connect(self) -> SyncBrowser:
        deadline = _monotonic() + self._timeout_ms / 1000
        while True:
            remaining = deadline - _monotonic()
            if remaining <= 0:
                break
            try:
                return self._playwright.chromium.connect_over_cdp(
                    self._endpoint, timeout=remaining * 1000
                )
            except self._error_type as error:
                refused = _is_refused(error, self._timeout_type)
            if not refused:
                raise GPMIntegrationError(_FAILED)
            left = deadline - _monotonic()
            if left <= 0:
                break
            _sleep(min(RETRY_INTERVAL_SECONDS, left))
        raise GPMIntegrationError(_UNREACHABLE)

    def __enter__(self) -> PlaywrightAttachment:
        if self._used:
            raise GPMIntegrationError(_REUSED)
        self._used = True
        browser = self._connect()
        contexts = list(browser.contexts)
        if not contexts:
            _close_quietly(browser)
            raise GPMIntegrationError(_NO_CONTEXT)
        self._browser = browser
        return PlaywrightAttachment(browser, contexts[0])

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        browser, self._browser = self._browser, None
        if browser is None:
            return
        failed = False
        try:
            browser.close()
        except Exception:
            failed = True
        if not failed:
            return
        if exc is None:
            raise GPMIntegrationError(_DETACH_FAILED)
        exc.add_note(_DETACH_NOTE)


class _AsyncAttachmentContext:
    def __init__(
        self, playwright: AsyncPlaywright, endpoint: str, timeout_ms: int, error_types: ErrorTypes
    ) -> None:
        self._playwright = playwright
        self._endpoint = endpoint
        self._timeout_ms = timeout_ms
        self._error_type, self._timeout_type = error_types
        self._used = False
        self._browser: AsyncBrowser | None = None

    async def _connect(self) -> AsyncBrowser:
        deadline = _monotonic() + self._timeout_ms / 1000
        while True:
            remaining = deadline - _monotonic()
            if remaining <= 0:
                break
            try:
                return await self._playwright.chromium.connect_over_cdp(
                    self._endpoint, timeout=remaining * 1000
                )
            except self._error_type as error:
                refused = _is_refused(error, self._timeout_type)
            if not refused:
                raise GPMIntegrationError(_FAILED)
            left = deadline - _monotonic()
            if left <= 0:
                break
            await _async_sleep(min(RETRY_INTERVAL_SECONDS, left))
        raise GPMIntegrationError(_UNREACHABLE)

    async def __aenter__(self) -> AsyncPlaywrightAttachment:
        if self._used:
            raise GPMIntegrationError(_REUSED)
        self._used = True
        browser = await self._connect()
        contexts = list(browser.contexts)
        if not contexts:
            await _aclose_quietly(browser)
            raise GPMIntegrationError(_NO_CONTEXT)
        self._browser = browser
        return AsyncPlaywrightAttachment(browser, contexts[0])

    async def _detach(self, browser: AsyncBrowser) -> GPMIntegrationError | None:
        try:
            await browser.close()
        except Exception:
            return GPMIntegrationError(_DETACH_FAILED)
        return None

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        browser, self._browser = self._browser, None
        if browser is None:
            return
        error, cancelled = await run_bounded_cleanup(
            self._detach(browser),
            failure=lambda: GPMIntegrationError(_DETACH_FAILED),
            timeout=DETACH_TIMEOUT_SECONDS,
        )
        if cancelled:
            if isinstance(exc, asyncio.CancelledError):
                if error is not None:
                    exc.add_note(_DETACH_NOTE)
                return
            cancellation = asyncio.CancelledError()
            if error is not None:
                cancellation.add_note(_DETACH_NOTE)
            raise cancellation
        if error is None:
            return
        if exc is None:
            raise error
        exc.add_note(_DETACH_NOTE)


def connect(
    launch: StartResult,
    playwright: SyncPlaywright,
    *,
    browser_kind: BrowserType,
    timeout_ms: int = 10000,
) -> _SyncAttachmentContext:
    """Attach ``playwright.chromium`` to the launched profile; detach with ``browser.close()``.

    The connection is made when the ``with`` block is entered, retrying only while the debugging
    port refuses connections, within ``timeout_ms`` in total. Every other failure is raised at
    once as :class:`GPMIntegrationError`. The existing default context and page are reused; no
    new context is ever created.
    """
    _check_inputs(launch, browser_kind, timeout_ms)
    error_types = _playwright_error_types(use_async=False)
    return _SyncAttachmentContext(playwright, _endpoint(launch), timeout_ms, error_types)


def connect_async(
    launch: StartResult,
    playwright: AsyncPlaywright,
    *,
    browser_kind: BrowserType,
    timeout_ms: int = 10000,
) -> _AsyncAttachmentContext:
    """Async twin of :func:`connect`; detach is bounded to 10 seconds and survives cancellation."""
    _check_inputs(launch, browser_kind, timeout_ms)
    error_types = _playwright_error_types(use_async=True)
    return _AsyncAttachmentContext(playwright, _endpoint(launch), timeout_ms, error_types)
