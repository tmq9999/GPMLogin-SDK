"""Shared request-building helpers for resources. No I/O here."""

from __future__ import annotations

from typing import Generic, NamedTuple, TypeVar

from .._operations import Operation
from ..enums import SortOrder
from ..errors import GPMValidationError

T = TypeVar("T")


class Call(NamedTuple, Generic[T]):
    """A fully validated request, ready for ``Transport.request`` or ``AsyncTransport.request``."""

    operation: Operation[T]
    query: dict[str, object] | None = None
    body: dict[str, object] | None = None


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise GPMValidationError(f"Invalid value for '{field}'.", field=field)
    return value


def page_query(
    *, page: object, page_size: object, search: object, sort: object
) -> dict[str, object]:
    """Validated list query. ``sort`` accepts the numeric ``SortOrder`` values 0-3 only."""
    page_number = _positive_int(page, "page")
    size = _positive_int(page_size, "page_size")
    if search is not None and not isinstance(search, str):
        raise GPMValidationError("Invalid value for 'search'.", field="search")
    if isinstance(sort, bool) or not isinstance(sort, int) or sort not in tuple(SortOrder):
        raise GPMValidationError("Invalid value for 'sort'.", field="sort")
    query: dict[str, object] = {"page": page_number, "page_size": size, "sort": int(sort)}
    if search is not None:
        query["search"] = search
    return query


def require_confirm(confirm: object, what: str) -> None:
    """Destructive deletes need an explicit literal ``confirm=True``; the SDK never prompts."""
    if confirm is not True:
        raise GPMValidationError(f"Deleting {what} requires confirm=True.", field="confirm")


def non_blank_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GPMValidationError(f"Invalid value for '{field}'.", field=field)
    return value


def optional_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise GPMValidationError(f"Invalid value for '{field}'.", field=field)
    return value
