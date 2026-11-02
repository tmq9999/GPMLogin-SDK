"""Async client. Resources are attached in later tasks."""

from __future__ import annotations

import os
from contextlib import AbstractAsyncContextManager
from types import TracebackType

import httpx

from ._async_transport import AsyncTransport
from ._logging import install_query_redaction
from .config import GPMConfig, resolve_config
from .errors import GPMConfigurationError
from .helpers.session import AsyncProfileSession, ProfileSession, validate_session_args
from .models import StartOptions
from .resources.browsers import AsyncBrowsersResource
from .resources.extensions import AsyncExtensionsResource
from .resources.groups import AsyncGroupsResource
from .resources.profiles import AsyncProfilesResource
from .resources.proxies import AsyncProxiesResource


class AsyncGPMClient:
    """Client for the GPM Login local API using ``httpx.AsyncClient`` (asyncio only in v1).

    Same ownership rules as :class:`GPMClient`: an SDK-created HTTP client is closed by
    :meth:`aclose` / ``async with``; an injected one is never closed by the SDK. Constructing a
    client performs no network I/O and needs no running event loop.
    """

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        port_file: str | os.PathLike[str] | None = None,
        timeout: float | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config: GPMConfig = resolve_config(
            host=host, port=port, port_file=port_file, timeout=timeout
        )
        if http_client is not None and not isinstance(http_client, httpx.AsyncClient):
            raise GPMConfigurationError(
                "http_client must be an httpx.AsyncClient for AsyncGPMClient."
            )
        install_query_redaction()
        self._owns_http = http_client is None
        self._http: httpx.AsyncClient = http_client or httpx.AsyncClient(
            trust_env=False, follow_redirects=False, timeout=self.config.timeout
        )
        self._transport = AsyncTransport(self.config, self._http)
        self.profiles = AsyncProfilesResource(self._transport)
        self.browsers = AsyncBrowsersResource(self._transport)
        self.groups = AsyncGroupsResource(self._transport)
        self.proxies = AsyncProxiesResource(self._transport)
        self.extensions = AsyncExtensionsResource(self._transport)
        self._closed = False

    async def aclose(self) -> None:
        """Release the SDK-owned HTTP client. Idempotent; never closes an injected client."""
        if self._closed:
            return
        self._closed = True
        self._transport.mark_closed()
        if self._owns_http:
            await self._http.aclose()

    def profile_session(
        self,
        profile_id: str,
        *,
        exclusive: bool = False,
        start_options: StartOptions | None = None,
    ) -> AbstractAsyncContextManager[ProfileSession]:
        """Start the profile, run the ``with`` body, and stop the profile at the end, at most once.

        ``exclusive=True`` is required: the session owns the profile and takes an in-memory,
        process-local lock, so a second session for the same profile in this process fails fast
        with ``GPMProfileBusyError``. The lock is not distributed and does not prove the browser
        is stopped or was not already running. The profile is never deleted. If start times out
        the browser state is unknown (``state_uncertain``) and the SDK does not stop or retry.
        """
        validate_session_args(profile_id, exclusive, start_options)
        return AsyncProfileSession(self, profile_id, start_options)

    async def __aenter__(self) -> AsyncGPMClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
