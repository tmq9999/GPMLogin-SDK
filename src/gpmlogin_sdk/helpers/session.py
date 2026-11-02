"""Exclusive profile sessions: start, run the caller's work, stop at most once, never delete."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import TracebackType
from typing import TYPE_CHECKING

from .._ownership import (
    Lease,
    acquire_profile,
    attach_cleanup_error,
    run_bounded_cleanup,
)
from ..errors import (
    GPMCleanupError,
    GPMConfigurationError,
    GPMError,
    GPMProtocolError,
    GPMValidationError,
)
from ..models import StartOptions, StartResult
from ..resources.profiles import start_call, stop_call

if TYPE_CHECKING:
    from ..async_client import AsyncGPMClient
    from ..client import GPMClient

CLEANUP_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class ProfileSession:
    """A started profile. ``launch`` hides endpoints and paths from ``repr``."""

    profile_id: str
    launch: StartResult


def validate_session_args(
    profile_id: str, exclusive: object, start_options: StartOptions | None
) -> None:
    if exclusive is not True:
        raise GPMValidationError(
            "profile_session requires exclusive=True: it owns the profile and stops it at the end.",
            field="exclusive",
        )
    start_call(profile_id, start_options)


def _stop_timeout(client_timeout: float) -> float:
    return min(CLEANUP_TIMEOUT_SECONDS, client_timeout)


def _cleanup_error(error: Exception) -> GPMCleanupError:
    return GPMCleanupError(error if isinstance(error, GPMError) else None)


class SyncProfileSession:
    def __init__(
        self, client: GPMClient, profile_id: str, start_options: StartOptions | None
    ) -> None:
        self._client = client
        self._profile_id = profile_id
        self._options = start_options
        self._used = False
        self._lease: Lease | None = None

    def _stop(self) -> GPMCleanupError | None:
        client = self._client
        operation = stop_call(self._profile_id).operation
        try:
            client._transport.request(operation, timeout=_stop_timeout(client.config.timeout))
        except Exception as error:
            return _cleanup_error(error)
        return None

    def __enter__(self) -> ProfileSession:
        if self._used:
            raise GPMConfigurationError("A profile session context can only be entered once.")
        self._used = True
        lease = acquire_profile(self._client.config.api_key, self._profile_id)
        try:
            launch = self._client.profiles.start(self._profile_id, self._options)
        except GPMProtocolError as error:
            try:
                if error.success_confirmed:
                    cleanup = self._stop()
                    if cleanup is not None:
                        attach_cleanup_error(error, cleanup)
            finally:
                lease.release()
            raise
        except BaseException:
            lease.release()
            raise
        self._lease = lease
        return ProfileSession(self._profile_id, launch)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        lease, self._lease = self._lease, None
        if lease is None:
            return
        try:
            cleanup = self._stop()
        finally:
            lease.release()
        if cleanup is None:
            return
        if exc is None:
            raise cleanup
        attach_cleanup_error(exc, cleanup)


class AsyncProfileSession:
    def __init__(
        self, client: AsyncGPMClient, profile_id: str, start_options: StartOptions | None
    ) -> None:
        self._client = client
        self._profile_id = profile_id
        self._options = start_options
        self._used = False
        self._lease: Lease | None = None

    async def _stop(self) -> GPMCleanupError | None:
        client = self._client
        operation = stop_call(self._profile_id).operation
        try:
            await client._transport.request(operation, timeout=_stop_timeout(client.config.timeout))
        except Exception as error:
            return _cleanup_error(error)
        return None

    async def __aenter__(self) -> ProfileSession:
        if self._used:
            raise GPMConfigurationError("A profile session context can only be entered once.")
        self._used = True
        lease = acquire_profile(self._client.config.api_key, self._profile_id)
        try:
            launch = await self._client.profiles.start(self._profile_id, self._options)
        except GPMProtocolError as error:
            cancelled = False
            try:
                if error.success_confirmed:
                    cleanup, cancelled = await run_bounded_cleanup(
                        self._stop(), failure=GPMCleanupError, timeout=CLEANUP_TIMEOUT_SECONDS
                    )
                    if cleanup is not None:
                        attach_cleanup_error(error, cleanup)
            finally:
                lease.release()
            if cancelled:
                raise asyncio.CancelledError from None
            raise
        except BaseException:
            lease.release()
            raise
        self._lease = lease
        return ProfileSession(self._profile_id, launch)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        lease, self._lease = self._lease, None
        if lease is None:
            return
        try:
            cleanup, cancelled = await run_bounded_cleanup(
                self._stop(), failure=GPMCleanupError, timeout=CLEANUP_TIMEOUT_SECONDS
            )
        finally:
            lease.release()
        if cancelled:
            if isinstance(exc, asyncio.CancelledError):
                if cleanup is not None:
                    attach_cleanup_error(exc, cleanup)
                return
            cancellation = asyncio.CancelledError()
            if cleanup is not None:
                attach_cleanup_error(cancellation, cleanup)
            raise cancellation
        if cleanup is None:
            return
        if exc is None:
            raise cleanup
        attach_cleanup_error(exc, cleanup)
