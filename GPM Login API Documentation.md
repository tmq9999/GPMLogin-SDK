# GPM Login API Documentation

> **Integration reference for AI coding agents and software developers**  
> Source: [GPM Login — Official Local API Documentation](https://gpmlogin.com/doc)  
> Documentation reviewed: **2026-11-02**  
> Scope: the **GPM Login local HTTP API (`/api/v1`)** described on the linked official page.  
> Status: **Documentation-derived, not live-tested against a running GPM Login instance.**

## 1. How an AI Agent Should Use This Document

This is an implementation-oriented reference for creating clients, automation workflows, and browser integrations with GPM Login.

**Agent implementation rules:**

1. Use the exact HTTP methods, endpoint paths, and parameter spellings listed here. Some destructive operations intentionally use `GET`, and the launch option is spelled `addition_args` (not `additional_args`).
2. Treat `success: true` in the JSON response as application-level success; do not assume HTTP 2xx alone is sufficient.
3. Read the actual `data` object and validate required properties before using them. Treat undocumented fields and error details as unknown.
4. Use the runtime-discovered API port when it differs from 9495; do not permanently assume that 9495 is available.
5. Use a **Chromium/Chrome** profile for Playwright CDP automation. Do not assume the Firefox profile can be attached using Playwright's Chromium CDP connector.
6. Treat `raw_proxy` as secret-bearing data if it contains credentials. Never log it verbatim or commit it to source control.
7. Never permanently delete a profile or its disk data without the caller's explicit consent. Prefer soft deletion for recoverability.
8. Do not expose the local HTTP API or browser debugging port publicly. The official API is designed for access from the same machine.
9. When the vendor documentation conflicts with itself, note the discrepancy and verify behavior against the installed app before relying on it.
10. Separate **vendor-confirmed API facts** from the **implementation examples and recommendations** supplied in this file.

## 2. Local API Architecture

```text
AI agent / Python / Node.js application
                |
                | HTTP JSON requests
                v
      http://127.0.0.1:<PORT>/api/v1
                |
                v
       GPM Login desktop application
                |
                | start profile
                v
          Managed browser process
                |
                | CDP debugging port / WebSocket URL
                v
     Playwright / Puppeteer / Selenium
```

### 2.1 Base URL and port

Default base URL:

```text
http://127.0.0.1:9495/api/v1
```

Equivalent documented hostname:

```text
http://localhost:9495/api/v1
```

- Default port: **9495**.
- If occupied, GPM Login picks another available port within **8000–10000**.
- GPM Login writes the selected port into a file named **`http.port`** in its application-local data directory.
- The vendor page does **not** specify an absolute, cross-platform path to `http.port`. Configure that file path explicitly, discover it from the installed application, or allow users to set `GPM_API_PORT`.
- The API only accepts requests from `localhost` / `127.0.0.1` according to the official documentation, so no API token is required for these local requests.

Suggested configuration:

```env
GPM_API_HOST=127.0.0.1
GPM_API_PORT=9495
GPM_API_TIMEOUT_SECONDS=30
```

**Deployment note:** If your script runs in a remote VPS, container, or a different host, `127.0.0.1` refers to that script's own network environment, not automatically to the machine running GPM Login. Run the agent on the GPM host or design a deliberately secured local-access bridge. Never expose the unauthenticated API or CDP port directly to the public internet.

### 2.2 Request format

- Query parameters: URL query string.
- Create/update operations: JSON request body, typically with `Content-Type: application/json`.
- Paths are relative to `/api/v1`.
- The vendor does not document a required API key, bearer token, or authentication header for local access.

### 2.3 Common response envelope

All documented operations use a JSON wrapper resembling:

```json
{
  "success": true,
  "data": {},
  "message": "OK",
  "sender": "GPMLogin Global v1.0.0"
}
```

Suggested client-side type:

```ts
interface GpmResponse<T> {
  success: boolean;
  data: T | null;
  message: string;
  sender: string;
}
```

**Important:** The `sender` value in examples is not a substitute for version discovery, and the official page does not specify a stable error schema, error status-code mapping, or rate limit. Preserve raw error metadata in diagnostics without leaking secrets.

### 2.4 Paginated collection result

Used by profiles, groups, and proxies lists:

```json
{
  "current_page": 1,
  "per_page": 30,
  "total": 120,
  "last_page": 4,
  "data": []
}
```

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `page` | integer | `1` | Requested page number |
| `page_size` | integer | `30` | Page size |
| `search` | string | — | Entity-specific search text |
| `sort` | integer | `0` | Ordering selection |

Sort values:

| `sort` | Ordering |
|---:|---|
| `0` | Newest first |
| `1` | Oldest first |
| `2` | Name A–Z |
| `3` | Name Z–A |

```ts
interface Page<T> {
  current_page: number;
  per_page: number;
  total: number;
  last_page: number;
  data: T[];
}
```

## 3. Endpoint Index

All paths below are relative to `http://127.0.0.1:<PORT>` and include `/api/v1`.

| Method | Endpoint | Operation | Risk |
|---|---|---|---|
| `GET` | `/api/v1/profiles` | List profiles | Read |
| `GET` | `/api/v1/profiles/{id}` | Get profile, including fingerprint | Read |
| `POST` | `/api/v1/profiles/create` | Create a profile | Write |
| `POST` | `/api/v1/profiles/update/{id}` | Partially update a profile | Write |
| `GET` | `/api/v1/profiles/delete/{id}` | Soft/hard delete a profile | **Destructive** |
| `GET` | `/api/v1/profiles/start/{id}` | Start a profile browser | Process state |
| `GET` | `/api/v1/profiles/stop/{id}` | Stop a profile browser | Process state |
| `GET` | `/api/v1/browsers/versions` | Get available browser versions | Read |
| `GET` | `/api/v1/groups` | List groups | Read |
| `GET` | `/api/v1/groups/{id}` | Get a group | Read |
| `POST` | `/api/v1/groups/create` | Create a group | Write |
| `POST` | `/api/v1/groups/update/{id}` | Update a group | Write |
| `GET` | `/api/v1/groups/delete/{id}` | Delete a group | **Destructive** |
| `GET` | `/api/v1/proxies` | List shared proxies | Read/sensitive |
| `GET` | `/api/v1/proxies/{id}` | Get a proxy | Read/sensitive |
| `POST` | `/api/v1/proxies/create` | Add proxy | Write |
| `POST` | `/api/v1/proxies/update/{id}` | Change proxy | Write |
| `GET` | `/api/v1/proxies/delete/{id}` | Delete proxy | **Destructive** |
| `GET` | `/api/v1/extensions` | List installed extensions | Read |
| `GET` | `/api/v1/extensions/update-state/{id}` | Enable/disable extension | Write |

Total: **20 documented endpoints**.

## 4. Profiles API

### 4.1 `GET /api/v1/profiles` — List profiles

Parameters: `page`, `page_size`, `search` (searches profile name), `sort`.

```http
GET /api/v1/profiles?page=1&page_size=30&sort=0&search=Test HTTP/1.1
Host: 127.0.0.1:9495
```

Example response (illustrative subset of officially documented fields):

```json
{
  "success": true,
  "data": {
    "current_page": 1,
    "per_page": 30,
    "total": 1,
    "last_page": 1,
    "data": [
      {
        "id": "37f783ac-2635-4d53-ab8d-a300c790ecdc",
        "name": "Profile 01",
        "group_id": "all",
        "storage_path": "C:\\GPMLogin\\profiles\\37f7...",
        "raw_proxy": "socks5://127.0.0.1:5000",
        "browser": { "name": "chrome", "version": "137.0.7151.41" },
        "os": "windows",
        "note": "",
        "created_at": "2026-06-08 10:00:00",
        "updated_at": "2026-06-08 10:00:00",
        "tags": []
      }
    ]
  },
  "message": "OK",
  "sender": "GPMLogin Global v1.0.0"
}
```

**Agent note:** The list intentionally omits the full fingerprint; call the single-profile endpoint when fingerprint details are needed.

### 4.2 `GET /api/v1/profiles/{id}` — Get profile details

Path parameter: `id` (string, required).

```http
GET /api/v1/profiles/37f783ac-2635-4d53-ab8d-a300c790ecdc HTTP/1.1
Host: 127.0.0.1:9495
```

Returned `data` includes a profile `id`, `name`, `group_id`, `raw_proxy`, `browser`, `os`, and `fingerprint`. The official page shows the `fingerprint` field as a placeholder rather than a full schema; do not assume its internal keys.

### 4.3 `POST /api/v1/profiles/create` — Create profile

**Required JSON field:** `name` (string). Other fields may be omitted or `null` to use defaults; the vendor states fingerprint values are randomized when unspecified.

```bash
curl -X POST 'http://127.0.0.1:9495/api/v1/profiles/create' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Automation Profile",
    "browser_type": 1,
    "os_type": 1,
    "canvas_mode": 1,
    "timezone_base_on_ip": true,
    "is_language_base_on_ip": true
  }'
```

Example success `data`:

```json
{
  "id": "69911f98-...",
  "name": "Automation Profile"
}
```

The `id` shown is an abbreviated example, **not** an ID to send to the API. Use the ID returned by the running application.

### 4.4 `POST /api/v1/profiles/update/{id}` — Update profile

Path parameter: `id` (string, required). Body supports the same settings as create. The introductory description says omitted or `null` fields preserve current values, while the published shared parameter table still marks `name` as required. **Treat this as a documentation inconsistency**: for maximal compatibility include `name` when known, or test whether it can be omitted in your installed version.

```json
{
  "name": "Updated Automation Profile",
  "raw_proxy": "socks5://127.0.0.1:5000",
  "note": "Managed by automation"
}
```

**Important update semantics:** `null`/omitted means preserve an existing setting (according to the update overview). An empty string may have a different meaning; for `raw_proxy`, an empty string is explicitly documented as *no proxy*. Do not assume that `null` clears a value.

### 4.5 Complete create/update settings reference

The following are the **exact request keys** from the official page. Except `name` on create, fields are optional.

| JSON key | Type | Supported values / behavior |
|---|---|---|
| `name` | string | Profile name; required on create |
| `group_id` | string or null | Default group on create; keep current group on update when omitted/null |
| `raw_proxy` | string | Proxy URL/string; `""` represents no proxy |
| `bypass_proxy_extensions` | string | Domains that bypass the proxy; delimiter format not documented |
| `browser_type` | enum | `1` Chrome; `2` Firefox; string names supported where applicable |
| `browser_version` | string | Installed/supported browser version; inspect versions endpoint |
| `os_type` | enum | `1` Windows; `2` macOS Intel; `3` macOS ARM; `4` Linux; `5` Android |
| `custom_user_agent` | string | Override User-Agent manually |
| `task_bar_title` | string | Window title shown on taskbar |
| `webrtc_mode` | enum | `1` IP-based; `2` Fixed; `3` Real; `4` Disabled |
| `fixed_webrtc_public_ip` | string | Required if `webrtc_mode=2` |
| `port_protect` | string | Port-scan protection setting; specific syntax not documented |
| `geolocation_mode` | enum | `1` Allow; `2` Prompt; `3` Block |
| `canvas_mode` | enum | `1` Noise; `2` Real; `3` Block |
| `client_rect_mode` | enum | `1` Noise; `2` Real |
| `webgl_image_mode` | enum | `1` Noise; `2` Real |
| `webgl_metadata_mode` | enum | `1` Masked; `2` Real |
| `audio_mode` | enum | `1` Noise; `2` Real |
| `is_masked_media` | boolean | `true` masks camera, microphone, speaker device details; default `false` |
| `font_mode` | enum | `1` Masked; `2` Real |
| `timezone_base_on_ip` | boolean | Default `true` |
| `timezone` | string | Fixed IANA timezone, e.g. `Asia/Ho_Chi_Minh`, when `timezone_base_on_ip=false` |
| `is_language_base_on_ip` | boolean | Default `true` |
| `fixed_language` | string | Language code such as `vi`, `en`, `zh` |
| `startup_urls` | string | Multiple URLs separated by **newline characters** |
| `note` | string or null | Free-form note |

Enum keys often accept an integer or a supported string name, but the full list of accepted string spellings is not documented. **Use numeric enum values for predictable interoperability.**

Examples of conditional settings:

```json
{
  "name": "Fixed Timezone Profile",
  "timezone_base_on_ip": false,
  "timezone": "Asia/Ho_Chi_Minh",
  "is_language_base_on_ip": false,
  "fixed_language": "en",
  "startup_urls": "https://example.com\nhttps://example.org"
}
```

```json
{
  "name": "Fixed WebRTC Profile",
  "webrtc_mode": 2,
  "fixed_webrtc_public_ip": "203.0.113.10"
}
```

The IP `203.0.113.10` is a documentation/test address, not a usable public proxy IP.

### 4.6 `GET /api/v1/profiles/delete/{id}` — Delete profile

Query parameter `mode`:

- `soft` (default): move profile to trash.
- `hard`: permanently erase the profile **and on-disk profile data**.

```http
GET /api/v1/profiles/delete/PROFILE_ID?mode=soft HTTP/1.1
Host: 127.0.0.1:9495
```

Success response uses `data: null`. Implement a hard-delete safety confirmation in interactive tools, and never infer permission to hard-delete from a generic cleanup request.

### 4.7 `GET /api/v1/profiles/start/{id}` — Launch browser

Optional query parameters:

| Name | Type | Default | Notes |
|---|---|---|---|
| `remote_debugging_port` | integer | Random available port | Explicit CDP port if desired |
| `window_scale` | number | `1` | Example `0.8` |
| `window_pos` | string | — | `x,y`, e.g. `100,100` |
| `window_size` | string | — | `width,height`, e.g. `800,600` |
| `skip_proxy_check` | boolean | `false` | Skip proxy test before launch |
| `addition_args` | string | — | Extra Chromium flags, e.g. `--mute-audio` |

**Spelling matters:** `addition_args` is the documented parameter name.

```http
GET /api/v1/profiles/start/PROFILE_ID?window_size=1280%2C800&window_pos=100%2C100 HTTP/1.1
Host: 127.0.0.1:9495
```

Representative response from official schema:

```json
{
  "success": true,
  "data": {
    "profile_id": "7798d4ca-a002-4a52-9223-5140c68667bc",
    "driver_path": "C:\\GPMLogin\\drivers\\chromedriver.exe",
    "remote_debugging_port": 40444,
    "websocket_debugging_url": "ws://127.0.0.1:40444/devtools/browser/abc-123",
    "addition_info": {
      "process_id": 12345,
      "profile_name": "Profile 01",
      "window_handle": 1180736,
      "exec_time": 1200
    }
  },
  "message": "OK",
  "sender": "GPMLogin Global v1.0.0"
}
```

The returned port and WebSocket URL are **runtime values**. Never hard-code `40444` or the WebSocket path. `driver_path` is intended for integrations such as Selenium; Chromium CDP clients can use the debugging port or WebSocket URL.

### 4.8 `GET /api/v1/profiles/stop/{id}` — Stop browser

```http
GET /api/v1/profiles/stop/PROFILE_ID HTTP/1.1
Host: 127.0.0.1:9495
```

Success response has `data: null`.

**Lifecycle recommendation:** Start → attach automation → run task → dispose of automation connection → call GPM stop. Ensure stop is attempted in a `finally` block when the automation owns the browser lifecycle. Do not stop a browser owned by another concurrent worker.

## 5. Browser Versions API

### `GET /api/v1/browsers/versions`

Returns available versions for the `browser_version` field. The documented `data` shape is:

```json
{
  "chromium": ["137.0.7151.41", "136.0.7103.93"],
  "firefox": ["128.0", "127.0"]
}
```

These versions are **illustrative entries from the docs**, not guaranteed to exist on every installation. Query at runtime before choosing a specific version. Chrome profile type is `1`, whereas the version-list key is named `chromium` in the documented response.

## 6. Groups API

Groups organize profiles.

| Method | Path | Parameters/body | Result |
|---|---|---|---|
| GET | `/api/v1/groups` | `page`, `page_size`, `search` (name), `sort` | `Page<Group>` |
| GET | `/api/v1/groups/{id}` | `id` in path | Single group |
| POST | `/api/v1/groups/create` | JSON: `name` required, `sort_order` optional (default `0`) | Created group |
| POST | `/api/v1/groups/update/{id}` | JSON: `name` required per table, `sort_order` optional | Updated group |
| GET | `/api/v1/groups/delete/{id}` | `id` in path | `data: null` on success |

Example group representation:

```json
{
  "id": "67db46f9-...",
  "name": "Marketing",
  "sort_order": 1
}
```

Create request:

```json
{ "name": "Automation", "sort_order": 10 }
```

Update request:

```json
{ "name": "Automation - Updated", "sort_order": 5 }
```

`sort_order` is an integer; lower numbers appear higher in the list. **On update, the official text says `sort_order` takes effect only when greater than 0**, so do not assume that sending `0` reorders a group.

## 7. Proxies API

This API manages a **shared proxy store**. It is distinct from setting a profile's `raw_proxy` directly.

| Method | Path | Parameters/body | Result |
|---|---|---|---|
| GET | `/api/v1/proxies` | `page`, `page_size`, `search` (proxy string), `sort` | `Page<Proxy>` |
| GET | `/api/v1/proxies/{id}` | `id` in path | Single proxy |
| POST | `/api/v1/proxies/create` | JSON `raw_proxy` required | Created proxy |
| POST | `/api/v1/proxies/update/{id}` | JSON `raw_proxy` required | Updated proxy |
| GET | `/api/v1/proxies/delete/{id}` | `id` in path | `data: null` on success |

Officially supported `raw_proxy` input forms include:

```text
ip:port
ip:port:user:pass
http://host:port
http://user:password@host:port
socks5://host:port
socks5://user:password@host:port
```

The last credential-bearing SOCKS5/HTTP URL examples illustrate standard URL syntax; the official page explicitly lists `http://`, `socks5://`, and the colon-separated formats but does not enumerate every valid URL/auth combination. Confirm your specific credential format against the installed version.

Example create request:

```json
{ "raw_proxy": "socks5://127.0.0.1:5001" }
```

Example stored proxy:

```json
{
  "id": "a36a1e31-...",
  "raw_proxy": "socks5://127.0.0.1:5001",
  "meta_data": null,
  "tags": []
}
```

**Agent security requirements:** Mask proxy credentials in all logs, telemetry, exception output, and debug traces. Avoid printing results of `GET /proxies` directly. The official API does not document a special `proxy_id` field in the profile create/update body, so do not invent one.

## 8. Extensions API

### 8.1 `GET /api/v1/extensions` — List extensions

Unlike the other list endpoints, this returns an **array directly** inside `data`, not a paginated object.

```json
{
  "success": true,
  "data": [
    {
      "id": "9d30b2b55768f1051833465850725851",
      "name": "uBlock Origin",
      "version": "1.54.0",
      "is_active": true
    }
  ],
  "message": "OK",
  "sender": "GPMLogin Global v1.0.0"
}
```

### 8.2 `GET /api/v1/extensions/update-state/{id}` — Set extension state

| Query parameter | Type | Required | Meaning |
|---|---|---|---|
| `active` | boolean | Yes | `true` enables, `false` disables |
| `applied_group_ids` | string | No | Comma-separated group IDs. Omit for global scope |

Examples:

```text
GET /api/v1/extensions/update-state/EXTENSION_ID?active=true
GET /api/v1/extensions/update-state/EXTENSION_ID?active=false&applied_group_ids=GROUP_ID_1%2CGROUP_ID_2
```

Documented success message: `Extension state updated successfully`, with `data: null`.

**Important:** These are extension-enable/disable operations. No install, upload, remove, or per-profile extension installation endpoint is documented on the source page.

## 9. Python Client Example (requests)

The following is a **new implementation example**, not vendor-provided SDK code. It uses standard requests and the documented response envelope. Install dependency with `pip install requests`.

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests


class GpmApiError(RuntimeError):
    pass


@dataclass
class GpmClient:
    host: str = os.getenv("GPM_API_HOST", "127.0.0.1")
    port: int = int(os.getenv("GPM_API_PORT", "9495"))
    timeout: float = float(os.getenv("GPM_API_TIMEOUT_SECONDS", "30"))

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}/api/v1"

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        # Normalize booleans for query strings.
        query = {
            key: str(value).lower() if isinstance(value, bool) else value
            for key, value in (params or {}).items()
            if value is not None
        }
        response = requests.request(
            method,
            self.base_url + path,
            params=query,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        try:
            body = response.json()
        except ValueError as exc:
            raise GpmApiError("GPM returned a non-JSON response") from exc
        if not isinstance(body, dict) or body.get("success") is not True:
            message = body.get("message", "Unexpected GPM API response") if isinstance(body, dict) else "Unexpected GPM API response"
            raise GpmApiError(str(message))
        return body.get("data")

    def list_profiles(self, *, page: int = 1, page_size: int = 30) -> dict:
        return self.request("GET", "/profiles", params={"page": page, "page_size": page_size})

    def get_profile(self, profile_id: str) -> dict:
        return self.request("GET", f"/profiles/{profile_id}")

    def create_profile(self, name: str, **settings: Any) -> dict:
        return self.request("POST", "/profiles/create", payload={"name": name, **settings})

    def update_profile(self, profile_id: str, **settings: Any) -> dict:
        return self.request("POST", f"/profiles/update/{profile_id}", payload=settings)

    def start_profile(self, profile_id: str, **options: Any) -> dict:
        return self.request("GET", f"/profiles/start/{profile_id}", params=options)

    def stop_profile(self, profile_id: str) -> None:
        self.request("GET", f"/profiles/stop/{profile_id}")

    def soft_delete_profile(self, profile_id: str) -> None:
        self.request("GET", f"/profiles/delete/{profile_id}", params={"mode": "soft"})


if __name__ == "__main__":
    api = GpmClient()
    created = api.create_profile("Managed by Python", browser_type=1)
    profile_id = created["id"]
    print("Created profile ID:", profile_id)
    # Start only if desired. Do not hard-delete as routine cleanup.
```

### 9.1 Python + Playwright CDP attachment

Install: `pip install requests playwright` (and complete any normal Playwright setup required by your environment).

```python
from playwright.sync_api import sync_playwright

api = GpmClient()
profile = api.create_profile("CDP Example", browser_type=1)
profile_id = profile["id"]

started = False
try:
    launch = api.start_profile(profile_id)
    started = True
    port = launch["remote_debugging_port"]

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://example.com")
        print(page.title())
        browser.close()  # Release Playwright's connection.
finally:
    if started:
        api.stop_profile(profile_id)
```

**Operational cautions:**

- Import `GpmClient` from your client module or put both examples in one file.
- Attach to the **existing** persistent browser context returned by CDP; do not accidentally replace it with a blank, temporary context.
- The code assumes a Chrome/Chromium profile. Playwright Chromium CDP does not provide a generic attachment interface for the GPM Firefox profile.
- Start/stop behavior on already-running profiles, concurrency restrictions, and CDP error conditions are not fully described in the official page. Implement ownership checks in a multi-worker app.
- This example creates a profile and deliberately leaves it on disk for reuse or manual cleanup.

## 10. TypeScript / Node.js Example

The snippet below uses built-in `fetch` (Node.js 18+). It is **an integration example**, not official SDK code.

```ts
const API_BASE = `http://127.0.0.1:${process.env.GPM_API_PORT ?? "9495"}/api/v1`;

type GpmResponse<T> = {
  success: boolean;
  data: T | null;
  message: string;
  sender: string;
};

type StartResult = {
  profile_id: string;
  driver_path: string;
  remote_debugging_port: number;
  websocket_debugging_url: string;
  addition_info?: {
    process_id?: number;
    profile_name?: string;
    window_handle?: number;
    exec_time?: number;
  };
};

async function gpmRequest<T>(
  method: "GET" | "POST",
  path: string,
  options: { query?: Record<string, string | number | boolean>; body?: unknown } = {}
): Promise<T> {
  const url = new URL(API_BASE + path);
  for (const [key, value] of Object.entries(options.query ?? {})) {
    url.searchParams.set(key, String(value));
  }

  const response = await fetch(url, {
    method,
    headers: options.body === undefined ? undefined : { "Content-Type": "application/json" },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: AbortSignal.timeout(30_000),
  });

  if (!response.ok) throw new Error(`GPM HTTP error ${response.status}`);
  const payload = (await response.json()) as GpmResponse<T>;
  if (payload.success !== true) throw new Error(`GPM API error: ${payload.message}`);
  return payload.data as T;
}

async function createAndStartProfile() {
  const profile = await gpmRequest<{ id: string; name: string }>(
    "POST",
    "/profiles/create",
    { body: { name: "Node CDP Example", browser_type: 1 } }
  );
  const launch = await gpmRequest<StartResult>(
    "GET",
    `/profiles/start/${encodeURIComponent(profile.id)}`
  );
  return { profile, launch };
}
```

For a Playwright integration, install `npm install playwright` and connect using `chromium.connectOverCDP(launch.websocket_debugging_url)` or the HTTP endpoint constructed with `launch.remote_debugging_port`. Use an existing context (`browser.contexts()[0]`) rather than creating an unrelated persistent profile.

```ts
import { chromium } from "playwright";

const { profile, launch } = await createAndStartProfile();
try {
  const browser = await chromium.connectOverCDP(launch.websocket_debugging_url);
  const context = browser.contexts()[0];
  const page = context.pages()[0] ?? await context.newPage();
  await page.goto("https://example.com");
  console.log(await page.title());
  await browser.close();
} finally {
  await gpmRequest<null>("GET", `/profiles/stop/${encodeURIComponent(profile.id)}`);
}
```

The snippets assume that `createAndStartProfile` and `gpmRequest` are in scope or imported from a module. For production, do not silently ignore startup or cleanup errors.

## 11. Suggested Domain Types

The following types model the **documented portion** of returned objects. Additional fields may exist.

```ts
export interface GpmBrowserVersion {
  name: string;
  version: string;
}

export interface GpmProfileSummary {
  id: string;
  name: string;
  group_id?: string | null;
  storage_path?: string;
  raw_proxy?: string;
  browser?: GpmBrowserVersion;
  os?: string;
  note?: string | null;
  created_at?: string;
  updated_at?: string;
  tags?: unknown[];
}

export interface GpmProfileDetails extends GpmProfileSummary {
  fingerprint?: Record<string, unknown>; // Structure not officially specified.
}

export interface GpmGroup {
  id: string;
  name: string;
  sort_order: number;
}

export interface GpmProxy {
  id: string;
  raw_proxy: string;
  meta_data?: unknown;
  tags?: unknown[];
}

export interface GpmExtension {
  id: string;
  name: string;
  version: string;
  is_active: boolean;
}

export interface GpmBrowserVersions {
  chromium: string[];
  firefox: string[];
}
```

Prefer optional keys for partial responses. Define explicit request DTOs in real projects and validate them before sending, particularly enum values and conditional fields.

## 12. Recommended Automation Workflows

### 12.1 Standard browser automation

```text
1. Resolve local GPM API host + active port.
2. GET /browsers/versions if a specific browser version is required.
3. GET /profiles (search) or POST /profiles/create.
4. GET /profiles/start/{id} with optional window settings.
5. Parse remote_debugging_port or websocket_debugging_url.
6. Connect Playwright/Puppeteer/Selenium to the running browser.
7. Execute automation against the existing browser context.
8. Close the automation connection.
9. GET /profiles/stop/{id} if this job owns the browser lifecycle.
10. Keep the profile for reuse, unless explicitly instructed to delete it.
```

### 12.2 Grouped profile creation

```text
POST /groups/create      -> read data.id
POST /profiles/create    -> set group_id = returned ID
GET  /profiles           -> verify profile is listed
```

### 12.3 Proxy assignment to a profile

```text
POST /profiles/update/{id}
Content-Type: application/json

{"name":"Existing Profile Name","raw_proxy":"socks5://127.0.0.1:5000"}
```

There is a shared proxy store API, but the official profile request model documents `raw_proxy` rather than a link/reference to a stored proxy record.

### 12.4 Extension scope control

```text
GET /extensions
-> Select extension ID from data[]
GET /extensions/update-state/{id}?active=true&applied_group_ids=GROUP_A,GROUP_B
```

URL-encode the comma-separated group IDs in a real HTTP client.

## 13. Reliability, Testing, and Safe Operations

### 13.1 Error handling

- Handle connection refusal, non-JSON bodies, request timeouts, non-2xx HTTP responses, and `success: false` envelopes.
- Keep separate handling for HTTP transport errors versus application-level errors.
- Do not manufacture undocumented response fields or assume exact error messages.
- For process operations (`start`, `stop`) and mutations, avoid automatic blind retries that could create duplicate state or interfere with another worker.
- For local browser automation, handle the period between successful browser launch and CDP attachment; a connection may need a short, bounded retry while the debugging socket becomes ready. The official page does not specify readiness or retry timings.
- If a profile is shared across workers, enforce one-owner-per-profile locking at the application level.

### 13.2 Security

- Restrict access to loopback addresses. No vendor-provided API key is documented for the local endpoint.
- Never publish the debugging WebSocket URL, proxy credentials, or local storage paths in shared logs.
- Keep `raw_proxy` secrets out of issue reports and screenshots.
- Require explicit confirmation for profile hard deletion or deletion of shared resources.
- If developing a web application, use a trusted backend for local API access rather than assuming that a browser frontend can access the user's desktop `localhost` service safely or consistently.

### 13.3 Agent acceptance tests (run against a real GPM installation)

- [ ] API base URL/port discovery works, including fallback ports.
- [ ] `GET /profiles` returns a valid common envelope and page object.
- [ ] `GET /browsers/versions` returns a versions map.
- [ ] Creating a test profile with only `name` succeeds.
- [ ] Profile ID from create can be retrieved with `GET /profiles/{id}`.
- [ ] A partial update behaves as expected with and without `name` (vendor table discrepancy).
- [ ] Starting a Chrome profile returns a usable debugging connection.
- [ ] Playwright can attach to an existing Chrome context and navigate to a test page.
- [ ] Stopping the profile closes the intended process.
- [ ] Groups and proxies CRUD are exercised with disposable records.
- [ ] Extensions listing returns an array, not a paginated result.
- [ ] Extension state change is performed only on a permitted disposable/test environment.
- [ ] No proxy secrets appear in log output.
- [ ] Soft delete moves a test profile to trash; hard delete is not tested without explicit permission.

## 14. Known Documentation Gaps / Do Not Assume

The vendor page does **not** fully define the following:

1. The absolute path to `http.port` on Windows, macOS, or Linux.
2. A machine-readable OpenAPI schema, official Python/TypeScript SDK, or stable client-library versioning.
3. An exhaustive fingerprint response schema for `GET /profiles/{id}`.
4. Accepted string aliases for each enum field beyond the examples and general statement that strings are supported where applicable.
5. An exhaustive validation/error response catalog, HTTP status mapping, rate limits, or retry policy.
6. Whether an update can omit `name` in every version (the update description and shared parameter table differ).
7. How to enumerate browser process state independent of starting/stopping.
8. Specific format and delimiters for `bypass_proxy_extensions` and `port_protect`.
9. The precise semantics of clearing **every** optional field on update.
10. Whether all credential-bearing proxy URI variations work in all builds.
11. Connection/lifecycle behavior under concurrent start requests or when the profile browser is already running.
12. Additional extension management endpoints beyond listing and toggling state.

**Implementation policy:** If functionality depends on one of these gaps, test that behavior against the installed version, record the observed result, and keep it separate from documented contractual behavior. Never fabricate an endpoint because another browser-management product has it.

## 15. Quick Reference

```text
API Base URL: http://127.0.0.1:9495/api/v1
Port fallback: 8000–10000; check application data's http.port file
Auth: None for documented localhost access
Create profile: POST /profiles/create
List profiles: GET /profiles
Get profile: GET /profiles/{id}
Update profile: POST /profiles/update/{id}
Start browser: GET /profiles/start/{id}
Stop browser: GET /profiles/stop/{id}
Delete profile: GET /profiles/delete/{id}?mode=soft|hard
Browser versions: GET /browsers/versions
Groups: GET /groups, GET /groups/{id}, POST /groups/create,
        POST /groups/update/{id}, GET /groups/delete/{id}
Proxies: GET /proxies, GET /proxies/{id}, POST /proxies/create,
         POST /proxies/update/{id}, GET /proxies/delete/{id}
Extensions: GET /extensions,
            GET /extensions/update-state/{id}?active=true|false
```

### Primary source

- **Official GPM Login API Documentation:** https://gpmlogin.com/doc
- **Reviewed on:** 2026-11-02.
- **Accuracy note:** This file combines the documented API contract with independent implementation guidance and self-contained Python/TypeScript examples. It is **not an official GPM Login SDK**, and the documented examples have not been exercised against your local installation.
