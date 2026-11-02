"""Browser versions resource (1 endpoint)."""

from __future__ import annotations

from .._async_transport import AsyncTransport
from .._operations import Operation
from .._transport import Transport
from ..models import BrowserVersions, parse_versions


def _versions_operation() -> Operation[BrowserVersions]:
    return Operation("browsers.versions", "GET", "/browsers/versions", False, parse_versions)


class BrowsersResource:
    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def versions(self) -> BrowserVersions:
        """Browser versions installed in GPM Login (``chromium`` is the Chrome profile type)."""
        return self._transport.request(_versions_operation())


class AsyncBrowsersResource:
    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def versions(self) -> BrowserVersions:
        """Browser versions installed in GPM Login (``chromium`` is the Chrome profile type)."""
        return await self._transport.request(_versions_operation())
