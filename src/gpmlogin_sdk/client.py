"""Blocking client. Resources are attached in later tasks."""

from __future__ import annotations

import os
from contextlib import AbstractContextManager
from types import TracebackType

import httpx

from ._logging import install_query_redaction
from ._transport import Transport
from .config import GPMConfig, resolve_config
from .errors import GPMConfigurationError
from .helpers.session import ProfileSession, SyncProfileSession, validate_session_args
from .models import StartOptions
from .resources.browsers import BrowsersResource
from .resources.extensions import ExtensionsResource
from .resources.groups import GroupsResource
from .resources.profiles import ProfilesResource
from .resources.proxies import ProxiesResource


class GPMClient:
    """Client for the GPM Login local API using a blocking ``httpx.Client``.

    Ownership: an HTTP client created by the SDK is closed by :meth:`close` / ``with``; a client
    passed as ``http_client`` is never closed by the SDK and the caller must configure it
    equivalently (no proxies from the environment, no redirects). Constructing a client performs
    no network I/O.
    """

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        port_file: str | os.PathLike[str] | None = None,
        timeout: float | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.config: GPMConfig = resolve_config(
            host=host, port=port, port_file=port_file, timeout=timeout
        )
        if http_client is not None and not isinstance(http_client, httpx.Client):
            raise GPMConfigurationError("http_client must be an httpx.Client for GPMClient.")
        install_query_redaction()
        self._owns_http = http_client is None
        self._http: httpx.Client = http_client or httpx.Client(
            trust_env=False, follow_redirects=False, timeout=self.config.timeout
        )
        self._transport = Transport(self.config, self._http)
        self.profiles = ProfilesResource(self._transport)
        self.browsers = BrowsersResource(self._transport)
        self.groups = GroupsResource(self._transport)
        self.proxies = ProxiesResource(self._transport)
        self.extensions = ExtensionsResource(self._transport)
        self._closed = False

    def close(self) -> None:
        """Release the SDK-owned HTTP client. Idempotent; never closes an injected client."""
        if self._closed:
            return
        self._closed = True
        self._transport.mark_closed()
        if self._owns_http:
            self._http.close()

    def profile_session(
        self,
        profile_id: str,
        *,
        exclusive: bool = False,
        start_options: StartOptions | None = None,
    ) -> AbstractContextManager[ProfileSession]:
        """Start the profile, run the ``with`` body, and stop the profile at the end, at most once.

        ``exclusive=True`` is required: the session owns the profile and takes an in-memory,
        process-local lock, so a second session for the same profile in this process fails fast
        with ``GPMProfileBusyError``. The lock is not distributed and does not prove the browser
        is stopped or was not already running. The profile is never deleted. If start times out
        the browser state is unknown (``state_uncertain``) and the SDK does not stop or retry.
        """
        validate_session_args(profile_id, exclusive, start_options)
        return SyncProfileSession(self, profile_id, start_options)

    def __enter__(self) -> GPMClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
