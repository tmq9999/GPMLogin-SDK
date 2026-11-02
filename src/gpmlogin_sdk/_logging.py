"""Keep request query strings out of HTTPX's INFO request log.

HTTPX logs every request URL, query included, at INFO on the ``httpx`` logger. GPM queries can
hold search text and launch arguments, so a filter drops the query from loopback ``/api/v1`` URLs.
It is attached once to the shared ``httpx`` logger when a client is created and leaves every
other URL untouched.
"""

from __future__ import annotations

import logging

import httpx

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})
_API_PREFIX = "/api/v1"


def _redact(value: object) -> object:
    if (
        isinstance(value, httpx.URL)
        and value.host in _LOOPBACK_HOSTS
        and value.path.startswith(_API_PREFIX)
        and value.query
    ):
        return value.copy_with(query=None)
    return value


class _RedactQuery(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(_redact(arg) for arg in record.args)
        return True


def install_query_redaction() -> None:
    logger = logging.getLogger("httpx")
    if not any(isinstance(existing, _RedactQuery) for existing in logger.filters):
        logger.addFilter(_RedactQuery())
