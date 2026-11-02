from __future__ import annotations

from typing import Any

import pytest

from gpmlogin_sdk._validation import validate_create, validate_start, validate_update
from gpmlogin_sdk.enums import (
    AudioMode,
    BrowserType,
    CanvasMode,
    ClientRectMode,
    FontMode,
    GeolocationMode,
    OSType,
    SortOrder,
    WebGLImageMode,
    WebGLMetadataMode,
    WebRTCMode,
)
from gpmlogin_sdk.errors import GPMValidationError

ENUM_TABLE: dict[str, tuple[Any, set[int]]] = {
    "browser_type": (BrowserType, {1, 2}),
    "os_type": (OSType, {1, 2, 3, 4, 5}),
    "webrtc_mode": (WebRTCMode, {1, 2, 3, 4}),
    "geolocation_mode": (GeolocationMode, {1, 2, 3}),
    "canvas_mode": (CanvasMode, {1, 2, 3}),
    "client_rect_mode": (ClientRectMode, {1, 2}),
    "webgl_image_mode": (WebGLImageMode, {1, 2}),
    "webgl_metadata_mode": (WebGLMetadataMode, {1, 2}),
    "audio_mode": (AudioMode, {1, 2}),
    "font_mode": (FontMode, {1, 2}),
}


def test_enum_values_match_source_table() -> None:
    for enum_cls, expected in ENUM_TABLE.values():
        assert {member.value for member in enum_cls} == expected
    assert {member.value for member in SortOrder} == {0, 1, 2, 3}
    assert BrowserType.CHROME == 1 and BrowserType.FIREFOX == 2


def test_create_requires_non_empty_name() -> None:
    validate_create({"name": "A"})
    for body in ({}, {"name": ""}, {"name": "   "}, {"name": None}, {"name": 5}):
        with pytest.raises(GPMValidationError):
            validate_create(body)  # type: ignore[arg-type]


def test_create_accepts_complete_valid_body() -> None:
    validate_create(
        {
            "name": "A",
            "group_id": None,
            "raw_proxy": "socks5://127.0.0.1:5000",
            "bypass_proxy_extensions": "a.com",
            "browser_type": 1,
            "browser_version": "137.0.7151.41",
            "os_type": BrowserType.CHROME,
            "custom_user_agent": "ua",
            "task_bar_title": "t",
            "webrtc_mode": 2,
            "fixed_webrtc_public_ip": "203.0.113.10",
            "port_protect": "p",
            "geolocation_mode": 1,
            "canvas_mode": 1,
            "client_rect_mode": 1,
            "webgl_image_mode": 1,
            "webgl_metadata_mode": 1,
            "audio_mode": 1,
            "is_masked_media": False,
            "font_mode": 1,
            "timezone_base_on_ip": False,
            "timezone": "Asia/Ho_Chi_Minh",
            "is_language_base_on_ip": False,
            "fixed_language": "en",
            "startup_urls": "https://a.example\nhttps://b.example",
            "note": None,
        }
    )


def test_create_rejects_unknown_key_without_echoing_it() -> None:
    with pytest.raises(GPMValidationError) as caught:
        validate_create({"name": "A", "SECRET_KEY": 1})  # type: ignore[typeddict-unknown-key]
    assert "SECRET_KEY" not in str(caught.value)


def test_create_webrtc_fixed_requires_ip() -> None:
    with pytest.raises(GPMValidationError):
        validate_create({"name": "A", "webrtc_mode": 2})
    with pytest.raises(GPMValidationError):
        validate_create({"name": "A", "webrtc_mode": 2, "fixed_webrtc_public_ip": ""})
    validate_create({"name": "A", "webrtc_mode": 2, "fixed_webrtc_public_ip": "203.0.113.10"})
    validate_create({"name": "A", "webrtc_mode": 1})


@pytest.mark.parametrize("field", sorted(ENUM_TABLE))
def test_enum_fields_accept_table_values_and_reject_others(field: str) -> None:
    enum_cls, valid = ENUM_TABLE[field]
    extra: dict[str, Any] = {}
    for value in sorted(valid):
        if field == "webrtc_mode" and value == 2:
            extra = {"fixed_webrtc_public_ip": "203.0.113.10"}
        validate_create({"name": "A", field: value, **extra})  # type: ignore[misc]
    validate_create({"name": "A", field: list(enum_cls)[0], **extra})  # type: ignore[misc]
    for bad in (0, max(valid) + 1, -1, True, False, 1.0, "1", "chrome", None.__class__):
        with pytest.raises(GPMValidationError):
            validate_create({"name": "A", field: bad})  # type: ignore[misc]


@pytest.mark.parametrize(
    "field", ["is_masked_media", "timezone_base_on_ip", "is_language_base_on_ip"]
)
def test_bool_fields_reject_non_bool(field: str) -> None:
    validate_create({"name": "A", field: True})  # type: ignore[misc]
    validate_create({"name": "A", field: False})  # type: ignore[misc]
    for bad in (0, 1, "true"):
        with pytest.raises(GPMValidationError):
            validate_create({"name": "A", field: bad})  # type: ignore[misc]


