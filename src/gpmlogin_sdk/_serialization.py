"""Wire conversions: query strings, JSON bodies and path-segment IDs."""

from __future__ import annotations

import math
from collections.abc import Mapping
from enum import IntEnum
from urllib.parse import quote

from .errors import GPMValidationError


def _query_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(int(value))
    if isinstance(value, float):
        if not math.isfinite(value):
            raise GPMValidationError("A query value must be finite.")
        return repr(value)
    if isinstance(value, str):
        return value
    raise GPMValidationError("A query value has an unsupported type.")


def serialize_query(values: Mapping[str, object]) -> dict[str, str]:
    """Drop ``None`` and spell booleans as ``true``/``false``; ``False``, ``0`` and ``""`` stay."""
    return {key: _query_value(value) for key, value in values.items() if value is not None}


def serialize_body(values: Mapping[str, object]) -> dict[str, object]:
    """Copy a JSON body, keeping ``None`` (JSON null) and turning IntEnum members into ints."""
    return {
        key: int(value) if isinstance(value, IntEnum) else value for key, value in values.items()
    }


def encode_id(value: str) -> str:
    """Percent-encode an ID as one path segment. IDs are opaque; they need not be UUIDs."""
    if not isinstance(value, str) or value in ("", ".", ".."):
        raise GPMValidationError("An ID must be a non-empty string.")
    return quote(value, safe="")
