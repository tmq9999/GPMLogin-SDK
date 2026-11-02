# Usage

## Configuration

`GPMClient(host=None, port=None, port_file=None, timeout=None, http_client=None)`; the async client
takes the same arguments. Hosts are limited to `localhost` and `127.0.0.1`.

Port precedence, first match wins and only that source is read (a bad chosen source raises
`GPMConfigurationError` instead of falling through):

1. the `port` argument
2. `GPM_API_PORT`
3. a port file: the `port_file` argument or `GPM_HTTP_PORT_FILE`
4. `9495`

`GPM_API_HOST` and `GPM_API_TIMEOUT_SECONDS` set the host and the default timeout (30 s).
Constructing a client does no network I/O.

## Injecting an HTTP client

Pass `http_client=httpx.Client(...)` (or `httpx.AsyncClient`) to control transport, for example in
tests with `httpx.MockTransport`. An injected client is never closed by the SDK. Configure it with
`trust_env=False` and without redirects, as the SDK-owned client does. A client the SDK created
itself is closed by `close()` / `aclose()` or the `with` block.

## Errors

Every SDK error derives from `GPMError`. Messages are fixed text: they never echo your input or
the vendor's `message`, and raw HTTPX exceptions are not chained.

| Error | Meaning |
|---|---|
| `GPMValidationError` | Rejected before any request (`.field` names the contract field) |
| `GPMTransportError` / `GPMTimeoutError` | Connection or timeout failure |
| `GPMHTTPError` | Non-2xx HTTP status (redirects are not followed) |
| `GPMAPIError` | Envelope said `success: false` |
| `GPMProtocolError` | Response did not match the contract (`.success_confirmed`) |
| `GPMProfileBusyError` | This process already owns that profile |
| `GPMCleanupError` | The session could not confirm the profile stopped |
| `GPMIntegrationError` | Playwright missing or the attachment failed |

For mutating operations, `state_uncertain=True` on a transport, timeout, HTTP or protocol error means
GPM may have applied the change. Note that start, stop, delete and extension state are GET requests
but still count as mutating. Nothing is retried, so reconcile the state yourself. A `GPMProtocolError` with
`success_confirmed=True` means GPM said the call succeeded but its data was unusable, so a create or
update may well have been applied even though `state_uncertain` is False.

## Logging

Error messages and the SDK's own logs never contain request values. HTTPX logs each request URL
at INFO on the `httpx` logger; the SDK installs a filter on that logger that removes the query
string from GPM API URLs (search text, launch arguments). Other URLs are not changed. If you
configure your own HTTPX logging or transport hooks, keep query strings out of them too.

## Pagination and lookup

`list(page=, page_size=, search=, sort=)` returns a `Page`. `iter_all()` yields every item lazily,
one request per page. A server that answers with a different page than requested raises
`GPMProtocolError`; there is no snapshot guarantee if data changes while you iterate.

`find_by_name(name)` (profiles, groups) is exact and case-sensitive, scans all pages, and returns
`None` when nothing matches. Two different ids with the same name raise
`GPMAmbiguousMatchError`; the SDK never picks one.

## Sending fields: omitted, null, empty

Fields you leave out of a request dict are omitted from the request. Query parameters set to `None`
are dropped; `False`, `0` and `""` are kept. JSON body values of `None` are sent as `null`. An empty
string is an explicit value, for example `raw_proxy=""` clears a profile's proxy.
`build_start_options()` and `join_startup_urls()` follow the same rule: only what you pass is sent.

## Proxy helpers and the rename race

`profiles.update` always needs `name`. `set_proxy` / `clear_proxy` therefore do a `get` first to
reuse the current name unless you pass `name=`, then one `update`. These are two requests, not a
transaction: a rename by someone else in between is overwritten (a race). Pass `name=` to skip
the read. `proxies.*` is the shared proxy store and is separate from a profile's own `raw_proxy`.

## Deleting

`profiles.soft_delete` marks a profile deleted. `profiles.hard_delete`, `groups.delete` and
`proxies.delete` erase data and need `confirm=True`; anything else raises `GPMValidationError`
before a request. Sessions never delete.

## Extensions

`extensions.set_state(id, active=..., group_ids=None)`: `group_ids=None` is global scope and
changes the extension for every group. Pass a non-empty list to limit it. There is no live test
for this by default.

## Sessions, cleanup and cancellation

`profile_session(profile_id, exclusive=True, start_options=None)`:

- Start succeeds, block runs, stop is sent once. Failure to stop raises `GPMCleanupError`; if your
  block also failed, your error is kept and `error.cleanup_error` holds the cleanup failure.
- If start returns `success: true` with an unusable payload, the profile is stopped once and the
  `GPMProtocolError` is raised.
- If start fails or times out, nothing is stopped and nothing is retried.
- The stop request uses at most 10 s. In asyncio, if the task is cancelled the stop still runs to
  completion (or the 10 s deadline), then `CancelledError` is re-raised. The lock is released
  only afterwards.
- Entering a second session for the same profile in this process raises `GPMProfileBusyError`
  at once. `localhost` and `127.0.0.1` are the same host for this check.

## Playwright

`integrations.playwright.connect(launch, playwright, browser_kind=BrowserType.CHROME)` attaches
over CDP to the existing default context and detaches on exit. It never stops the profile or
your Playwright instance. Use a dedicated Chrome profile; Firefox is rejected. Connection
retries happen only while the port refuses connections (up to `timeout_ms`, default 10 s, every
250 ms); every other failure is raised at once.
