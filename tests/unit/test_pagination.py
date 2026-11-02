from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from gpmlogin_sdk import GPMProtocolError, Page
from gpmlogin_sdk.helpers.pagination import iterate_pages, iterate_pages_async


def make_page(number: int, ids: list[str], last_page: int) -> Page[Any]:
    return Page(
        current_page=number,
        per_page=2,
        total=99,
        last_page=last_page,
        data=[SimpleNamespace(id=item) for item in ids],
    )


class Server:
    def __init__(self, pages: dict[int, Page[Any]]) -> None:
        self.pages = pages
        self.fetched: list[int] = []

    def fetch(self, number: int) -> Page[Any]:
        self.fetched.append(number)
        return self.pages[number]

    async def fetch_async(self, number: int) -> Page[Any]:
        return self.fetch(number)


THREE_PAGES = {
    1: make_page(1, ["p1"], 3),
    2: make_page(2, ["p2"], 3),
    3: make_page(3, ["p3"], 3),
}


def test_iterator_is_lazy_and_fetches_one_page_at_a_time() -> None:
    server = Server(dict(THREE_PAGES))
    items = iterate_pages(server.fetch)
    assert server.fetched == []
    assert next(items).id == "p1"
    assert server.fetched == [1]
    assert [p.id for p in items] == ["p2", "p3"]
    assert server.fetched == [1, 2, 3]


def test_breaking_early_does_not_load_the_rest() -> None:
    server = Server(dict(THREE_PAGES))
    for item in iterate_pages(server.fetch):
        assert item.id == "p1"
        break
    assert server.fetched == [1]


def test_stops_at_last_page_without_asking_for_another() -> None:
    server = Server({1: make_page(1, ["a"], 1)})
    assert [p.id for p in iterate_pages(server.fetch)] == ["a"]
    assert server.fetched == [1]


def test_stops_on_an_empty_page_even_if_last_page_promises_more() -> None:
    server = Server({1: make_page(1, ["a"], 5), 2: make_page(2, [], 5)})
    assert [p.id for p in iterate_pages(server.fetch)] == ["a"]
    assert server.fetched == [1, 2]


def test_empty_collection_yields_nothing_after_one_request() -> None:
    server = Server({1: make_page(1, [], 0)})
    assert list(iterate_pages(server.fetch)) == []
    assert server.fetched == [1]


def test_server_repeating_a_page_number_is_a_protocol_error_after_two_calls() -> None:
    server = Server({1: make_page(1, ["a"], 9), 2: make_page(1, ["a"], 9)})
    items = iterate_pages(server.fetch, operation="profiles.iter_all")
    assert next(items).id == "a"
    with pytest.raises(GPMProtocolError) as caught:
        next(items)
    assert server.fetched == [1, 2]
    assert caught.value.operation == "profiles.iter_all"


def test_wrong_first_page_number_is_a_protocol_error_before_any_item() -> None:
    server = Server({1: make_page(2, ["x"], 3)})
    with pytest.raises(GPMProtocolError):
        list(iterate_pages(server.fetch))


def test_last_page_may_change_and_new_metadata_wins() -> None:
    server = Server(
        {1: make_page(1, ["a"], 2), 2: make_page(2, ["b"], 3), 3: make_page(3, ["c"], 3)}
    )
    assert [p.id for p in iterate_pages(server.fetch)] == ["a", "b", "c"]
    assert server.fetched == [1, 2, 3]


def test_a_server_that_never_ends_cannot_hang_a_consumer_that_breaks() -> None:
    calls = 0

    def endless(number: int) -> Page[Any]:
        nonlocal calls
        calls += 1
        return make_page(number, [f"i{number}"], number + 1)

    for count, _ in enumerate(iterate_pages(endless), start=1):
        if count == 5:
            break
    assert calls == 5


@pytest.mark.asyncio
async def test_async_iterator_is_lazy_and_returned_without_awaiting() -> None:
    server = Server(dict(THREE_PAGES))
    items = iterate_pages_async(server.fetch_async)
    assert server.fetched == []
    seen = [item.id async for item in items]
    assert seen == ["p1", "p2", "p3"]
    assert server.fetched == [1, 2, 3]


@pytest.mark.asyncio
async def test_async_break_stops_fetching() -> None:
    server = Server(dict(THREE_PAGES))
    items = iterate_pages_async(server.fetch_async)
    async for item in items:
        assert item.id == "p1"
        break
    await items.aclose()
    assert server.fetched == [1]


@pytest.mark.asyncio
async def test_async_repeated_page_is_a_protocol_error() -> None:
    server = Server({1: make_page(1, ["a"], 9), 2: make_page(1, ["a"], 9)})
    with pytest.raises(GPMProtocolError):
        async for _ in iterate_pages_async(server.fetch_async):
            pass
    assert server.fetched == [1, 2]


@pytest.mark.asyncio
async def test_async_cancellation_propagates_out_of_the_iterator() -> None:
    gate = asyncio.Event()

    async def slow(number: int) -> Page[Any]:
        await gate.wait()
        return make_page(number, ["a"], 1)

    async def consume() -> None:
        async for _ in iterate_pages_async(slow):
            pass

    task = asyncio.ensure_future(consume())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
