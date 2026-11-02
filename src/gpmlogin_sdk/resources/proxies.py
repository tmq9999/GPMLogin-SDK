"""Shared proxy store resource (5 endpoints). Not a link to a profile's own ``raw_proxy``."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

from .._async_transport import AsyncTransport
from .._operations import Operation, parse_none
from .._serialization import encode_id
from .._transport import Transport
from ..enums import SortOrder
from ..helpers.pagination import (
    iterate_pages,
    iterate_pages_async,
)
from ..models import Page, Proxy, parse_page, parse_proxy
from ._common import Call, non_blank_text, page_query, require_confirm


def _parse_proxy_page(value: object) -> Page[Proxy]:
    return parse_page(value, parse_proxy)


def list_call(*, page: int, page_size: int, search: str | None, sort: int) -> Call[Page[Proxy]]:
    query = page_query(page=page, page_size=page_size, search=search, sort=sort)
    return Call(Operation("proxies.list", "GET", "/proxies", False, _parse_proxy_page), query)


def get_call(proxy_id: str) -> Call[Proxy]:
    path = f"/proxies/{encode_id(proxy_id)}"
    return Call(Operation("proxies.get", "GET", path, False, parse_proxy))


def create_call(raw_proxy: str) -> Call[Proxy]:
    body: dict[str, object] = {"raw_proxy": non_blank_text(raw_proxy, "raw_proxy")}
    operation = Operation("proxies.create", "POST", "/proxies/create", True, parse_proxy)
    return Call(operation, body=body)


def update_call(proxy_id: str, raw_proxy: str) -> Call[Proxy]:
    path = f"/proxies/update/{encode_id(proxy_id)}"
    body: dict[str, object] = {"raw_proxy": non_blank_text(raw_proxy, "raw_proxy")}
    return Call(Operation("proxies.update", "POST", path, True, parse_proxy), body=body)


def delete_call(proxy_id: str, confirm: object) -> Call[None]:
    path = f"/proxies/delete/{encode_id(proxy_id)}"
    require_confirm(confirm, "a proxy (shared resource)")
    return Call(Operation("proxies.delete", "GET", path, True, parse_none))


class ProxiesResource:
    """Responses contain credentials; models keep ``raw_proxy`` out of ``repr``."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def list(
        self,
        *,
        page: int = 1,
        page_size: int = 30,
        search: str | None = None,
        sort: SortOrder = SortOrder.NEWEST,
    ) -> Page[Proxy]:
        call = list_call(page=page, page_size=page_size, search=search, sort=sort)
        return self._transport.request(call.operation, query=call.query)

    def get(self, proxy_id: str) -> Proxy:
        return self._transport.request(get_call(proxy_id).operation)

    def create(self, raw_proxy: str) -> Proxy:
        call = create_call(raw_proxy)
        return self._transport.request(call.operation, body=call.body)

    def update(self, proxy_id: str, raw_proxy: str) -> Proxy:
        call = update_call(proxy_id, raw_proxy)
        return self._transport.request(call.operation, body=call.body)

    def delete(self, proxy_id: str, *, confirm: bool = False) -> None:
        """Delete a shared proxy. Requires ``confirm=True``."""
        self._transport.request(delete_call(proxy_id, confirm).operation)

    def iter_all(
        self, *, page_size: int = 30, search: str | None = None, sort: SortOrder = SortOrder.NEWEST
    ) -> Iterator[Proxy]:
        """Lazily iterate every proxies page by page: one request per page, only when needed."""
        page_query(page=1, page_size=page_size, search=search, sort=sort)
        return iterate_pages(
            lambda number: self.list(page=number, page_size=page_size, search=search, sort=sort),
            operation="proxies.iter_all",
        )


class AsyncProxiesResource:
    """Responses contain credentials; models keep ``raw_proxy`` out of ``repr``."""

    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def list(
        self,
        *,
        page: int = 1,
        page_size: int = 30,
        search: str | None = None,
        sort: SortOrder = SortOrder.NEWEST,
    ) -> Page[Proxy]:
        call = list_call(page=page, page_size=page_size, search=search, sort=sort)
        return await self._transport.request(call.operation, query=call.query)

    async def get(self, proxy_id: str) -> Proxy:
        return await self._transport.request(get_call(proxy_id).operation)

    async def create(self, raw_proxy: str) -> Proxy:
        call = create_call(raw_proxy)
        return await self._transport.request(call.operation, body=call.body)

    async def update(self, proxy_id: str, raw_proxy: str) -> Proxy:
        call = update_call(proxy_id, raw_proxy)
        return await self._transport.request(call.operation, body=call.body)

    async def delete(self, proxy_id: str, *, confirm: bool = False) -> None:
        """Delete a shared proxy. Requires ``confirm=True``."""
        await self._transport.request(delete_call(proxy_id, confirm).operation)

    def iter_all(
        self, *, page_size: int = 30, search: str | None = None, sort: SortOrder = SortOrder.NEWEST
    ) -> AsyncIterator[Proxy]:
        """Lazily iterate every proxies page by page. Use ``async for``; do not ``await`` it."""
        page_query(page=1, page_size=page_size, search=search, sort=sort)
        return iterate_pages_async(
            lambda number: self.list(page=number, page_size=page_size, search=search, sort=sort),
            operation="proxies.iter_all",
        )
