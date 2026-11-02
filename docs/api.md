# API reference

Both clients expose the same resources: `profiles`, `groups`, `proxies`, `extensions`, `browsers`.
The async client has the same method names; every call except `iter_all` is awaited. `iter_all`
returns an `AsyncIterator` and is used with `async for` without `await`.

## Endpoint table (20 of 20)

| Endpoint | SDK method | Notes |
|---|---|---|
| `GET /profiles` | `profiles.list` | Paged |
| `GET /profiles/{id}` | `profiles.get` | |
| `POST /profiles/create` | `profiles.create` | `name` required |
| `POST /profiles/update/{id}` | `profiles.update` | Response is `ProfileUpdated` |
| `GET /profiles/delete/{id}` | `profiles.soft_delete` | `mode=soft`; hard delete is `profiles.hard_delete(confirm=True)` |
| `GET /profiles/start/{id}` | `profiles.start` | Mutating despite GET |
| `GET /profiles/stop/{id}` | `profiles.stop` | Mutating despite GET |
| `GET /browsers/versions` | `browsers.versions` | |
| `GET /groups` | `groups.list` | Paged |
| `GET /groups/{id}` | `groups.get` | |
| `POST /groups/create` | `groups.create` | |
| `POST /groups/update/{id}` | `groups.update` | |
| `GET /groups/delete/{id}` | `groups.delete` | `confirm=True` |
| `GET /proxies` | `proxies.list` | Paged |
| `GET /proxies/{id}` | `proxies.get` | |
| `POST /proxies/create` | `proxies.create` | |
| `POST /proxies/update/{id}` | `proxies.update` | |
| `GET /proxies/delete/{id}` | `proxies.delete` | `confirm=True` |
| `GET /extensions` | `extensions.list` | |
| `GET /extensions/update-state/{id}` | `extensions.set_state` | Global scope when `group_ids=None` |

Every method above is a single HTTP request with no retries.

The rows use the form `` `METHOD /path` | `resource.method` `` and are checked against the
documented endpoint list by the test suite.

## Signatures (blocking client)

```text
GPMClient(*, host=None, port=None, port_file=None, timeout=None, http_client=None)
AsyncGPMClient(*, host=None, port=None, port_file=None, timeout=None, http_client=None)

profiles.list(*, page=1, page_size=30, search=None, sort=SortOrder.NEWEST) -> Page[ProfileSummary]
profiles.get(profile_id) -> ProfileDetails
profiles.create(body: CreateProfileRequest) -> ProfileCreated
profiles.update(profile_id, body: UpdateProfileRequest) -> ProfileUpdated
profiles.soft_delete(profile_id) -> None
profiles.hard_delete(profile_id, *, confirm=False) -> None
profiles.start(profile_id, options: StartOptions | None = None) -> StartResult
profiles.stop(profile_id) -> None
profiles.iter_all(*, page_size=30, search=None, sort=SortOrder.NEWEST) -> Iterator[ProfileSummary]
profiles.find_by_name(name) -> ProfileSummary | None
profiles.set_proxy(profile_id, raw_proxy, *, name=None) -> ProfileUpdated
profiles.clear_proxy(profile_id, *, name=None) -> ProfileUpdated

groups.list(*, page=1, page_size=30, search=None, sort=SortOrder.NEWEST) -> Page[Group]
groups.get(group_id) -> Group
groups.create(name, *, sort_order=0) -> Group
groups.update(group_id, *, name, sort_order=None) -> Group
groups.delete(group_id, *, confirm=False) -> None
groups.iter_all(...) -> Iterator[Group]
groups.find_by_name(name) -> Group | None

proxies.list(*, page=1, page_size=30, search=None, sort=SortOrder.NEWEST) -> Page[Proxy]
proxies.get(proxy_id) -> Proxy
proxies.create(raw_proxy) -> Proxy
proxies.update(proxy_id, raw_proxy) -> Proxy
proxies.delete(proxy_id, *, confirm=False) -> None
proxies.iter_all(...) -> Iterator[Proxy]

extensions.list() -> list[Extension]
extensions.set_state(extension_id, *, active, group_ids=None) -> None
browsers.versions() -> BrowserVersions

client.profile_session(profile_id, *, exclusive=False, start_options=None)
    -> context manager yielding ProfileSession(profile_id, launch)   # exclusive must be True
```

## Helpers

- `build_start_options(*, window_size, window_pos, window_scale, remote_debugging_port,
  skip_proxy_check, addition_args) -> StartOptions`
- `join_startup_urls(urls) -> str`
- `gpmlogin_sdk.integrations.playwright.connect(launch, playwright, *, browser_kind,
  timeout_ms=10000)` and `connect_async(...)`. Attachments have `.browser`, `.context` and
  `get_or_create_page()`.

Models are frozen dataclasses. Fields that can hold credentials, paths or endpoints (for example
`raw_proxy`, `storage_path`, `websocket_debugging_url`) and unknown vendor fields in `extra` are
hidden from `repr`.
