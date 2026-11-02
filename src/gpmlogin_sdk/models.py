"""Request TypedDicts, response dataclasses and their strict parsers.

Fields that can carry secrets or local paths (proxies, storage and driver paths, fingerprints, CDP
endpoints, unknown vendor keys) use ``repr=False`` so they never reach logs or tracebacks by
accident. Unknown response keys are kept in ``extra``.

This module deliberately has no ``from __future__ import annotations``: ``Required[...]`` in
TypedDicts is only honoured at runtime when annotations are evaluated eagerly.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, NoReturn, Required, TypedDict, TypeVar

from .errors import GPMProtocolError

T = TypeVar("T")


class _ProfileSettings(TypedDict, total=False):
    group_id: str | None
    raw_proxy: str | None
    bypass_proxy_extensions: str | None
    browser_type: int | None
    browser_version: str | None
    os_type: int | None
    custom_user_agent: str | None
    task_bar_title: str | None
    webrtc_mode: int | None
    fixed_webrtc_public_ip: str | None
    port_protect: str | None
    geolocation_mode: int | None
    canvas_mode: int | None
    client_rect_mode: int | None
    webgl_image_mode: int | None
    webgl_metadata_mode: int | None
    audio_mode: int | None
    is_masked_media: bool | None
    font_mode: int | None
    timezone_base_on_ip: bool | None
    timezone: str | None
    is_language_base_on_ip: bool | None
    fixed_language: str | None
    startup_urls: str | None
    note: str | None


class CreateProfileRequest(_ProfileSettings, total=False):
    name: Required[str]


class UpdateProfileRequest(_ProfileSettings, total=False):
    name: str


class StartOptions(TypedDict, total=False):
    remote_debugging_port: int
    window_scale: float
    window_pos: str
    window_size: str
    skip_proxy_check: bool
    addition_args: str


@dataclass(frozen=True)
class BrowserInfo:
    name: str | None = None
    version: str | None = None
    extra: dict[str, object] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class ProfileSummary:
    id: str
    name: str
    group_id: str | None = None
    storage_path: str | None = field(default=None, repr=False)
    raw_proxy: str | None = field(default=None, repr=False)
    browser: BrowserInfo | None = None
    os: str | None = None
    note: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    tags: list[object] | None = None
    extra: dict[str, object] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class ProfileDetails(ProfileSummary):
    fingerprint: dict[str, object] | None = field(default=None, repr=False)


@dataclass(frozen=True)
class ProfileCreated:
    id: str
    name: str
    extra: dict[str, object] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class ProfileUpdated:
    """Result of a profile update. The vendor does not document the response, so it is opaque."""

    data: dict[str, object] | None = field(default=None, repr=False)


@dataclass(frozen=True)
class Group:
    id: str
    name: str
    sort_order: int
    extra: dict[str, object] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class Proxy:
    id: str
    raw_proxy: str = field(repr=False)
    meta_data: object | None = field(default=None, repr=False)
    tags: list[object] | None = None
    extra: dict[str, object] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class Extension:
    id: str
    name: str
    version: str
    is_active: bool
    extra: dict[str, object] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class BrowserVersions:
    chromium: list[str]
    firefox: list[str]
    extra: dict[str, object] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class StartResult:
    profile_id: str
    driver_path: str | None = field(default=None, repr=False)
    remote_debugging_port: int | None = field(default=None, repr=False)
    websocket_debugging_url: str | None = field(default=None, repr=False)
    addition_info: dict[str, object] | None = field(default=None, repr=False)
    extra: dict[str, object] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class Page(Generic[T]):
    current_page: int
    per_page: int
    total: int
    last_page: int
    data: list[T]
    extra: dict[str, object] = field(default_factory=dict, repr=False)


def _fail() -> NoReturn:
    raise GPMProtocolError("parse")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        _fail()
    return dict(value)


def _req_str(data: dict[str, object], key: str, *, non_empty: bool = False) -> str:
    value = data.pop(key, None)
    if not isinstance(value, str) or (non_empty and not value):
        _fail()
    return value


def _opt_str(data: dict[str, object], key: str, *, non_empty: bool = False) -> str | None:
    value = data.pop(key, None)
    if value is None:
        return None
    if not isinstance(value, str) or (non_empty and not value):
        _fail()
    return value


def _req_int(data: dict[str, object], key: str) -> int:
    value = data.pop(key, None)
    if not isinstance(value, int) or isinstance(value, bool):
        _fail()
    return value


def _opt_dict(data: dict[str, object], key: str) -> dict[str, object] | None:
    value = data.pop(key, None)
    if value is None:
        return None
    return _mapping(value)


def _opt_list(data: dict[str, object], key: str) -> list[object] | None:
    value = data.pop(key, None)
    if value is None:
        return None
    if not isinstance(value, list):
        _fail()
    return list(value)


def _parse_browser(value: object) -> BrowserInfo:
    data = _mapping(value)
    return BrowserInfo(name=_opt_str(data, "name"), version=_opt_str(data, "version"), extra=data)


def _summary_fields(data: dict[str, object]) -> dict[str, Any]:
    browser = data.pop("browser", None)
    return {
        "id": _req_str(data, "id", non_empty=True),
        "name": _req_str(data, "name"),
        "group_id": _opt_str(data, "group_id"),
        "storage_path": _opt_str(data, "storage_path"),
        "raw_proxy": _opt_str(data, "raw_proxy"),
        "browser": None if browser is None else _parse_browser(browser),
        "os": _opt_str(data, "os"),
        "note": _opt_str(data, "note"),
        "created_at": _opt_str(data, "created_at"),
        "updated_at": _opt_str(data, "updated_at"),
        "tags": _opt_list(data, "tags"),
    }


def parse_profile_summary(value: object) -> ProfileSummary:
    data = _mapping(value)
    fields = _summary_fields(data)
    return ProfileSummary(**fields, extra=data)


def parse_profile_details(value: object) -> ProfileDetails:
    data = _mapping(value)
    fields = _summary_fields(data)
    fingerprint = _opt_dict(data, "fingerprint")
    return ProfileDetails(**fields, fingerprint=fingerprint, extra=data)


def parse_profile_created(value: object) -> ProfileCreated:
    data = _mapping(value)
    return ProfileCreated(
        id=_req_str(data, "id", non_empty=True), name=_req_str(data, "name"), extra=data
    )


def parse_profile_updated(value: object) -> ProfileUpdated:
    if value is None:
        return ProfileUpdated(data=None)
    return ProfileUpdated(data=_mapping(value))


def parse_group(value: object) -> Group:
    data = _mapping(value)
    return Group(
        id=_req_str(data, "id", non_empty=True),
        name=_req_str(data, "name"),
        sort_order=_req_int(data, "sort_order"),
        extra=data,
    )


def parse_proxy(value: object) -> Proxy:
    data = _mapping(value)
    return Proxy(
        id=_req_str(data, "id", non_empty=True),
        raw_proxy=_req_str(data, "raw_proxy"),
        meta_data=data.pop("meta_data", None),
        tags=_opt_list(data, "tags"),
        extra=data,
    )


def parse_extension(value: object) -> Extension:
    data = _mapping(value)
    is_active = data.pop("is_active", None)
    if not isinstance(is_active, bool):
        _fail()
    return Extension(
        id=_req_str(data, "id", non_empty=True),
        name=_req_str(data, "name"),
        version=_req_str(data, "version"),
        is_active=is_active,
        extra=data,
    )


def parse_extensions(value: object) -> list[Extension]:
    if not isinstance(value, list):
        _fail()
    return [parse_extension(item) for item in value]


def _str_list(data: dict[str, object], key: str) -> list[str]:
    value = data.pop(key, None)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        _fail()
    return list(value)


def parse_versions(value: object) -> BrowserVersions:
    data = _mapping(value)
    return BrowserVersions(
        chromium=_str_list(data, "chromium"), firefox=_str_list(data, "firefox"), extra=data
    )


def parse_start(value: object) -> StartResult:
    data = _mapping(value)
    profile_id = _req_str(data, "profile_id", non_empty=True)
    driver_path = _opt_str(data, "driver_path")
    port_value = data.pop("remote_debugging_port", None)
    port: int | None = None
    if port_value is not None:
        if not _is_int(port_value) or not 1 <= int(port_value) <= 65535:  # type: ignore[call-overload]
            _fail()
        port = int(port_value)  # type: ignore[call-overload]
    websocket_url = _opt_str(data, "websocket_debugging_url", non_empty=True)
    addition_info = _opt_dict(data, "addition_info")
    if port is None and websocket_url is None:
        _fail()
    return StartResult(
        profile_id=profile_id,
        driver_path=driver_path,
        remote_debugging_port=port,
        websocket_debugging_url=websocket_url,
        addition_info=addition_info,
        extra=data,
    )


def parse_page(value: object, item_parser: Callable[[object], T]) -> Page[T]:
    data = _mapping(value)
    current_page = _req_int(data, "current_page")
    per_page = _req_int(data, "per_page")
    total = _req_int(data, "total")
    last_page = _req_int(data, "last_page")
    raw_items = data.pop("data", None)
    if not isinstance(raw_items, list):
        _fail()
    if current_page < 1 or per_page < 0 or total < 0 or last_page < 0:
        _fail()
    items = [item_parser(item) for item in raw_items]
    if items and last_page < current_page:
        _fail()
    return Page(
        current_page=current_page,
        per_page=per_page,
        total=total,
        last_page=last_page,
        data=items,
        extra=data,
    )