@pytest.mark.parametrize(
    "field",
    [
        "raw_proxy",
        "bypass_proxy_extensions",
        "browser_version",
        "custom_user_agent",
        "task_bar_title",
        "fixed_webrtc_public_ip",
        "port_protect",
        "timezone",
        "fixed_language",
        "startup_urls",
        "note",
        "group_id",
    ],
)
def test_string_fields_reject_non_strings_and_accept_none_and_empty(field: str) -> None:
    validate_create({"name": "A", field: ""})  # type: ignore[misc]
    validate_create({"name": "A", field: None})  # type: ignore[misc]
    for bad in (5, True, ["x"], b"x"):
        with pytest.raises(GPMValidationError):
            validate_create({"name": "A", field: bad})  # type: ignore[misc]


def test_invalid_value_error_does_not_echo_value() -> None:
    with pytest.raises(GPMValidationError) as caught:
        validate_create({"name": "A", "timezone": 987654})  # type: ignore[typeddict-item]
    assert "987654" not in str(caught.value)
    assert caught.value.field == "timezone"


def test_body_must_be_a_mapping() -> None:
    for fn in (validate_create, validate_update):
        with pytest.raises(GPMValidationError):
            fn(["name"])  # type: ignore[arg-type]


def test_update_name_is_optional_but_not_null() -> None:
    validate_update({})
    validate_update({"note": "only note"})
    validate_update({"name": "N"})
    for bad in ({"name": None}, {"name": ""}, {"name": 3}):
        with pytest.raises(GPMValidationError):
            validate_update(bad)  # type: ignore[arg-type]


def test_update_raw_proxy_empty_string_differs_from_null_and_both_are_valid() -> None:
    validate_update({"raw_proxy": ""})
    validate_update({"raw_proxy": None})


def test_update_requires_ip_only_when_request_sets_fixed_webrtc() -> None:
    validate_update({"webrtc_mode": 1})
    validate_update({"fixed_webrtc_public_ip": "203.0.113.10"})
    with pytest.raises(GPMValidationError):
        validate_update({"webrtc_mode": 2})
    validate_update({"webrtc_mode": 2, "fixed_webrtc_public_ip": "203.0.113.10"})


def test_start_options_valid_and_invalid() -> None:
    validate_start({})
    validate_start(
        {
            "remote_debugging_port": 9222,
            "window_scale": 0.8,
            "window_pos": "-100,0",
            "window_size": "1280,800",
            "skip_proxy_check": False,
            "addition_args": "--mute-audio --foo=bar baz",
        }
    )
    bad_options: list[dict[str, Any]] = [
        {"remote_debugging_port": 0},
        {"remote_debugging_port": 65536},
        {"remote_debugging_port": True},
        {"remote_debugging_port": "9222"},
        {"window_scale": 0},
        {"window_scale": -1.0},
        {"window_scale": float("nan")},
        {"window_scale": True},
        {"window_pos": "100"},
        {"window_pos": "a,b"},
        {"window_pos": (1, 2)},
        {"window_size": "0,600"},
        {"window_size": "-1,600"},
        {"window_size": "800x600"},
        {"skip_proxy_check": 1},
        {"addition_args": 5},
        {"unknown": 1},
    ]
    for bad in bad_options:
        with pytest.raises(GPMValidationError):
            validate_start(bad)  # type: ignore[arg-type]


DOCUMENTED_KEYS = {
    "name", "group_id", "raw_proxy", "bypass_proxy_extensions", "browser_type", "browser_version",
    "os_type", "custom_user_agent", "task_bar_title", "webrtc_mode", "fixed_webrtc_public_ip",
    "port_protect", "geolocation_mode", "canvas_mode", "client_rect_mode", "webgl_image_mode",
    "webgl_metadata_mode", "audio_mode", "is_masked_media", "font_mode", "timezone_base_on_ip",
    "timezone", "is_language_base_on_ip", "fixed_language", "startup_urls", "note",
}  # fmt: skip


def test_request_typed_dicts_have_exactly_the_documented_keys() -> None:
    from gpmlogin_sdk.models import CreateProfileRequest, StartOptions, UpdateProfileRequest

    assert set(CreateProfileRequest.__annotations__) == DOCUMENTED_KEYS
    assert set(UpdateProfileRequest.__annotations__) == DOCUMENTED_KEYS
    assert CreateProfileRequest.__required_keys__ == {"name"}
    assert UpdateProfileRequest.__required_keys__ == frozenset()
    assert set(StartOptions.__annotations__) == {
        "remote_debugging_port", "window_scale", "window_pos", "window_size",
        "skip_proxy_check", "addition_args",
    }  # fmt: skip
