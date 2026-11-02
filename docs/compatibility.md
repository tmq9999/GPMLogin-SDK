# Compatibility and verification status

This page separates what is **documented**, what is **mocked**, and what has been **live**
verified. Nothing here has been verified against a real GPM Login build.

## Documented (source: `GPM Login API Documentation.md`)

The SDK implements the 20 endpoints in that file and nothing else. Paths, methods, query and body
names come from it. Response fields not listed there are kept as untyped `extra` data, and
`profiles.update` returns `ProfileUpdated` because the document gives no stable response schema.

## Mocked (offline test suite)

`python -m pytest tests/unit tests/contract` runs every request through `httpx.MockTransport`.
These are contract tests of the SDK, not evidence that GPM behaves the same. They cover wire
format, sync/async parity for all 20 operations, error privacy, sessions, cancellation, and
the Playwright adapter against fake objects.

## Live (needs a real GPM Login)

Not run. `tests/integration` is opt-in and skipped by default:

| Variable | Enables |
|---|---|
| `GPM_RUN_LIVE=1` | Read-only checks: list profiles, browser versions, extensions |
| `GPM_RUN_LIVE_MUTATIONS=1` | Create, update, start, stop and soft-delete of a profile the test itself creates |
| `GPM_RUN_LIVE_SHARED_MUTATIONS=1` | Group and proxy create/update/delete of records the test creates |

Set `GPM_API_PORT` explicitly. The tests never look for or touch existing profiles, never hard
delete, and never change extension state. Record the GPM build and date here when you run them:
build: _not run_.

## Playwright CDP spike

Checked on 2026-11-02 with playwright 1.64.1, Python 3.13.13, Windows 11. Only the Playwright
driver was started; no browser binary and no GPM were used.

- `connect_over_cdp` to a closed local port (both `ws://` and `http://` endpoints, sync and async)
  raised `playwright.Error` (not `TimeoutError`) with a message containing
  `connect ECONNREFUSED 127.0.0.1:<port>`. There is no error code, so the adapter retries only
  when a non-timeout `Error` contains `ECONNREFUSED`.
- The `timeout` argument of `connect_over_cdp` is in milliseconds.

Unverified: a real Chromium or GPM Chrome connect and disconnect, readiness failures, the texts of
auth or protocol errors, error texts on other operating systems, and what `browser.close()` does
to a GPM-managed browser beyond disconnecting. Treat the adapter as unverified against live
browsers until you have run it.

## Versions used for the offline run

| Item | Version |
|---|---|
| Python | 3.13.13 only (3.11 and 3.12 are claimed by metadata, not tested here) |
| httpx | 0.28.1 |
| playwright (optional) | 1.64.1 |
| pytest / pytest-asyncio | 9.2.0 / 1.4.1 |
| ruff / mypy | 0.17.3 / 2.4.1 |

## Async scope

The async client targets `asyncio` only (it uses `asyncio` tasks for bounded cleanup). Trio and
AnyIO-on-Trio are not supported in v1. Python 3.11 is the lowest supported version.
