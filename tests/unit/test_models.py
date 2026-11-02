from __future__ import annotations

from typing import Any

import pytest

from gpmlogin_sdk.errors import GPMProtocolError
from gpmlogin_sdk.models import (
    BrowserVersions,
    Extension,
    Group,
    Page,
    ProfileCreated,
    ProfileDetails,
    ProfileSummary,
    ProfileUpdated,
    Proxy,
    StartResult,
    parse_extension,
    parse_extensions,
    parse_group,
    parse_page,
    parse_profile_created,
    parse_profile_details,
    parse_profile_summary,
    parse_profile_updated,
    parse_proxy,
    parse_start,
    parse_versions,
)

SECRET = "SECRET"

SUMMARY = {
    "id": "37f783ac-2635-4d53-ab8d-a300c790ecdc",
    "name": "Profile 01",
    "group_id": "all",
    "storage_path": "C:\\GPMLogin\\profiles\\37f7",
    "raw_proxy": "socks5://127.0.0.1:5000",
    "browser": {"name": "chrome", "version": "137.0.7151.41"},
    "os": "windows",
    "note": "",
    "created_at": "2026-06-08 10:00:00",
    "updated_at": "2026-06-08 10:00:00",
    "tags": [],
}


def protocol_error(fn: Any, *args: Any) -> GPMProtocolError:
    with pytest.raises(GPMProtocolError) as caught:
        fn(*args)
    assert caught.value.success_confirmed is False
    return caught.value


def test_parse_profile_created_keeps_unknown_keys_in_extra() -> None:
    created = parse_profile_created({"id": "p1", "name": "A", "new": 7})
    assert isinstance(created, ProfileCreated)
    assert created.id == "p1" and created.name == "A"
    assert created.extra == {"new": 7}


def test_parse_profile_summary_full_and_minimal() -> None:
    summary = parse_profile_summary(SUMMARY)
    assert isinstance(summary, ProfileSummary)
    assert summary.id == SUMMARY["id"]
    assert summary.browser is not None and summary.browser.version == "137.0.7151.41"
    assert summary.tags == []
    assert summary.extra == {}
    minimal = parse_profile_summary({"id": "p", "name": "n"})
    assert minimal.raw_proxy is None and minimal.browser is None and minimal.tags is None


def test_parse_profile_details_adds_fingerprint_without_schema_checks() -> None:
    details = parse_profile_details({**SUMMARY, "fingerprint": {"anything": {"nested": [1]}}})
    assert isinstance(details, ProfileDetails)
    assert details.fingerprint == {"anything": {"nested": [1]}}
    assert parse_profile_details({"id": "p", "name": "n"}).fingerprint is None


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        "x",
        {"name": "n"},
        {"id": "p"},
        {"id": 1, "name": "n"},
        {"id": "", "name": "n"},
        {"id": "p", "name": None},
        {"id": "p", "name": "n", "tags": "x"},
        {"id": "p", "name": "n", "browser": "chrome"},
        {"id": "p", "name": "n", "raw_proxy": 5},
        {"id": "p", "name": "n", "browser": {"name": 5}},
    ],
)
def test_profile_parsers_reject_malformed_values(value: object) -> None:
    error = protocol_error(parse_profile_summary, value)
    assert str(error) and SECRET not in str(error)


def test_parse_profile_updated_accepts_null_or_object() -> None:
    assert parse_profile_updated(None) == ProfileUpdated(data=None)
    assert parse_profile_updated({"id": "p"}).data == {"id": "p"}
    protocol_error(parse_profile_updated, ["x"])


def test_parse_group() -> None:
    group = parse_group({"id": "g1", "name": "Marketing", "sort_order": 0, "extra_key": 1})
    assert group == Group(id="g1", name="Marketing", sort_order=0, extra={"extra_key": 1})
    for bad in (
        {"id": "g1", "name": "M"},
        {"id": "g1", "name": "M", "sort_order": True},
        {"id": "g1", "name": "M", "sort_order": "1"},
        {"id": "", "name": "M", "sort_order": 1},
    ):
        protocol_error(parse_group, bad)


def test_parse_proxy_optional_fields() -> None:
    proxy = parse_proxy({"id": "x1", "raw_proxy": "ip:port", "meta_data": None, "tags": []})
    assert isinstance(proxy, Proxy)
    assert proxy.meta_data is None and proxy.tags == []
    assert parse_proxy({"id": "x1", "raw_proxy": "ip:port"}).tags is None
    for bad in ({"id": "x1"}, {"id": "x1", "raw_proxy": 5}, {"raw_proxy": "a"}):
        protocol_error(parse_proxy, bad)


def test_parse_extension_requires_boolean_is_active() -> None:
    ext = parse_extension({"id": "e1", "name": "uBlock", "version": "1.0", "is_active": True})
    assert ext == Extension(id="e1", name="uBlock", version="1.0", is_active=True)
    for bad in (
        {"id": "e1", "name": "n", "version": "1", "is_active": "true"},
        {"id": "e1", "name": "n", "version": "1", "is_active": 1},
        {"id": "e1", "name": "n", "version": "1"},
        {"id": "e1", "name": "n", "is_active": True},
    ):
        protocol_error(parse_extension, bad)


