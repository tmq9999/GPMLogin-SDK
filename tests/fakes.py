"""Fake Playwright objects exposing only the public surface the adapter uses."""

from __future__ import annotations

from typing import Any


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    async def async_sleep(self, seconds: float) -> None:
        self.sleep(seconds)


def install_clock(monkeypatch: Any, adapter: Any) -> FakeClock:
    clock = FakeClock()
    monkeypatch.setattr(adapter, "_monotonic", clock.monotonic)
    monkeypatch.setattr(adapter, "_sleep", clock.sleep)
    monkeypatch.setattr(adapter, "_async_sleep", clock.async_sleep)
    return clock


class FakePage:
    pass


class FakeContext:
    def __init__(self, pages: list[FakePage] | None = None) -> None:
        self.pages = list(pages or [])
        self.new_page_calls = 0

    def _new_page(self) -> FakePage:
        self.new_page_calls += 1
        page = FakePage()
        self.pages.append(page)
        return page

    def new_page(self) -> FakePage:
        return self._new_page()


class AsyncFakeContext(FakeContext):
    async def new_page(self) -> FakePage:  # type: ignore[override]
        return self._new_page()


class FakeBrowser:
    """No ``new_context``: the adapter must never create a context."""

    def __init__(
        self,
        contexts: list[Any],
        events: list[str],
        close_error: BaseException | None = None,
    ) -> None:
        self.contexts = contexts
        self.events = events
        self.close_error = close_error
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1
        self.events.append("detach")
        if self.close_error is not None:
            raise self.close_error


class AsyncFakeBrowser(FakeBrowser):
    async def close(self) -> None:  # type: ignore[override]
        FakeBrowser.close(self)


class FakeChromium:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[tuple[str, float | None]] = []

    def _next(self, endpoint_url: str, timeout: float | None) -> Any:
        self.calls.append((endpoint_url, timeout))
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def connect_over_cdp(self, endpoint_url: str, *, timeout: float | None = None) -> Any:
        return self._next(endpoint_url, timeout)


class AsyncFakeChromium(FakeChromium):
    async def connect_over_cdp(  # type: ignore[override]
        self,
        endpoint_url: str,
        *,
        timeout: float | None = None,  # noqa: ASYNC109
    ) -> Any:
        return self._next(endpoint_url, timeout)


class _ForbiddenBrowserType:
    def connect_over_cdp(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("only Chromium may be used")


class FakePlaywright:
    def __init__(self, outcomes: list[Any], *, is_async: bool = False) -> None:
        self.chromium = AsyncFakeChromium(outcomes) if is_async else FakeChromium(outcomes)
        self.firefox = _ForbiddenBrowserType()
        self.webkit = _ForbiddenBrowserType()
        self.stop_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1


def make_world(
    mode: str,
    *,
    pages: int = 1,
    has_context: bool = True,
    close_error: BaseException | None = None,
    events: list[str] | None = None,
) -> tuple[FakePlaywright, Any, Any, list[str]]:
    """Fake Playwright with one browser; returns (pw, browser, context, events)."""
    recorded = events if events is not None else []
    is_async = mode == "async"
    context = (AsyncFakeContext if is_async else FakeContext)([FakePage() for _ in range(pages)])
    browser_type = AsyncFakeBrowser if is_async else FakeBrowser
    browser = browser_type([context] if has_context else [], recorded, close_error)
    return FakePlaywright([browser], is_async=is_async), browser, context, recorded
