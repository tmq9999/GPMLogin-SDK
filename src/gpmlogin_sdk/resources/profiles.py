"""Profiles resource: 7 endpoints (delete has explicit soft and hard methods)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

from .._async_transport import AsyncTransport
from .._operations import Operation, parse_none
from .._serialization import encode_id
from .._transport import Transport
from .._validation import validate_create, validate_start, validate_update
from ..enums import SortOrder
from ..helpers.pagination import (
    find_unique,
    find_unique_async,
    iterate_pages,
    iterate_pages_async,
)
from ..models import (
    CreateProfileRequest,
    Page,
    ProfileCreated,
    ProfileDetails,
    ProfileSummary,
    ProfileUpdated,
    StartOptions,
    StartResult,
    UpdateProfileRequest,
    parse_page,
    parse_profile_created,
    parse_profile_details,
    parse_profile_summary,
    parse_profile_updated,
    parse_start,
)
from ._common import Call, non_blank_text, page_query, require_confirm


def _parse_summary_page(value: object) -> Page[ProfileSummary]:
    return parse_page(value, parse_profile_summary)


def list_call(
    *, page: int, page_size: int, search: str | None, sort: int
) -> Call[Page[ProfileSummary]]:
    query = page_query(page=page, page_size=page_size, search=search, sort=sort)
    return Call(Operation("profiles.list", "GET", "/profiles", False, _parse_summary_page), query)


def get_call(profile_id: str) -> Call[ProfileDetails]:
    path = f"/profiles/{encode_id(profile_id)}"
    return Call(Operation("profiles.get", "GET", path, False, parse_profile_details))


def create_call(body: CreateProfileRequest) -> Call[ProfileCreated]:
    validate_create(body)
    operation = Operation(
        "profiles.create", "POST", "/profiles/create", True, parse_profile_created
    )
    return Call(operation, body=dict(body))


def update_call(profile_id: str, body: UpdateProfileRequest) -> Call[ProfileUpdated]:
    path = f"/profiles/update/{encode_id(profile_id)}"
    validate_update(body)
    operation = Operation("profiles.update", "POST", path, True, parse_profile_updated)
    return Call(operation, body=dict(body))


def soft_delete_call(profile_id: str) -> Call[None]:
    path = f"/profiles/delete/{encode_id(profile_id)}"
    operation = Operation("profiles.soft_delete", "GET", path, True, parse_none)
    return Call(operation, {"mode": "soft"})


def hard_delete_call(profile_id: str, confirm: object) -> Call[None]:
    path = f"/profiles/delete/{encode_id(profile_id)}"
    require_confirm(confirm, "a profile permanently (hard delete)")
    operation = Operation("profiles.hard_delete", "GET", path, True, parse_none)
    return Call(operation, {"mode": "hard"})


def start_call(profile_id: str, options: StartOptions | None) -> Call[StartResult]:
    path = f"/profiles/start/{encode_id(profile_id)}"
    if options is not None:
        validate_start(options)
    operation = Operation("profiles.start", "GET", path, True, parse_start)
    return Call(operation, dict(options) if options else None)


def stop_call(profile_id: str) -> Call[None]:
    path = f"/profiles/stop/{encode_id(profile_id)}"
    return Call(Operation("profiles.stop", "GET", path, True, parse_none))


class ProfilesResource:
    """Blocking profile operations. Every call is one HTTP request; nothing is retried."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def list(
        self,
        *,
        page: int = 1,
        page_size: int = 30,
        search: str | None = None,
        sort: SortOrder = SortOrder.NEWEST,
    ) -> Page[ProfileSummary]:
        call = list_call(page=page, page_size=page_size, search=search, sort=sort)
        return self._transport.request(call.operation, query=call.query)

    def get(self, profile_id: str) -> ProfileDetails:
        return self._transport.request(get_call(profile_id).operation)

    def create(self, body: CreateProfileRequest) -> ProfileCreated:
        call = create_call(body)
        return self._transport.request(call.operation, body=call.body)

    def update(self, profile_id: str, body: UpdateProfileRequest) -> ProfileUpdated:
        call = update_call(profile_id, body)
        return self._transport.request(call.operation, body=call.body)

    def soft_delete(self, profile_id: str) -> None:
        call = soft_delete_call(profile_id)
        self._transport.request(call.operation, query=call.query)

    def hard_delete(self, profile_id: str, *, confirm: bool = False) -> None:
        """Permanently erase the profile and its on-disk data. Requires ``confirm=True``."""
        call = hard_delete_call(profile_id, confirm)
        self._transport.request(call.operation, query=call.query)

    def start(self, profile_id: str, options: StartOptions | None = None) -> StartResult:
        call = start_call(profile_id, options)
        return self._transport.request(call.operation, query=call.query)

    def stop(self, profile_id: str) -> None:
        self._transport.request(stop_call(profile_id).operation)

    def iter_all(
        self, *, page_size: int = 30, search: str | None = None, sort: SortOrder = SortOrder.NEWEST
    ) -> Iterator[ProfileSummary]:
        """Lazily iterate every profiles page by page: one request per page, only when needed."""
        page_query(page=1, page_size=page_size, search=search, sort=sort)
        return iterate_pages(
            lambda number: self.list(page=number, page_size=page_size, search=search, sort=sort),
            operation="profiles.iter_all",
        )

    def find_by_name(self, name: str) -> ProfileSummary | None:
        """The profile whose name equals ``name`` exactly (case-sensitive), else None.

        Scans every page of the server-side search results and raises
        ``GPMAmbiguousMatchError`` if two different entities share the name.
        """
        wanted = non_blank_text(name, "name")
        return find_unique(self.iter_all(search=wanted), wanted)

    def set_proxy(
        self, profile_id: str, raw_proxy: str, *, name: str | None = None
    ) -> ProfileUpdated:
        """Point the profile at ``raw_proxy`` by updating its own ``raw_proxy`` field.

        Without ``name`` this does one GET (to read the current name) and then one POST that
        resends it, because the vendor's update table marks ``name`` as required. This is
        best effort, not a transaction: if another caller renames the profile between the two
        requests (a race), the rename is overwritten. Pass ``name`` to skip the GET. Use
        :meth:`clear_proxy` to remove a proxy; an empty ``raw_proxy`` is rejected here.
        """
        encode_id(profile_id)
        proxy = non_blank_text(raw_proxy, "raw_proxy")
        explicit = None if name is None else non_blank_text(name, "name")
        resolved = explicit if explicit is not None else self.get(profile_id).name
        return self.update(profile_id, {"name": resolved, "raw_proxy": proxy})

    def clear_proxy(self, profile_id: str, *, name: str | None = None) -> ProfileUpdated:
        """Remove the profile's proxy by sending ``raw_proxy=""``.

        Same GET-then-POST behaviour and rename race as :meth:`set_proxy`; not a transaction.
        """
        encode_id(profile_id)
        explicit = None if name is None else non_blank_text(name, "name")
        resolved = explicit if explicit is not None else self.get(profile_id).name
        return self.update(profile_id, {"name": resolved, "raw_proxy": ""})


