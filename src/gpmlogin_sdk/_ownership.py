"""Process-wide, in-memory exclusive profile ownership and bounded async cleanup.

The registry only stops two sessions in one Python process from driving the same profile at once.
It is not distributed: other processes, other machines and the GPM UI are not covered, and holding
a lease does not prove the browser is stopped.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

from .errors import GPMCleanupError, GPMError, GPMProfileBusyError

E = TypeVar("E", bound=GPMError)

_LOCK = threading.Lock()
_HELD: set[tuple[str, int, str]] = set()

CLEANUP_NOTE = "Profile cleanup also failed; see the cleanup_error attribute or GPMCleanupError."


class Lease:
    def __init__(self, key: tuple[str, int, str]) -> None:
        self._key = key
        self._released = False

    def release(self) -> None:
        """Free the profile. Idempotent, and a stale lease never frees a newer holder's lock."""
        with _LOCK:
            if self._released:
                return
            self._released = True
            _HELD.discard(self._key)


def acquire_profile(api_key: tuple[str, int], profile_id: str) -> Lease:
    """Take the profile or fail fast with :class:`GPMProfileBusyError`; never waits."""
    key = (api_key[0], api_key[1], profile_id)
    with _LOCK:
        if key in _HELD:
            busy = True
        else:
            _HELD.add(key)
            busy = False
    if busy:
        raise GPMProfileBusyError
    return Lease(key)


def attach_cleanup_error(error: BaseException, cleanup: GPMCleanupError) -> None:
    """Record a cleanup failure on the original error without replacing or chaining it."""
    try:
        error.cleanup_error = cleanup  # type: ignore[attr-defined]
    except (AttributeError, TypeError):
        error.add_note(CLEANUP_NOTE)


async def run_bounded_cleanup(
    cleanup: Coroutine[Any, Any, E | None],
    *,
    failure: Callable[[], E],
    timeout: float = 10.0,  # noqa: ASYNC109 - a deadline for asyncio.wait, not asyncio.timeout
) -> tuple[E | None, bool]:
    """Run ``cleanup`` to completion even if the caller is cancelled, within ``timeout`` seconds.

    Returns ``(error, was_cancelled)``; ``failure()`` builds the error when the cleanup raises or
    hits the deadline. Cancellation requests received meanwhile are
    remembered, not acted on, so the caller can re-raise after cleanup. At the deadline the
    cleanup task is cancelled and awaited, never left running in the background.
    """
    task = asyncio.ensure_future(cleanup)
    deadline = time.monotonic() + timeout
    was_cancelled = False
    while not task.done():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            await asyncio.wait({task}, timeout=remaining)
        except asyncio.CancelledError:
            was_cancelled = True
    if not task.done():
        task.cancel()
        while not task.done():
            try:
                await asyncio.wait({task})
            except asyncio.CancelledError:
                was_cancelled = True
    if task.cancelled():
        return failure(), was_cancelled
    if task.exception() is not None:
        return failure(), was_cancelled
    return task.result(), was_cancelled
