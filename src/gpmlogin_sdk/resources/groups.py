"""Groups resource (5 endpoints)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

from .._async_transport import AsyncTransport
from .._operations import Operation, parse_none
from .._serialization import encode_id
from .._transport import Transport
from ..enums import SortOrder
from ..errors import GPMValidationError
from ..helpers.pagination import (
    find_unique,
    find_unique_async,
    iterate_pages,
    iterate_pages_async,
)
from ..models import Group, Page, parse_group, parse_page
from ._common import Call, non_blank_text, optional_int, page_query, require_confirm


def _parse_group_page(value: object) -> Page[Group]:
    return parse_page(value, parse_group)


def list_call(*, page: int, page_size: int, search: str | None, sort: int) -> Call[Page[Group]]:
    query = page_query(page=page, page_size=page_size, search=search, sort=sort)
    return Call(Operation("groups.list", "GET", "/groups", False, _parse_group_page), query)


def get_call(group_id: str) -> Call[Group]:
    path = f"/groups/{encode_id(group_id)}"
    return Call(Operation("groups.get", "GET", path, False, parse_group))


def create_call(name: str, sort_order: int) -> Call[Group]:
    order = optional_int(sort_order, "sort_order")
    if order is None:
        raise GPMValidationError("Invalid value for 'sort_order'.", field="sort_order")
    body: dict[str, object] = {"name": non_blank_text(name, "name"), "sort_order": order}
    return Call(Operation("groups.create", "POST", "/groups/create", True, parse_group), body=body)


def update_call(group_id: str, name: str, sort_order: int | None) -> Call[Group]:
    path = f"/groups/update/{encode_id(group_id)}"
    body: dict[str, object] = {"name": non_blank_text(name, "name")}
    order = optional_int(sort_order, "sort_order")
    if order is not None:
        body["sort_order"] = order
    return Call(Operation("groups.update", "POST", path, True, parse_group), body=body)


def delete_call(group_id: str, confirm: object) -> Call[None]:
    path = f"/groups/delete/{encode_id(group_id)}"
    require_confirm(confirm, "a group (shared resource)")
    return Call(Operation("groups.delete", "GET", path, True, parse_none))


class GroupsResource:
    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def list(
        self,
        *,
        page: int = 1,
        page_size: int = 30,
        search: str | None = None,
        sort: SortOrder = SortOrder.NEWEST,
    ) -> Page[Group]:
        call = list_call(page=page, page_size=page_size, search=search, sort=sort)
        return self._transport.request(call.operation, query=call.query)

    def get(self, group_id: str) -> Group:
        return self._transport.request(get_call(group_id).operation)

    def create(self, name: str, *, sort_order: int = 0) -> Group:
        call = create_call(name, sort_order)
        return self._transport.request(call.operation, body=call.body)

    def update(self, group_id: str, *, name: str, sort_order: int | None = None) -> Group:
        """Vendor note: ``sort_order`` only takes effect above 0 on update; 0 is still sent."""
        call = update_call(group_id, name, sort_order)
        return self._transport.request(call.operation, body=call.body)

    def delete(self, group_id: str, *, confirm: bool = False) -> None:
        """Delete a shared group. Requires ``confirm=True``."""
        self._transport.request(delete_call(group_id, confirm).operation)

    def iter_all(
        self, *, page_size: int = 30, search: str | None = None, sort: SortOrder = SortOrder.NEWEST
    ) -> Iterator[Group]:
        """Lazily iterate every groups page by page: one request per page, only when needed."""
        page_query(page=1, page_size=page_size, search=search, sort=sort)
        return iterate_pages(
            lambda number: self.list(page=number, page_size=page_size, search=search, sort=sort),
            operation="groups.iter_all",
        )

    def find_by_name(self, name: str) -> Group | None:
        """The group whose name equals ``name`` exactly (case-sensitive), else None.

        Scans every page of the server-side search results and raises
        ``GPMAmbiguousMatchError`` if two different entities share the name.
        """
        wanted = non_blank_text(name, "name")
        return find_unique(self.iter_all(search=wanted), wanted)


class AsyncGroupsResource:
    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def list(
        self,
        *,
        page: int = 1,
        page_size: int = 30,
        search: str | None = None,
        sort: SortOrder = SortOrder.NEWEST,
    ) -> Page[Group]:
        call = list_call(page=page, page_size=page_size, search=search, sort=sort)
        return await self._transport.request(call.operation, query=call.query)

    async def get(self, group_id: str) -> Group:
        return await self._transport.request(get_call(group_id).operation)

    async def create(self, name: str, *, sort_order: int = 0) -> Group:
        call = create_call(name, sort_order)
        return await self._transport.request(call.operation, body=call.body)

    async def update(self, group_id: str, *, name: str, sort_order: int | None = None) -> Group:
        """Vendor note: ``sort_order`` only takes effect above 0 on update; 0 is still sent."""
        call = update_call(group_id, name, sort_order)
        return await self._transport.request(call.operation, body=call.body)

    async def delete(self, group_id: str, *, confirm: bool = False) -> None:
        """Delete a shared group. Requires ``confirm=True``."""
        await self._transport.request(delete_call(group_id, confirm).operation)

    def iter_all(
        self, *, page_size: int = 30, search: str | None = None, sort: SortOrder = SortOrder.NEWEST
    ) -> AsyncIterator[Group]:
        """Lazily iterate every groups page by page. Use ``async for``; do not ``await`` it."""
        page_query(page=1, page_size=page_size, search=search, sort=sort)
        return iterate_pages_async(
            lambda number: self.list(page=number, page_size=page_size, search=search, sort=sort),
            operation="groups.iter_all",
        )

    async def find_by_name(self, name: str) -> Group | None:
        """The group whose name equals ``name`` exactly (case-sensitive), else None.

        Scans every page of the server-side search results and raises
        ``GPMAmbiguousMatchError`` if two different entities share the name.
        """
        wanted = non_blank_text(name, "name")
        return await find_unique_async(self.iter_all(search=wanted), wanted)
