from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest

from gpmlogin_sdk import GPMCleanupError, GPMError, GPMProfileBusyError, _ownership
from gpmlogin_sdk._ownership import (
    acquire_profile,
    attach_cleanup_error,
    run_bounded_cleanup,
)

KEY = ("127.0.0.1", 9495)


@pytest.fixture(autouse=True)
def clean_registry() -> Any:
    assert set() == _ownership._HELD
    yield
    leaked = set(_ownership._HELD)
    _ownership._HELD.clear()
    assert leaked == set(), "a test leaked a profile lease"


def test_second_acquire_for_the_same_key_fails_fast_and_release_frees_it() -> None:
    lease = acquire_profile(KEY, "p1")
    with pytest.raises(GPMProfileBusyError):
        acquire_profile(KEY, "p1")
    lease.release()
    acquire_profile(KEY, "p1").release()


def test_release_is_idempotent_and_a_stale_lease_cannot_free_a_newer_one() -> None:
    first = acquire_profile(KEY, "p1")
    first.release()
    second = acquire_profile(KEY, "p1")
    first.release()
    with pytest.raises(GPMProfileBusyError):
        acquire_profile(KEY, "p1")
    second.release()
    second.release()


def test_other_profiles_and_other_ports_do_not_contend() -> None:
    leases = [
        acquire_profile(KEY, "p1"),
        acquire_profile(KEY, "p2"),
        acquire_profile(("127.0.0.1", 9496), "p1"),
    ]
    for lease in leases:
        lease.release()


def test_busy_error_does_not_echo_the_profile_id() -> None:
    lease = acquire_profile(KEY, "secret-profile-id")
    try:
        with pytest.raises(GPMProfileBusyError) as caught:
            acquire_profile(KEY, "secret-profile-id")
        assert "secret-profile-id" not in str(caught.value)
    finally:
        lease.release()


def test_exactly_one_thread_wins_a_race_for_the_same_profile() -> None:
    barrier = threading.Barrier(16)
    winners: list[object] = []
    losers: list[int] = []

    def worker() -> None:
        barrier.wait()
        try:
            winners.append(acquire_profile(KEY, "race"))
        except GPMProfileBusyError:
            losers.append(1)

    threads = [threading.Thread(target=worker) for _ in range(16)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(winners) == 1
    assert len(losers) == 15
    winners[0].release()  # type: ignore[attr-defined]


def test_cleanup_error_defaults_to_none_on_every_gpm_error() -> None:
    assert GPMError.cleanup_error is None
    assert GPMError().cleanup_error is None


def test_attach_sets_the_attribute_when_it_can() -> None:
    task_error = ValueError("boom")
    cleanup = GPMCleanupError()
    attach_cleanup_error(task_error, cleanup)
    assert task_error.cleanup_error is cleanup  # type: ignore[attr-defined]


def test_attach_adds_a_safe_note_when_the_attribute_cannot_be_set() -> None:
    class Locked(Exception):
        def __setattr__(self, name: str, value: object) -> None:
            if name == "cleanup_error":
                raise AttributeError(name)
            super().__setattr__(name, value)

    task_error = Locked("boom")
    attach_cleanup_error(task_error, GPMCleanupError())
    assert any("cleanup" in note.lower() for note in task_error.__notes__)


def test_cleanup_error_message_is_fixed_text() -> None:
    assert "stop" in str(GPMCleanupError()).lower()
    assert GPMCleanupError().stop_error is None


@pytest.mark.asyncio
async def test_bounded_cleanup_returns_the_cleanup_result() -> None:
    async def ok() -> GPMCleanupError | None:
        return None

    assert await run_bounded_cleanup(ok(), failure=GPMCleanupError) == (None, False)

    failure = GPMCleanupError()

    async def bad() -> GPMCleanupError | None:
        return failure

    assert await run_bounded_cleanup(bad(), failure=GPMCleanupError) == (failure, False)


@pytest.mark.asyncio
async def test_bounded_cleanup_survives_repeated_cancellation_and_reports_it() -> None:
    gate = asyncio.Event()
    started = asyncio.Event()
    finished: list[str] = []

    async def cleanup() -> GPMCleanupError | None:
        started.set()
        await gate.wait()
        finished.append("done")
        return None

    runner = asyncio.create_task(run_bounded_cleanup(cleanup(), failure=GPMCleanupError))
    await started.wait()
    runner.cancel()
    await asyncio.sleep(0)
    runner.cancel()
    await asyncio.sleep(0)
    assert not runner.done()
    assert finished == []
    gate.set()
    result = await runner
    assert result == (None, True)
    assert finished == ["done"]


@pytest.mark.asyncio
async def test_bounded_cleanup_cancels_and_awaits_the_task_at_the_deadline() -> None:
    started = asyncio.Event()
    cancelled: list[str] = []

    async def hangs() -> GPMCleanupError | None:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.append("cancelled")
            raise
        return None

    error, was_cancelled = await run_bounded_cleanup(hangs(), failure=GPMCleanupError, timeout=0.05)
    assert isinstance(error, GPMCleanupError)
    assert was_cancelled is False
    assert cancelled == ["cancelled"]


@pytest.mark.asyncio
async def test_bounded_cleanup_turns_an_unexpected_exception_into_a_cleanup_error() -> None:
    async def explodes() -> GPMCleanupError | None:
        raise RuntimeError("raw vendor text")

    error, _ = await run_bounded_cleanup(explodes(), failure=GPMCleanupError)
    assert isinstance(error, GPMCleanupError)
    assert "raw vendor text" not in str(error)


@pytest.mark.asyncio
async def test_bounded_cleanup_uses_the_caller_supplied_failure_type() -> None:
    from gpmlogin_sdk import GPMIntegrationError

    async def explodes() -> GPMIntegrationError | None:
        raise RuntimeError("raw")

    error, _ = await run_bounded_cleanup(explodes(), failure=GPMIntegrationError)
    assert type(error) is GPMIntegrationError
