"""Numeric enums taken verbatim from the GPM Login API documentation (section 4.5 and 2.4)."""

from __future__ import annotations

from enum import IntEnum


class BrowserType(IntEnum):
    CHROME = 1
    FIREFOX = 2


class OSType(IntEnum):
    WINDOWS = 1
    MACOS_INTEL = 2
    MACOS_ARM = 3
    LINUX = 4
    ANDROID = 5


class WebRTCMode(IntEnum):
    IP_BASED = 1
    FIXED = 2
    REAL = 3
    DISABLED = 4


class GeolocationMode(IntEnum):
    ALLOW = 1
    PROMPT = 2
    BLOCK = 3


class CanvasMode(IntEnum):
    NOISE = 1
    REAL = 2
    BLOCK = 3


class ClientRectMode(IntEnum):
    NOISE = 1
    REAL = 2


class WebGLImageMode(IntEnum):
    NOISE = 1
    REAL = 2


class WebGLMetadataMode(IntEnum):
    MASKED = 1
    REAL = 2


class AudioMode(IntEnum):
    NOISE = 1
    REAL = 2


class FontMode(IntEnum):
    MASKED = 1
    REAL = 2


class SortOrder(IntEnum):
    NEWEST = 0
    OLDEST = 1
    NAME_ASC = 2
    NAME_DESC = 3