class AsyncProfilesResource:
    """Awaitable profile operations; same names, arguments and results as the blocking class."""

    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def list(
        self,
        *,
        page: int = 1,
        page_size: int = 30,
        search: str | None = None,
        sort: SortOrder = SortOrder.NEWEST,
    ) -> Page[ProfileSummary]:
        call = list_call(page=page, page_size=page_size, search=search, sort=sort)
        return await self._transport.request(call.operation, query=call.query)

    async def get(self, profile_id: str) -> ProfileDetails:
        return await self._transport.request(get_call(profile_id).operation)

    async def create(self, body: CreateProfileRequest) -> ProfileCreated:
        call = create_call(body)
        return await self._transport.request(call.operation, body=call.body)

    async def update(self, profile_id: str, body: UpdateProfileRequest) -> ProfileUpdated:
        call = update_call(profile_id, body)
        return await self._transport.request(call.operation, body=call.body)

    async def soft_delete(self, profile_id: str) -> None:
        call = soft_delete_call(profile_id)
        await self._transport.request(call.operation, query=call.query)

    async def hard_delete(self, profile_id: str, *, confirm: bool = False) -> None:
        """Permanently erase the profile and its on-disk data. Requires ``confirm=True``."""
        call = hard_delete_call(profile_id, confirm)
        await self._transport.request(call.operation, query=call.query)

    async def start(self, profile_id: str, options: StartOptions | None = None) -> StartResult:
        call = start_call(profile_id, options)
        return await self._transport.request(call.operation, query=call.query)

    async def stop(self, profile_id: str) -> None:
        await self._transport.request(stop_call(profile_id).operation)

    def iter_all(
        self, *, page_size: int = 30, search: str | None = None, sort: SortOrder = SortOrder.NEWEST
    ) -> AsyncIterator[ProfileSummary]:
        """Lazily iterate every profiles page by page. Use ``async for``; do not ``await`` it."""
        page_query(page=1, page_size=page_size, search=search, sort=sort)
        return iterate_pages_async(
            lambda number: self.list(page=number, page_size=page_size, search=search, sort=sort),
            operation="profiles.iter_all",
        )

    async def find_by_name(self, name: str) -> ProfileSummary | None:
        """The profile whose name equals ``name`` exactly (case-sensitive), else None.

        Scans every page of the server-side search results and raises
        ``GPMAmbiguousMatchError`` if two different entities share the name.
        """
        wanted = non_blank_text(name, "name")
        return await find_unique_async(self.iter_all(search=wanted), wanted)

    async def set_proxy(
        self, profile_id: str, raw_proxy: str, *, name: str | None = None
    ) -> ProfileUpdated:
        """Point the profile at ``raw_proxy`` by updating its own ``raw_proxy`` field.

        Without ``name`` this does one GET (to read the current name) and then one POST that
        resends it, because the vendor's update table marks ``name`` as required. This is
        best effort, not a transaction: if another caller renames the profile between the two
        requests (a race), the rename is overwritten. Pass ``name`` to skip the GET. Use
        :meth:`clear_proxy` to remove a proxy; an empty ``raw_proxy`` is rejected here.
        """
        encode_id(profile_id)
        proxy = non_blank_text(raw_proxy, "raw_proxy")
        explicit = None if name is None else non_blank_text(name, "name")
        resolved = explicit if explicit is not None else (await self.get(profile_id)).name
        return await self.update(profile_id, {"name": resolved, "raw_proxy": proxy})

    async def clear_proxy(self, profile_id: str, *, name: str | None = None) -> ProfileUpdated:
        """Remove the profile's proxy by sending ``raw_proxy=""``.

        Same GET-then-POST behaviour and rename race as :meth:`set_proxy`; not a transaction.
        """
        encode_id(profile_id)
        explicit = None if name is None else non_blank_text(name, "name")
        resolved = explicit if explicit is not None else (await self.get(profile_id)).name
        return await self.update(profile_id, {"name": resolved, "raw_proxy": ""})