def test_parse_extensions_requires_a_list() -> None:
    items = parse_extensions([{"id": "e1", "name": "n", "version": "1", "is_active": False}])
    assert [item.id for item in items] == ["e1"]
    assert parse_extensions([]) == []
    protocol_error(parse_extensions, {"data": []})
    protocol_error(parse_extensions, [{"id": "e1"}])


def test_parse_versions() -> None:
    versions = parse_versions({"chromium": ["137.0"], "firefox": ["128.0"]})
    assert versions == BrowserVersions(chromium=["137.0"], firefox=["128.0"])
    for bad in (
        {"chrome": ["1"], "firefox": []},
        {"chromium": "137", "firefox": []},
        {"chromium": [1], "firefox": []},
        {"chromium": []},
        [],
    ):
        protocol_error(parse_versions, bad)


def test_parse_start_requires_at_least_one_cdp_endpoint() -> None:
    full = parse_start(
        {
            "profile_id": "p1",
            "driver_path": "C:\\d.exe",
            "remote_debugging_port": 40444,
            "websocket_debugging_url": "ws://127.0.0.1:40444/devtools/browser/abc",
            "addition_info": {"process_id": 1},
            "future": True,
        }
    )
    assert isinstance(full, StartResult)
    assert full.remote_debugging_port == 40444
    assert full.addition_info == {"process_id": 1}
    assert full.extra == {"future": True}
    assert parse_start({"profile_id": "p", "remote_debugging_port": 9222}).driver_path is None
    assert parse_start({"profile_id": "p", "websocket_debugging_url": "ws://x"}).profile_id == "p"
    for bad in (
        {"profile_id": "p"},
        {"remote_debugging_port": 9222},
        {"profile_id": "p", "remote_debugging_port": True},
        {"profile_id": "p", "remote_debugging_port": 0},
        {"profile_id": "p", "remote_debugging_port": 70000},
        {"profile_id": "p", "remote_debugging_port": "9222"},
        {"profile_id": "p", "websocket_debugging_url": ""},
        {"profile_id": "p", "websocket_debugging_url": 5, "remote_debugging_port": 9222},
        {"profile_id": "p", "remote_debugging_port": 9222, "addition_info": []},
        {"profile_id": "p", "remote_debugging_port": 9222, "driver_path": 5},
    ):
        protocol_error(parse_start, bad)


def page_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "current_page": 1,
        "per_page": 30,
        "total": 1,
        "last_page": 1,
        "data": [{"id": "g1", "name": "M", "sort_order": 1}],
    }
    payload.update(overrides)
    return payload


def test_parse_page_with_item_parser() -> None:
    page = parse_page(page_payload(), parse_group)
    assert isinstance(page, Page)
    assert (page.current_page, page.per_page, page.total, page.last_page) == (1, 30, 1, 1)
    assert [g.id for g in page.data] == ["g1"]


def test_parse_page_allows_empty_collection_with_zero_last_page() -> None:
    page = parse_page(page_payload(total=0, last_page=0, data=[], current_page=1), parse_group)
    assert page.data == [] and page.last_page == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"current_page": -1},
        {"current_page": 0},
        {"per_page": -1},
        {"total": -1},
        {"last_page": -1},
        {"current_page": "1"},
        {"current_page": True},
        {"total": 1.5},
        {"data": "x"},
        {"data": None},
        {"current_page": 3, "last_page": 2},
        {"data": [{"id": "g1"}]},
    ],
)
def test_parse_page_rejects_bad_metadata_or_items(overrides: dict[str, Any]) -> None:
    protocol_error(parse_page, page_payload(**overrides), parse_group)


def test_parse_page_rejects_missing_metadata_and_non_object() -> None:
    for key in ("current_page", "per_page", "total", "last_page", "data"):
        payload = page_payload()
        del payload[key]
        protocol_error(parse_page, payload, parse_group)
    protocol_error(parse_page, [], parse_group)


def test_sensitive_values_never_appear_in_repr() -> None:
    details = ProfileDetails(
        id="p1",
        name="n",
        storage_path=SECRET,
        raw_proxy=SECRET,
        fingerprint={"k": SECRET},
        extra={"unknown": {"nested": SECRET}},
        note=None,
    )
    proxy = Proxy(id="x", raw_proxy=SECRET, meta_data={"m": SECRET}, extra={"u": SECRET})
    start = StartResult(
        profile_id="p1",
        driver_path=SECRET,
        remote_debugging_port=40444,
        websocket_debugging_url=f"ws://{SECRET}",
        addition_info={"a": SECRET},
        extra={"u": SECRET},
    )
    updated = ProfileUpdated(data={"k": SECRET})
    for obj in (details, proxy, start, updated, parse_profile_summary({**SUMMARY, "x": SECRET})):
        assert SECRET not in repr(obj)
        assert SECRET not in str(obj)
    assert "40444" not in repr(start)


def test_unknown_fields_are_reachable_through_extra_but_not_repr() -> None:
    created = parse_profile_created({"id": "p1", "name": "A", "leak": SECRET})
    assert created.extra["leak"] == SECRET
    assert SECRET not in repr(created)
