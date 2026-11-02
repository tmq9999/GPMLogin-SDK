"""Operation contract plus the I/O-free half of the transports (request prep, response decode)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, TypeVar

import httpx

from ._serialization import serialize_body, serialize_query
from .config import GPMConfig
from .errors import (
    GPMAPIError,
    GPMHTTPError,
    GPMProtocolError,
    GPMTimeoutError,
    GPMTransportError,
)

T = TypeVar("T")

_MISSING = object()
_INVALID_JSON = object()


@dataclass(frozen=True)
class Operation(Generic[T]):
    """One API call. ``mutates`` is explicit: a GET can still start, stop or delete things."""

    name: str
    method: Literal["GET", "POST"]
    path: str
    mutates: bool
    parser: Callable[[object], T] = field(repr=False)

    def __post_init__(self) -> None:
        path = self.path
        if (
            not path.startswith("/")
            or path.startswith("//")
            or any(char in path for char in "?#")
            or "://" in path
        ):
            raise ValueError("An operation path must be a relative '/...' path without a query.")


def parse_none(value: object) -> None:
    """Parser for operations whose success response has ``data: null``."""
    if value is not None:
        raise GPMProtocolError("parse")
    return None


def build_request_kwargs(
    config: GPMConfig,
    operation: Operation[Any],
    query: Mapping[str, object] | None,
    body: Mapping[str, object] | None,
    timeout: float | None,
) -> dict[str, Any]:
    """Arguments for ``httpx.Client.request``. Always an absolute URL built from the SDK config."""
    params = serialize_query(query) if query else None
    return {
        "method": operation.method,
        "url": config.base_url + operation.path,
        "params": params or None,
        "json": serialize_body(body) if body is not None else None,
        "timeout": config.timeout if timeout is None else timeout,
        "follow_redirects": False,
    }


def transport_failure(operation: Operation[Any], exc: Exception) -> GPMTransportError:
    """Map an HTTPX failure to a typed error that keeps nothing from ``exc``.

    Callers must raise the result *outside* their ``except`` block so no implicit exception
    context (which would carry the request URL) is attached.
    """
    uncertain = operation.mutates
    if isinstance(exc, httpx.TimeoutException):
        return GPMTimeoutError(operation.name, state_uncertain=uncertain)
    return GPMTransportError(operation.name, state_uncertain=uncertain)


def decode_response(operation: Operation[T], response: httpx.Response) -> T:
    status = response.status_code
    if not 200 <= status < 300:
        raise GPMHTTPError(operation.name, status_code=status, state_uncertain=operation.mutates)

    try:
        payload: object = response.json()
    except ValueError:
        payload = _INVALID_JSON

    if not isinstance(payload, dict):
        raise GPMProtocolError(
            operation.name, status_code=status, state_uncertain=operation.mutates
        )

    success = payload.get("success", _MISSING)
    if success is False:
        raise GPMAPIError(operation.name, status_code=status)
    if success is not True:
        raise GPMProtocolError(
            operation.name, status_code=status, state_uncertain=operation.mutates
        )

    failure: GPMProtocolError
    if "data" not in payload:
        failure = GPMProtocolError(operation.name, success_confirmed=True, status_code=status)
    else:
        try:
            return operation.parser(payload["data"])
        except GPMProtocolError:
            failure = GPMProtocolError(operation.name, success_confirmed=True, status_code=status)
    raise failure
