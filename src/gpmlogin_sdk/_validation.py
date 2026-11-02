"""Pure request validation. Error text is fixed; it never contains caller-supplied values."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping

from .enums import (
    AudioMode,
    BrowserType,
    CanvasMode,
    ClientRectMode,
    FontMode,
    GeolocationMode,
    OSType,
    WebGLImageMode,
    WebGLMetadataMode,
    WebRTCMode,
)
from .errors import GPMValidationError
from .models import CreateProfileRequest, StartOptions, UpdateProfileRequest

_ENUM_FIELDS: dict[str, frozenset[int]] = {
    "browser_type": frozenset(m.value for m in BrowserType),
    "os_type": frozenset(m.value for m in OSType),
    "webrtc_mode": frozenset(m.value for m in WebRTCMode),
    "geolocation_mode": frozenset(m.value for m in GeolocationMode),
    "canvas_mode": frozenset(m.value for m in CanvasMode),
    "client_rect_mode": frozenset(m.value for m in ClientRectMode),
    "webgl_image_mode": frozenset(m.value for m in WebGLImageMode),
    "webgl_metadata_mode": frozenset(m.value for m in WebGLMetadataMode),
    "audio_mode": frozenset(m.value for m in AudioMode),
    "font_mode": frozenset(m.value for m in FontMode),
}
_BOOL_FIELDS = frozenset({"is_masked_media", "timezone_base_on_ip", "is_language_base_on_ip"})
_STR_FIELDS = frozenset(
    {
        "group_id",
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
    }
)
_PROFILE_KEYS = frozenset(
    UpdateProfileRequest.__required_keys__ | UpdateProfileRequest.__optional_keys__
)
_START_KEYS = frozenset(StartOptions.__required_keys__ | StartOptions.__optional_keys__)

_POS_RE = re.compile(r"-?[0-9]+,-?[0-9]+")
_SIZE_RE = re.compile(r"[0-9]+,[0-9]+")


def _invalid(field: str) -> GPMValidationError:
    return GPMValidationError(f"Invalid value for '{field}'.", field=field)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_profile_body(body: object, *, create: bool) -> None:
    if not isinstance(body, Mapping):
        raise GPMValidationError("The request body must be a mapping.")
    for key in body:
        if not isinstance(key, str) or key not in _PROFILE_KEYS:
            raise GPMValidationError("The request contains an unknown field.")

    if "name" in body:
        name = body["name"]
        if not isinstance(name, str) or not name.strip():
            raise _invalid("name")
    elif create:
        raise GPMValidationError("The 'name' field is required.", field="name")

    for key, value in body.items():
        if key == "name" or value is None:
            continue
        if key in _STR_FIELDS:
            valid = isinstance(value, str)
        elif key in _BOOL_FIELDS:
            valid = isinstance(value, bool)
        else:
            valid = _is_int(value) and value in _ENUM_FIELDS[key]
        if not valid:
            raise _invalid(key)

    if body.get("webrtc_mode") == WebRTCMode.FIXED:
        ip = body.get("fixed_webrtc_public_ip")
        if not isinstance(ip, str) or not ip:
            raise GPMValidationError(
                "A fixed WebRTC mode requires 'fixed_webrtc_public_ip'.",
                field="fixed_webrtc_public_ip",
            )


def validate_create(body: CreateProfileRequest) -> None:
    _validate_profile_body(body, create=True)


def validate_update(body: UpdateProfileRequest) -> None:
    _validate_profile_body(body, create=False)


def validate_start(options: StartOptions) -> None:
    if not isinstance(options, Mapping):
        raise GPMValidationError("The start options must be a mapping.")
    for key in options:
        if not isinstance(key, str) or key not in _START_KEYS:
            raise GPMValidationError("The start options contain an unknown field.")

    port = options.get("remote_debugging_port")
    if "remote_debugging_port" in options and (not _is_int(port) or not 1 <= port <= 65535):  # type: ignore[operator]
        raise _invalid("remote_debugging_port")

    if "window_scale" in options:
        scale = options["window_scale"]
        if (
            isinstance(scale, bool)
            or not isinstance(scale, int | float)
            or not math.isfinite(scale)
            or scale <= 0
        ):
            raise _invalid("window_scale")

    if "window_pos" in options:
        pos = options["window_pos"]
        if not isinstance(pos, str) or not _POS_RE.fullmatch(pos):
            raise _invalid("window_pos")

    if "window_size" in options:
        size = options["window_size"]
        if (
            not isinstance(size, str)
            or not _SIZE_RE.fullmatch(size)
            or any(int(part) <= 0 for part in size.split(","))
        ):
            raise _invalid("window_size")

    if "skip_proxy_check" in options and not isinstance(options["skip_proxy_check"], bool):
        raise _invalid("skip_proxy_check")

    if "addition_args" in options and not isinstance(options["addition_args"], str):
        raise _invalid("addition_args")
