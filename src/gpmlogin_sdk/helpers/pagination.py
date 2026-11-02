"""Lazy pagination and exact-name lookup built on ``Page`` metadata. Pure: no I/O of its own."""

from __future__ import annotations

from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable, Iterable, Iterator
from typing import Any, Protocol, TypeVar

from ..errors import GPMAmbiguousMatchError, GPMProtocolError
from ..models import Page

T = TypeVar("T")


class _Named(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def name(self) -> str: ...


E = TypeVar("E", bound=_Named)


def _check_page(page: Page[Any], requested: int, operation: str) -> None:
    if page.current_page != requested:
        raise GPMProtocolError(operation)


def iterate_pages(fetch: Callable[[int], Page[T]], *, operation: str = "pagination") -> Iterator[T]:
    """Yield items page by page, fetching only when the consumer needs the next page.

    Stops after ``last_page`` or an empty page. A server that answers with a different page than
    requested is a protocol error, which also guarantees the loop cannot spin forever on a
    repeated page. There is no snapshot guarantee if the collection changes while iterating.
    """
    number = 1
    while True:
        page = fetch(number)
        _check_page(page, number, operation)
        yield from page.data
        if not page.data or number >= page.last_page:
            return
        number += 1


async def iterate_pages_async(
    fetch: Callable[[int], Awaitable[Page[T]]], *, operation: str = "pagination"
) -> AsyncIterator[T]:
    """Async twin of :func:`iterate_pages`; call it without ``await`` and use ``async for``."""
    number = 1
    while True:
        page = await fetch(number)
        _check_page(page, number, operation)
        for item in page.data:
            yield item
        if not page.data or number >= page.last_page:
            return
        number += 1


def find_unique(items: Iterable[E], name: str) -> E | None:
    """The single entity whose name equals ``name`` exactly (case-sensitive), else None.

    The same ID seen twice (a server repeating an entity) counts once; two different IDs with
    the same name raise :class:`GPMAmbiguousMatchError`.
    """
    found: E | None = None
    try:
        for item in items:
            if item.name != name:
                continue
            if found is None:
                found = item
            elif item.id != found.id:
                raise GPMAmbiguousMatchError
    finally:
        close = getattr(items, "close", None)
        if close is not None:
            close()
    return found


async def find_unique_async(items: AsyncIterable[E], name: str) -> E | None:
    found: E | None = None
    try:
        async for item in items:
            if item.name != name:
                continue
            if found is None:
                found = item
            elif item.id != found.id:
                raise GPMAmbiguousMatchError
    finally:
        aclose = getattr(items, "aclose", None)
        if aclose is not None:
            await aclose()
    return found
