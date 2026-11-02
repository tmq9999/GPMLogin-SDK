"""Operation matrix: one table row per wire behaviour, run against sync and async clients."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from gpmlogin_sdk import (
    BrowserVersions,
    Group,
    Page,
    ProfileCreated,
    ProfileDetails,
    ProfileUpdated,
    Proxy,
    SortOrder,
    StartResult,
)
from tests.conftest import Api, json_response


@dataclass(frozen=True)
class Case:
    id: str
    api: str
    template: tuple[str, str]  # (method, path template relative to /api/v1) = one endpoint
    method: str
    raw_path: str  # expected raw path relative to /api/v1
    data: object  # envelope "data" returned by the mock server
    expect: Callable[[Any], bool]
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    query: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] | None = None


def run_case(api_factory: Callable[..., Api], mode: str, case: Case) -> tuple[Api, Any]:
    api = api_factory(mode, lambda request: json_response(case.data))
    result = api.call(case.api, *case.args, **case.kwargs)
    assert len(api.requests) == 1, f"{case.id}: expected exactly one HTTP request"
    request = api.requests[0]
    assert request.method == case.method
    assert request.url.raw_path.split(b"?")[0].decode() == "/api/v1" + case.raw_path
    assert dict(request.url.params) == case.query
    body = json.loads(request.content) if request.content else None
    assert body == case.body
    assert case.expect(result), f"{case.id}: unexpected typed result {result!r}"
    return api, result


PROFILE_PAGE = {
    "current_page": 1,
    "per_page": 30,
    "total": 1,
    "last_page": 1,
    "data": [{"id": "p1", "name": "Profile 01", "raw_proxy": "socks5://127.0.0.1:5000"}],
}
START_DATA = {
    "profile_id": "p1",
    "driver_path": "C:\\GPMLogin\\drivers\\chromedriver.exe",
    "remote_debugging_port": 40444,
    "websocket_debugging_url": "ws://127.0.0.1:40444/devtools/browser/abc-123",
    "addition_info": {"process_id": 12345},
}

PROFILE_CASES: list[Case] = [
    Case(
        id="profiles.list-defaults",
        api="profiles.list",
        template=("GET", "/profiles"),
        method="GET",
        raw_path="/profiles",
        query={"page": "1", "page_size": "30", "sort": "0"},
        data=PROFILE_PAGE,
        expect=lambda r: isinstance(r, Page) and [p.id for p in r.data] == ["p1"],
    ),
    Case(
        id="profiles.list-search-sort",
        api="profiles.list",
        template=("GET", "/profiles"),
        method="GET",
        raw_path="/profiles",
        kwargs={"page": 2, "page_size": 10, "search": "", "sort": SortOrder.NAME_DESC},
        query={"page": "2", "page_size": "10", "search": "", "sort": "3"},
        data=PROFILE_PAGE,
        expect=lambda r: r.total == 1,
    ),
    Case(
        id="profiles.get",
        api="profiles.get",
        template=("GET", "/profiles/{id}"),
        method="GET",
        raw_path="/profiles/p1",
        args=("p1",),
        data={"id": "p1", "name": "A", "fingerprint": {"opaque": [1]}},
        expect=lambda r: isinstance(r, ProfileDetails) and r.fingerprint == {"opaque": [1]},
    ),
    Case(
        id="profiles.get-reserved-characters-are-encoded",
        api="profiles.get",
        template=("GET", "/profiles/{id}"),
        method="GET",
        raw_path="/profiles/a%2Fb%20%3F",
        args=("a/b ?",),
        data={"id": "a/b ?", "name": "A"},
        expect=lambda r: r.id == "a/b ?",
    ),
    Case(
        id="profiles.create-name-only",
        api="profiles.create",
        template=("POST", "/profiles/create"),
        method="POST",
        raw_path="/profiles/create",
        args=({"name": "A"},),
        body={"name": "A"},
        data={"id": "p1", "name": "A"},
        expect=lambda r: isinstance(r, ProfileCreated) and r.id == "p1",
    ),
    Case(
        id="profiles.create-keeps-false-empty-and-null",
        api="profiles.create",
        template=("POST", "/profiles/create"),
        method="POST",
        raw_path="/profiles/create",
        args=(
            {
                "name": "A",
                "browser_type": 1,
                "is_masked_media": False,
                "raw_proxy": "",
                "note": None,
            },
        ),
        body={
            "name": "A",
            "browser_type": 1,
            "is_masked_media": False,
            "raw_proxy": "",
            "note": None,
        },
        data={"id": "p2", "name": "A"},
        expect=lambda r: r.id == "p2",
    ),
    Case(
        id="profiles.update-without-name-null-and-empty",
        api="profiles.update",
        template=("POST", "/profiles/update/{id}"),
        method="POST",
        raw_path="/profiles/update/p1",
        args=("p1", {"note": None, "raw_proxy": ""}),
        body={"note": None, "raw_proxy": ""},
        data=None,
        expect=lambda r: r == ProfileUpdated(data=None),
    ),
    Case(
        id="profiles.update-with-name-and-proxy",
        api="profiles.update",
        template=("POST", "/profiles/update/{id}"),
        method="POST",
        raw_path="/profiles/update/p1",
        args=("p1", {"name": "N", "raw_proxy": "socks5://127.0.0.1:5000"}),
        body={"name": "N", "raw_proxy": "socks5://127.0.0.1:5000"},
        data={"id": "p1"},
        expect=lambda r: r.data == {"id": "p1"},
    ),
    Case(
        id="profiles.soft_delete",
        api="profiles.soft_delete",
        template=("GET", "/profiles/delete/{id}"),
        method="GET",
        raw_path="/profiles/delete/p1",
        args=("p1",),
        query={"mode": "soft"},
        data=None,
        expect=lambda r: r is None,
    ),
    Case(
        id="profiles.hard_delete-confirmed",
        api="profiles.hard_delete",
        template=("GET", "/profiles/delete/{id}"),
        method="GET",
        raw_path="/profiles/delete/p1",
        args=("p1",),
        kwargs={"confirm": True},
        query={"mode": "hard"},
        data=None,
        expect=lambda r: r is None,
    ),
    Case(
        id="profiles.start-no-options",
        api="profiles.start",
        template=("GET", "/profiles/start/{id}"),
        method="GET",
        raw_path="/profiles/start/p1",
        args=("p1",),
        data=START_DATA,
        expect=lambda r: isinstance(r, StartResult) and r.profile_id == "p1",
    ),
    Case(
        id="profiles.start-options",
        api="profiles.start",
        template=("GET", "/profiles/start/{id}"),
        method="GET",
        raw_path="/profiles/start/p1",
        args=("p1", {"skip_proxy_check": False, "addition_args": "--mute-audio"}),
        query={"skip_proxy_check": "false", "addition_args": "--mute-audio"},
        data=START_DATA,
        expect=lambda r: r.remote_debugging_port == 40444,
    ),
    Case(
        id="profiles.stop",
        api="profiles.stop",
        template=("GET", "/profiles/stop/{id}"),
        method="GET",
        raw_path="/profiles/stop/p1",
        args=("p1",),
        data=None,
        expect=lambda r: r is None,
    ),
]

BROWSER_CASES: list[Case] = [
    Case(
        id="browsers.versions",
        api="browsers.versions",
        template=("GET", "/browsers/versions"),
        method="GET",
        raw_path="/browsers/versions",
        data={"chromium": ["137.0.7151.41"], "firefox": ["128.0"]},
        expect=lambda r: isinstance(r, BrowserVersions) and r.chromium == ["137.0.7151.41"],
    ),
]


GROUP_PAGE = {
    "current_page": 1,
    "per_page": 30,
    "total": 1,
    "last_page": 1,
    "data": [{"id": "g1", "name": "Marketing", "sort_order": 1}],
}
PROXY_PAGE = {
    "current_page": 1,
    "per_page": 30,
    "total": 1,
    "last_page": 1,
    "data": [{"id": "x1", "raw_proxy": "socks5://127.0.0.1:5001", "meta_data": None, "tags": []}],
}

GROUP_CASES: list[Case] = [
    Case(
        id="groups.list",
        api="groups.list",
        template=("GET", "/groups"),
        method="GET",
        raw_path="/groups",
        kwargs={"search": "Mark", "sort": SortOrder.NAME_ASC},
        query={"page": "1", "page_size": "30", "search": "Mark", "sort": "2"},
        data=GROUP_PAGE,
        expect=lambda r: isinstance(r, Page) and r.data == [Group("g1", "Marketing", 1)],
    ),
    Case(
        id="groups.get",
        api="groups.get",
        template=("GET", "/groups/{id}"),
        method="GET",
        raw_path="/groups/g1",
        args=("g1",),
        data={"id": "g1", "name": "Marketing", "sort_order": 1},
        expect=lambda r: r == Group("g1", "Marketing", 1),
    ),
    Case(
        id="groups.create-explicit-sort-order",
        api="groups.create",
        template=("POST", "/groups/create"),
        method="POST",
        raw_path="/groups/create",
        args=("Automation",),
        kwargs={"sort_order": 10},
        body={"name": "Automation", "sort_order": 10},
        data={"id": "g2", "name": "Automation", "sort_order": 10},
        expect=lambda r: r.id == "g2",
    ),
    Case(
        id="groups.create-default-sort-order-is-sent-as-zero",
        api="groups.create",
        template=("POST", "/groups/create"),
        method="POST",
        raw_path="/groups/create",
        args=("Automation",),
        body={"name": "Automation", "sort_order": 0},
        data={"id": "g2", "name": "Automation", "sort_order": 0},
        expect=lambda r: r.sort_order == 0,
    ),
    Case(
        id="groups.update-keeps-sort-order-zero",
        api="groups.update",
        template=("POST", "/groups/update/{id}"),
        method="POST",
        raw_path="/groups/update/g1",
        args=("g1",),
        kwargs={"name": "N", "sort_order": 0},
        body={"name": "N", "sort_order": 0},
        data={"id": "g1", "name": "N", "sort_order": 0},
        expect=lambda r: r.name == "N",
    ),
    Case(
        id="groups.update-omits-sort-order-when-none",
        api="groups.update",
        template=("POST", "/groups/update/{id}"),
        method="POST",
        raw_path="/groups/update/g1",
        args=("g1",),
        kwargs={"name": "N"},
        body={"name": "N"},
        data={"id": "g1", "name": "N", "sort_order": 3},
        expect=lambda r: r.sort_order == 3,
    ),
    Case(
        id="groups.delete-confirmed",
        api="groups.delete",
        template=("GET", "/groups/delete/{id}"),
        method="GET",
        raw_path="/groups/delete/g1",
        args=("g1",),
        kwargs={"confirm": True},
        data=None,
        expect=lambda r: r is None,
    ),
]

PROXY_CASES: list[Case] = [
    Case(
        id="proxies.list",
        api="proxies.list",
        template=("GET", "/proxies"),
        method="GET",
        raw_path="/proxies",
        query={"page": "1", "page_size": "30", "sort": "0"},
        data=PROXY_PAGE,
        expect=lambda r: isinstance(r, Page) and [p.id for p in r.data] == ["x1"],
    ),
    Case(
        id="proxies.get",
        api="proxies.get",
        template=("GET", "/proxies/{id}"),
        method="GET",
        raw_path="/proxies/x1",
        args=("x1",),
        data={"id": "x1", "raw_proxy": "ip:port"},
        expect=lambda r: isinstance(r, Proxy) and r.raw_proxy == "ip:port",
    ),
    Case(
        id="proxies.create",
        api="proxies.create",
        template=("POST", "/proxies/create"),
        method="POST",
        raw_path="/proxies/create",
        args=("socks5://127.0.0.1:5001",),
        body={"raw_proxy": "socks5://127.0.0.1:5001"},
        data={"id": "x2", "raw_proxy": "socks5://127.0.0.1:5001"},
        expect=lambda r: r.id == "x2",
    ),
    Case(
        id="proxies.update",
        api="proxies.update",
        template=("POST", "/proxies/update/{id}"),
        method="POST",
        raw_path="/proxies/update/x1",
        args=("x1", "http://u:p@h:8080"),
        body={"raw_proxy": "http://u:p@h:8080"},
        data={"id": "x1", "raw_proxy": "http://u:p@h:8080"},
        expect=lambda r: r.id == "x1",
    ),
    Case(
        id="proxies.delete-confirmed",
        api="proxies.delete",
        template=("GET", "/proxies/delete/{id}"),
        method="GET",
        raw_path="/proxies/delete/x1",
        args=("x1",),
        kwargs={"confirm": True},
        data=None,
        expect=lambda r: r is None,
    ),
]

EXTENSION_DATA = [{"id": "e1", "name": "uBlock Origin", "version": "1.54.0", "is_active": True}]

EXTENSION_CASES: list[Case] = [
    Case(
        id="extensions.list-returns-a-plain-array",
        api="extensions.list",
        template=("GET", "/extensions"),
        method="GET",
        raw_path="/extensions",
        data=EXTENSION_DATA,
        expect=lambda r: isinstance(r, list) and [e.id for e in r] == ["e1"],
    ),
    Case(
        id="extensions.set_state-global-scope",
        api="extensions.set_state",
        template=("GET", "/extensions/update-state/{id}"),
        method="GET",
        raw_path="/extensions/update-state/e1",
        args=("e1",),
        kwargs={"active": True},
        query={"active": "true"},
        data=None,
        expect=lambda r: r is None,
    ),
    Case(
        id="extensions.set_state-false-with-group-scope",
        api="extensions.set_state",
        template=("GET", "/extensions/update-state/{id}"),
        method="GET",
        raw_path="/extensions/update-state/e1",
        args=("e1",),
        kwargs={"active": False, "group_ids": ["g1", "g2"]},
        query={"active": "false", "applied_group_ids": "g1,g2"},
        data=None,
        expect=lambda r: r is None,
    ),
]

ALL_CASES: list[Case] = [
    *PROFILE_CASES,
    *BROWSER_CASES,
    *GROUP_CASES,
    *PROXY_CASES,
    *EXTENSION_CASES,
]

MUTATING_APIS = frozenset(
    {
        "profiles.create",
        "profiles.update",
        "profiles.soft_delete",
        "profiles.hard_delete",
        "profiles.start",
        "profiles.stop",
        "groups.create",
        "groups.update",
        "groups.delete",
        "proxies.create",
        "proxies.update",
        "proxies.delete",
        "extensions.set_state",
    }
)

DOCUMENTED_ENDPOINTS = frozenset(
    {
        ("GET", "/profiles"),
        ("GET", "/profiles/{id}"),
        ("POST", "/profiles/create"),
        ("POST", "/profiles/update/{id}"),
        ("GET", "/profiles/delete/{id}"),
        ("GET", "/profiles/start/{id}"),
        ("GET", "/profiles/stop/{id}"),
        ("GET", "/browsers/versions"),
        ("GET", "/groups"),
        ("GET", "/groups/{id}"),
        ("POST", "/groups/create"),
        ("POST", "/groups/update/{id}"),
        ("GET", "/groups/delete/{id}"),
        ("GET", "/proxies"),
        ("GET", "/proxies/{id}"),
        ("POST", "/proxies/create"),
        ("POST", "/proxies/update/{id}"),
        ("GET", "/proxies/delete/{id}"),
        ("GET", "/extensions"),
        ("GET", "/extensions/update-state/{id}"),
    }
)
