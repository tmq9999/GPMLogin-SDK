from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from gpmlogin_sdk import GPMAmbiguousMatchError, GPMProtocolError, GPMValidationError
from tests.conftest import Api, json_response

ITEM_FACTORIES: dict[str, Callable[[str, str], dict[str, Any]]] = {
    "profiles": lambda id_, name: {"id": id_, "name": name},
    "groups": lambda id_, name: {"id": id_, "name": name, "sort_order": 1},
    "proxies": lambda id_, name: {"id": id_, "raw_proxy": name},
}
NAMED = ["profiles", "groups"]


class PagedServer:
    """Serves ``items`` in pages like GPM does, ignoring ``search`` (the SDK must filter)."""

    def __init__(self, items: list[dict[str, Any]], *, lie_about_page: bool = False) -> None:
        self.items = items
        self.lie_about_page = lie_about_page

    def __call__(self, request: httpx.Request) -> httpx.Response:
        params = request.url.params
        page = int(params["page"])
        size = int(params["page_size"])
        chunk = self.items[(page - 1) * size : page * size]
        last = max(1, -(-len(self.items) // size)) if self.items else 0
        payload = {
            "current_page": 1 if self.lie_about_page else page,
            "per_page": size,
            "total": len(self.items),
            "last_page": last,
            "data": chunk,
        }
        return json_response(payload)


def items_for(kind: str, names: list[str]) -> list[dict[str, Any]]:
    return [ITEM_FACTORIES[kind](f"id{i}", name) for i, name in enumerate(names)]


def drain(mode: str, iterator: Any) -> list[Any]:
    if mode == "sync":
        return list(iterator)

    async def collect() -> list[Any]:
        return [item async for item in iterator]

    return asyncio.run(collect())


@pytest.mark.parametrize("kind", ["profiles", "groups", "proxies"])
def test_iter_all_is_lazy_and_forwards_page_size_search_and_sort(
    api_factory: Callable[..., Api], mode: str, kind: str
) -> None:
    server = PagedServer(items_for(kind, ["a", "b", "c", "d", "e"]))
    api = api_factory(mode, server)
    iterator = api.call(f"{kind}.iter_all", page_size=2, search="needle", sort=3)
    assert api.requests == [], "creating the iterator performs no request"
    results = drain(mode, iterator)
    assert len(results) == 5
    assert [int(r.url.params["page"]) for r in api.requests] == [1, 2, 3]
    for request in api.requests:
        assert dict(request.url.params) | {"page": "x"} == {
            "page": "x",
            "page_size": "2",
            "search": "needle",
            "sort": "3",
        }


@pytest.mark.parametrize("kind", ["profiles", "groups", "proxies"])
def test_iter_all_validates_arguments_before_any_request(
    api_factory: Callable[..., Api], mode: str, kind: str
) -> None:
    api = api_factory(mode, PagedServer([]))
    for kwargs in ({"page_size": 0}, {"page_size": True}, {"sort": 7}, {"search": 1}):
        with pytest.raises(GPMValidationError):
            api.call(f"{kind}.iter_all", **kwargs)
    assert api.requests == []


@pytest.mark.parametrize("kind", ["profiles", "groups", "proxies"])
def test_lying_server_cannot_cause_an_endless_loop(
    api_factory: Callable[..., Api], mode: str, kind: str
) -> None:
    server = PagedServer(items_for(kind, ["a", "b", "c", "d"]), lie_about_page=True)
    api = api_factory(mode, server)
    iterator = api.call(f"{kind}.iter_all", page_size=2)
    with pytest.raises(GPMProtocolError):
        drain(mode, iterator)
    assert len(api.requests) == 2


@pytest.mark.parametrize("kind", NAMED)
def test_find_by_name_returns_none_for_no_exact_match(
    api_factory: Callable[..., Api], mode: str, kind: str
) -> None:
    api = api_factory(mode, PagedServer(items_for(kind, ["Alpha", "alphabet", "Alph"])))
    assert api.call(f"{kind}.find_by_name", "alpha") is None
    assert api.call(f"{kind}.find_by_name", "Alp") is None


@pytest.mark.parametrize("kind", NAMED)
def test_find_by_name_is_case_sensitive_and_forwards_search(
    api_factory: Callable[..., Api], mode: str, kind: str
) -> None:
    api = api_factory(mode, PagedServer(items_for(kind, ["Alpha", "alpha"])))
    found = api.call(f"{kind}.find_by_name", "alpha")
    assert found is not None and found.id == "id1"
    assert api.requests[0].url.params["search"] == "alpha"


@pytest.mark.parametrize("kind", NAMED)
def test_find_by_name_scans_every_page_before_returning_a_unique_match(
    api_factory: Callable[..., Api], mode: str, kind: str
) -> None:
    names = [f"n{i}" for i in range(95)] + ["target"] + [f"m{i}" for i in range(4)]
    api = api_factory(mode, PagedServer(items_for(kind, names)))
    found = api.call(f"{kind}.find_by_name", "target")
    assert found is not None and found.name == "target"
    assert [int(r.url.params["page"]) for r in api.requests] == [1, 2, 3, 4]


@pytest.mark.parametrize("kind", NAMED)
def test_duplicate_name_on_a_later_page_is_ambiguous(
    api_factory: Callable[..., Api], mode: str, kind: str
) -> None:
    names = ["dup"] + [f"n{i}" for i in range(60)] + ["dup"]
    api = api_factory(mode, PagedServer(items_for(kind, names)))
    with pytest.raises(GPMAmbiguousMatchError) as caught:
        api.call(f"{kind}.find_by_name", "dup")
    assert "dup" not in str(caught.value)
    assert len(api.requests) == 3


@pytest.mark.parametrize("kind", NAMED)
def test_same_entity_repeated_across_pages_is_not_ambiguous(
    api_factory: Callable[..., Api], mode: str, kind: str
) -> None:
    repeated = ITEM_FACTORIES[kind]("same", "dup")
    items = [repeated] + [ITEM_FACTORIES[kind](f"i{n}", f"n{n}") for n in range(40)] + [repeated]
    api = api_factory(mode, PagedServer(items))
    found = api.call(f"{kind}.find_by_name", "dup")
    assert found is not None and found.id == "same"


@pytest.mark.parametrize("kind", NAMED)
@pytest.mark.parametrize("name", ["", "   ", None, 5])
def test_find_by_name_rejects_blank_names_before_any_request(
    api_factory: Callable[..., Api], mode: str, kind: str, name: Any
) -> None:
    api = api_factory(mode, PagedServer([]))
    with pytest.raises(GPMValidationError):
        api.call(f"{kind}.find_by_name", name)
    assert api.requests == []


@pytest.mark.parametrize("kind", NAMED)
def test_find_by_name_with_a_lying_server_raises_protocol_error(
    api_factory: Callable[..., Api], mode: str, kind: str
) -> None:
    server = PagedServer(items_for(kind, [f"n{i}" for i in range(70)]), lie_about_page=True)
    api = api_factory(mode, server)
    with pytest.raises(GPMProtocolError):
        api.call(f"{kind}.find_by_name", "zzz")
    assert len(api.requests) == 2


def test_find_by_name_surfaces_server_errors_unchanged(
    api_factory: Callable[..., Api], mode: str
) -> None:
    api = api_factory(mode, lambda request: httpx.Response(500))
    with pytest.raises(Exception) as caught:
        api.call("profiles.find_by_name", "x")
    assert type(caught.value).__name__ == "GPMHTTPError"
    assert len(api.requests) == 1
