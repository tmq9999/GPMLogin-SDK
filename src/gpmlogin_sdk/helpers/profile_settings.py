"""Convenience builders for launch options and startup URLs. Pure functions, no I/O."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from .._validation import validate_start
from ..errors import GPMValidationError
from ..models import StartOptions


def _pair(value: object, field: str, *, positive: bool) -> str:
    if (
        not isinstance(value, tuple | list)
        or len(value) != 2
        or any(isinstance(part, bool) or not isinstance(part, int) for part in value)
        or (positive and any(part <= 0 for part in value))
    ):
        raise GPMValidationError(f"Invalid value for '{field}'.", field=field)
    return f"{value[0]},{value[1]}"


def build_start_options(
    *,
    window_size: tuple[int, int] | None = None,
    window_pos: tuple[int, int] | None = None,
    window_scale: float | None = None,
    remote_debugging_port: int | None = None,
    skip_proxy_check: bool | None = None,
    addition_args: str | None = None,
) -> StartOptions:
    """Build ``StartOptions`` from convenient values; omitted (``None``) options are not sent.

    ``window_size`` is ``(width, height)`` with positive ints; ``window_pos`` is ``(x, y)`` and
    may be negative. ``addition_args`` is passed through exactly as given, with no escaping.
    ``skip_proxy_check=False`` and an empty ``addition_args`` are kept, not dropped.
    """
    options: dict[str, object] = {}
    if window_size is not None:
        options["window_size"] = _pair(window_size, "window_size", positive=True)
    if window_pos is not None:
        options["window_pos"] = _pair(window_pos, "window_pos", positive=False)
    if window_scale is not None:
        options["window_scale"] = window_scale
    if remote_debugging_port is not None:
        options["remote_debugging_port"] = remote_debugging_port
    if skip_proxy_check is not None:
        options["skip_proxy_check"] = skip_proxy_check
    if addition_args is not None:
        options["addition_args"] = addition_args
    result = cast(StartOptions, options)
    validate_start(result)
    return result


def join_startup_urls(urls: Sequence[str]) -> str:
    """Join URLs with newlines for ``startup_urls``. An empty list gives an empty string."""
    if isinstance(urls, str | bytes) or not isinstance(urls, Sequence):
        raise GPMValidationError("Invalid value for 'urls'.", field="urls")
    for url in urls:
        if not isinstance(url, str) or not url.strip() or "\r" in url or "\n" in url:
            raise GPMValidationError("Invalid value for 'urls'.", field="urls")
    return "\n".join(urls)
