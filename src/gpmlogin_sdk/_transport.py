"""Blocking transport over ``httpx.Client``. Never retries; never follows redirects."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeVar

import httpx

from ._operations import Operation, build_request_kwargs, decode_response, transport_failure
from .config import GPMConfig
from .errors import GPMConfigurationError

T = TypeVar("T")


class Transport:
    def __init__(self, config: GPMConfig, http_client: httpx.Client) -> None:
        self._config = config
        self._http = http_client
        self._closed = False

    def mark_closed(self) -> None:
        self._closed = True

    def request(
        self,
        operation: Operation[T],
        *,
        query: Mapping[str, object] | None = None,
        body: Mapping[str, object] | None = None,
        timeout: float | None = None,
    ) -> T:
        if self._closed or self._http.is_closed:
            raise GPMConfigurationError("The client is closed.")
        kwargs = build_request_kwargs(self._config, operation, query, body, timeout)
        try:
            response = self._http.request(**kwargs)
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            failure = transport_failure(operation, exc)
        else:
            return decode_response(operation, response)
        raise failure
