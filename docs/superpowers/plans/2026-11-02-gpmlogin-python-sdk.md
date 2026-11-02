# GPMLogin Python SDK Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tạo SDK Python tái sử dụng được, bao phủ 20 endpoint GPM Login, có sync + async, wrapper thuận tiện và Playwright tùy chọn.

**Architecture:** Hai client tường minh dùng HTTPX, chia sẻ model, validation, serialization và operation contract. Resource giữ cùng tên hàm giữa sync/async; I/O, iterator và context manager tách theo chế độ. Core không phụ thuộc Playwright.

**Tech Stack:** Python >=3.11, HTTPX, dataclasses/TypedDict/IntEnum, pytest + pytest-asyncio, Ruff, mypy, build và setuptools. Async hỗ trợ asyncio; không cam kết Trio ở v1.

**Spec:** `docs/superpowers/specs/2026-11-02-gpmlogin-python-sdk-design.md`, được người dùng duyệt ngày 2026-11-02. Đọc cùng `GPM Login API Documentation.md`; không dùng ví dụ trong đó để suy ra endpoint/schema chưa được xác nhận.

## Global Constraints

- Python >=3.11; kiểm tra phiên bản Python còn được hỗ trợ tại thời điểm triển khai và pin ma trận CI cụ thể khi scaffold.
- Tên distribution dự kiến `gpmlogin-sdk`, import `gpmlogin_sdk`; cần kiểm tra tên trước khi publish, không mặc định tên còn trống.
- Core dependency: HTTPX. Model dùng dataclass, TypedDict, IntEnum và validation tường minh; không bắt buộc Pydantic.
- Extra `playwright`; core import/cài đặt vẫn hoạt động khi thiếu Playwright. Extra `dev` chứa công cụ build, pytest, async tests, lint và type check.
- Hai client có nhóm resource đối xứng: `.profiles`, `.groups`, `.proxies`, `.extensions`, `.browsers`. Sync trả model trực tiếp; async trả cùng model qua `await`. Helper iterator sync trả Iterator, async trả AsyncIterator.
- Không gọi `asyncio.run()` bên trong sync client và không chạy HTTP sync trên event loop.
- Không tự retry HTTP ở v1, kể cả GET. Phân loại operation read/mutation tường minh để mở rộng sau; start/stop/delete/extension state tuyệt đối không bị xem là read chỉ vì GET.
- Không tự publish PyPI, không tự launch GPM, không dò dải port, không thêm GUI/scheduler/worker framework hoặc adapter Selenium/Puppeteer.
- Không có `get_or_create`/`ensure`, batch start, bulk delete hoặc `create_and_start` ở v1.
- Không tự xóa profile trong cleanup. Không có live test hard-delete hoặc extension global mặc định.
- Các phiên bản dependency cụ thể được chọn bằng tài liệu Context7 khi triển khai, ghi vào môi trường kiểm thử/compatibility; không đoán bản mới nhất từ kế hoạch.

## Review Focus

1. Server trả `success=true` sau start nhưng launch malformed: session vẫn stop đúng một lần; timeout trước khi xác nhận success thì không tự stop — Task 3, 9.
2. Cùng profile qua `localhost` và `127.0.0.1`, hai client sync/async: phải chung khóa; khóa không bao trùm process khác — Task 9.
3. Server pagination lặp trang hoặc tên trùng ở trang sau: không lặp vô hạn và không chọn nhầm profile — Task 7.
4. Vendor message, unknown metadata và raw transport exception chứa secret: không lọt vào repr, log, traceback public — Task 2, 3, 11.
5. Async bị cancel trong start/cleanup hoặc client do caller quản lý: không mất cancellation, không stop khi trạng thái chưa rõ, không đóng nhầm HTTPX client — Task 4, 9.

## Cách thực hiện và phạm vi xác minh

Hiện chỉ có tài liệu và bản thiết kế, chưa có mã/package và chưa là Git repository. Task dưới đây là công việc tương lai; không có bước nào đã được triển khai hoặc test pass chỉ vì tài liệu này tồn tại.

Các lệnh chạy từ gốc dự án bằng PowerShell, Python môi trường dự án. `python -m pytest ...` là offline theo mặc định; mọi request HTTP phải đi qua injected `httpx.MockTransport`. Đây là contract tests của SDK, không phải bằng chứng GPM thật tuân theo fixture.

Mỗi task thực hiện RED → kiểm tra thất bại có đúng nguyên nhân → GREEN → commit/checkpoint. RED do thiếu module là hợp lệ ở task đầu; lỗi sai fixture/môi trường không chứng minh hành vi đang thiếu. Sau GREEN, commit các file của task bằng `git add <file paths>` và thông điệp đã chỉ định **nếu đã có Git**. Nếu chưa có, ghi checkpoint hoàn thành vào kế hoạch; không tự `git init`.

Không tự sửa tài liệu API nguồn. Nếu live observation khác tài liệu, ghi tại `docs/compatibility.md`, kèm build GPM và ngày kiểm chứng.

## File map và phụ thuộc

| Nhóm file | Trách nhiệm | Task |
|---|---|---|
| `pyproject.toml`, `.gitignore`, `src/gpmlogin_sdk/__init__.py`, `py.typed` | Package, dev tools, exports | 1, 4, 11 |
| `config.py`, `errors.py` | Config precedence, lỗi public an toàn | 1, 3 |
| `models.py`, `enums.py`, `_validation.py`, `_serialization.py` | DTO, response models, wire conversions | 2 |
| `_operations.py`, `_transport.py`, `_async_transport.py` | Operation contract, unwrap, HTTP | 3 |
| `client.py`, `async_client.py` | Client lifecycle và resource composition | 4 |
| `resources/{profiles,groups,proxies,extensions,browsers}.py` | Public sync + async API | 5, 6 |
| `helpers/pagination.py`, `helpers/profile_settings.py` | Iteration và settings builders | 7, 8 |
| `_ownership.py`, `helpers/session.py` | Profile lock, session cleanup | 9 |
| `integrations/playwright.py` | Optional CDP attachment | 10 |
| `tests/unit/`, `tests/contract/`, `tests/integration/` | Pure tests, wire assertions, live opt-in | Theo task |
| `tests/conftest.py`, `tests/contract/cases.py` | Mock factory và 20-operation matrix | 3, 5, 6 |
| `examples/{sync_basic,async_basic,sync_playwright,async_playwright}.py` | Ví dụ không chạy khi import | 11 |
| `README.md`, `docs/{usage,api,compatibility}.md`, `tools/verify_dist.py` | Hướng dẫn, coverage, clean install check | 11 |

Thêm `__init__.py` ở package con khi tạo thư mục. Resources chứa class sync/async trong cùng module. Phụ thuộc: `1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11`; thứ tự này ưu tiên việc kiểm thử tích hợp từng bước, không yêu cầu agent chạy song song.

### Task 1: Package tối thiểu và cấu hình local API

**Files:** Create `pyproject.toml`, `.gitignore`, `src/gpmlogin_sdk/{__init__.py,py.typed,config.py,errors.py}`, `tests/unit/test_config.py`, `tests/unit/test_package.py`.

**Interfaces:**

- Produces `resolve_config(*, host: str | None = None, port: int | None = None, port_file: str | Path | None = None, timeout: float | None = None) -> GPMConfig`.
- `GPMConfig` frozen dataclass: `host: str`, `port: int`, `timeout: float`; properties `base_url: str` (có `/api/v1`) và `api_key: tuple[str, int]` (host localhost chuẩn hóa thành 127.0.0.1 để khóa).
- `GPMError` base và `GPMConfigurationError`; `__version__ = "0.1.0"`.

- [ ] **Step 1 — Khởi tạo metadata đủ để chạy test.** Setuptools build backend, src discovery, `requires-python >=3.11`, core HTTPX, dev extra gồm pytest/pytest-asyncio/Ruff/mypy/build, playwright extra; pytest marker `live`, async strict mode. Chọn range dependency đã kiểm tra, ghi phiên bản dùng tại Task 11. Không cài Playwright browser qua bước này.
- [ ] **Step 2 — Viết failing config tests.** Dùng monkeypatch xóa các env liên quan giữa mỗi test; assertions cốt lõi:

```python
assert resolve_config().base_url == "http://127.0.0.1:9495/api/v1"
monkeypatch.setenv("GPM_API_PORT", "9555")
assert resolve_config(port=9666).port == 9666
assert resolve_config().port == 9555
with pytest.raises(GPMConfigurationError):
    resolve_config(host="example.com")
```

Thêm `test_config_file_and_precedence`: file chứa `9777\n`, env file path, explicit file path; explicit port thắng env port sai, nguồn thấp hơn không được đọc. Khi nguồn được chọn sai: env không phải số, file thiếu, permission error, file rỗng/JSON phải raise. Validate port integer 1..65535, từ chối bool; timeout hữu hạn >0; host có URL/path/userinfo/IPv6 không thuộc v1 phải bị từ chối.
- [ ] **Step 3 — Chạy RED.** `python -m pip install -e ".[dev]"`, rồi `python -m pytest tests/unit/test_config.py tests/unit/test_package.py -q`; expected FAIL vì config API chưa tồn tại.
- [ ] **Step 4 — Implement config và exports.** host: arg > `GPM_API_HOST` > 127.0.0.1; timeout: arg > `GPM_API_TIMEOUT_SECONDS` >30; port/file theo spec. File chọn lỗi không fallback; không quét port.
- [ ] **Step 5 — Chạy GREEN.** Lặp pytest trên; expected PASS. `python -c "import gpmlogin_sdk; assert gpmlogin_sdk.__version__ == '0.1.0'"` exit 0.
- [ ] **Step 6 — Commit/checkpoint:** `chore: scaffold typed package and local API configuration`.

### Task 2: Typed models, DTO và serialization đúng hợp đồng

**Files:** Create `src/gpmlogin_sdk/{models.py,enums.py,_validation.py,_serialization.py}`, `tests/unit/{test_models,test_validation,test_serialization}.py`; Modify `errors.py`, `__init__.py`.

**Interfaces:**

- Produces `CreateProfileRequest` TypedDict với `name: str` required, `UpdateProfileRequest` total=False, và `StartOptions` total=False. Create/update có đúng toàn bộ key ở bảng 4.5 tài liệu nguồn; dùng `NotRequired`/`Required`, không generic `**settings: Any` trong public signatures.
- `StartOptions`: `remote_debugging_port: int`, `window_scale: float`, `window_pos: str`, `window_size: str`, `skip_proxy_check: bool`, `addition_args: str` đều optional.
- `ProfileSummary(id, name, ...)`, `ProfileDetails` thêm fingerprint; `ProfileCreated(id, name)`; `ProfileUpdated(data: dict[str, object] | None)` cho response update chưa được mô tả đủ. `ProfileUpdated.data` repr=False; không yêu cầu vendor trả full Profile khi update.
- `Group(id, name, sort_order)`, `Proxy(id, raw_proxy, meta_data=None, tags=None)`, `Extension(id, name, version, is_active)`, `BrowserVersions(chromium, firefox)`, `Page[T](current_page, per_page, total, last_page, data)`.
- `StartResult(profile_id: str, driver_path: str | None, remote_debugging_port: int | None, websocket_debugging_url: str | None, addition_info: dict[str, object] | None)`; cần ít nhất một endpoint CDP khả dụng. Các model response có `extra: dict[str, object]` repr=False và giữ nguyên key chưa biết.
- Parser signatures: `parse_profile_summary(value: object) -> ProfileSummary`, `parse_profile_details(...) -> ProfileDetails`, `parse_profile_created(...) -> ProfileCreated`, `parse_profile_updated(...) -> ProfileUpdated`, `parse_group(...) -> Group`, `parse_proxy(...) -> Proxy`, `parse_extension(...) -> Extension`, `parse_versions(...) -> BrowserVersions`, `parse_start(...) -> StartResult`, `parse_page(value: object, item_parser: Callable[[object], T]) -> Page[T]`.
- `validate_create(body: CreateProfileRequest) -> None`, `validate_update(body: UpdateProfileRequest) -> None`, `validate_start(options: StartOptions) -> None`; `encode_id(value: str) -> str`; `serialize_query(values: Mapping[str, object]) -> dict[str, str]`; `serialize_body(values: Mapping[str, object]) -> dict[str, object]`.
- Thêm `GPMValidationError`, `GPMProtocolError(operation: str, *, success_confirmed: bool = False)`. Error text cố định, không chứa input value.

- [ ] **Step 1 — Viết failing tests.** Các assertions tiêu biểu:

```python
assert serialize_query({"active": False, "sort": 0, "search": "", "x": None}) == {
    "active": "false", "sort": "0", "search": ""
}
assert serialize_body({"raw_proxy": "", "note": None}) == {"raw_proxy": "", "note": None}
assert encode_id("a/b ?") == "a%2Fb%20%3F"
assert parse_profile_created({"id": "p1", "name": "A", "new": 7}).extra == {"new": 7}
```

Test create thiếu/rỗng name; WebRTC fixed thiếu IP; update name omitted hợp lệ; update raw_proxy empty khác null; enum sai và bool giả int bị từ chối. Test đủ các enum numeric trong bảng nguồn, browser enum 1/2, OS 1..5, sort 0..3; không tự phát minh string aliases. Group sort_order 0 được serialize, không hứa vendor áp dụng khi update.

Test `repr(ProfileDetails(...))`, Proxy, StartResult và unknown nested `extra` không lộ sentinel `SECRET`; mark toàn bộ field chứa raw_proxy, storage/driver path, fingerprint, metadata, extra và CDP endpoint repr=False. Unknown fields được truy cập qua `.extra` nhưng không xuất hiện trong repr.

Test parser từ chối id/name sai kiểu, bool làm số, page metadata âm/sai kiểu, extension active không phải bool; optional fields thiếu được chấp nhận. Page rỗng cho phép `last_page=0`, `current_page=1`, `total=0`; nonempty page cần last_page>=current_page. Không ép schema bên trong fingerprint/meta_data.
- [ ] **Step 2 — RED:** `python -m pytest tests/unit/test_models.py tests/unit/test_validation.py tests/unit/test_serialization.py -q`; expected FAIL vì chưa có implementation.
- [ ] **Step 3 — Implement các interface trên.** Request bỏ key bằng cách không đưa key vào dict; explicit None giữ JSON null chỉ ở field contract cho phép null, không dùng None làm sentinel mặc định. Enum numeric lấy đúng bảng tài liệu; không thêm default fingerprint phía SDK.
- [ ] **Step 4 — GREEN:** Lặp pytest trên; expected PASS. Thêm `python -m mypy src/gpmlogin_sdk` exit 0.
- [ ] **Step 5 — Commit/checkpoint:** `feat: add API models validation and wire serialization`.

### Task 3: Transport sync/async, envelope và lỗi an toàn

**Files:** Create `_operations.py`, `_transport.py`, `_async_transport.py` trong package; `tests/conftest.py`, `tests/unit/test_transport.py`, `tests/unit/test_error_privacy.py`; Modify `errors.py`.

**Interfaces:**

- Consumes config/parser/serializers Task 1–2.
- `Operation[T](name: str, method: Literal["GET", "POST"], path: str, mutates: bool, parser: Callable[[object], T])` frozen dataclass nội bộ; path đã encode ID, luôn relative `/profiles...`, không chứa base URL/query.
- `Transport(config: GPMConfig, http_client: httpx.Client)` và `AsyncTransport(..., http_client: httpx.AsyncClient)`; `request(operation: Operation[T], *, query: Mapping[str, object] | None = None, body: Mapping[str, object] | None = None, timeout: float | None = None) -> T`, async awaitable cùng signature. timeout override phục vụ bounded session cleanup.
- `parse_none(value: object) -> None` chỉ nhận None. `GPMTransportError`, `GPMTimeoutError`, `GPMHTTPError`, `GPMAPIError` có operation/status và `state_uncertain: bool`; timeout subclass transport. Mutating request lỗi sau lúc gửi là uncertain trừ khi envelope success/failure rõ ràng. Không hứa xác định request đã tới server.
- `GPMProtocolError.success_confirmed=True` chỉ khi HTTP thành công và envelope có `success is True`, nhưng parser data thất bại; session dùng marker này ở Task 9.
- Fixture `api_factory(mode, handler)` tạo client adapter sau Task 4, tự đóng injected HTTPX trong teardown; trước đó test transport trực tiếp. `mode` là `sync` hoặc `async`, handler ghi request và trả HTTPX Response.

- [ ] **Step 1 — Viết failing tests parametrized sync/async.** Hành vi: 200 + success true unwrap; success false → GPMAPIError; string `"true"` hoặc `1` → protocol error; missing success/data, body list, invalid JSON → protocol error. data null chỉ hợp lệ với parse_none/ProfileUpdated.

```python
# Assertions chung sau khi gọi bằng chế độ sync hoặc async tương ứng.
assert result.id == "p1"
assert len(recorded_requests) == 1
assert recorded_requests[0].method == "POST"
assert recorded_requests[0].url.path == "/api/v1/profiles/create"
assert caught.value.operation == "profiles.start"
assert caught.value.success_confirmed is True  # success=true, malformed launch
```

HTTP 500/302 (kể cả Location remote) → GPMHTTPError; không follow redirect. ConnectError/ReadTimeout → lỗi typed; không tự retry mutation hoặc GET read. Test request có Content-Type JSON chỉ khi body tồn tại, query False thành lowercase và base URL không nhân đôi `/api/v1`. HTTPX client inject có base_url khác không được thay đổi endpoint đích đã resolve; transport dùng absolute URL cấu hình SDK.

Privacy tests đặt `SECRET` trong vendor message, response text, query search, raw_proxy, proxy URL và HTTPX exception; `str`, `repr`, `traceback.format_exception`, caplog không có SECRET. Không lưu raw request/response/exception trong public fields. Model repr protection đã có Task 2; không chủ động log request qua HTTPX debug ở SDK.
- [ ] **Step 2 — RED:** `python -m pytest tests/unit/test_transport.py tests/unit/test_error_privacy.py -q`; expected FAIL ở transport/lỗi chưa tồn tại.
- [ ] **Step 3 — Implement chung envelope decoder và hai I/O wrapper.** Dùng HTTPX MockTransport để test, không network. Tắt follow redirects tại mỗi request; không chain raw exception vào public traceback. Không nuốt CancelledError; SDK không hứa che secret nếu caller bật logging raw HTTPX riêng hoặc chủ động in model.data.
- [ ] **Step 4 — GREEN:** Lặp pytest trên; expected PASS cả hai chế độ, request counter=1 ở mọi ca lỗi không retry.
- [ ] **Step 5 — Commit/checkpoint:** `feat: add sync async transport and safe typed errors`.

### Task 4: Public clients và quyền sở hữu HTTPX connection

**Files:** Create `client.py`, `async_client.py`, `tests/unit/test_clients.py`; Modify `__init__.py`.

**Interfaces:**

- Produces `GPMClient(*, host: str | None = None, port: int | None = None, port_file: str | Path | None = None, timeout: float | None = None, http_client: httpx.Client | None = None)`; `close() -> None`, `__enter__() -> GPMClient`, `__exit__(...) -> None`.
- `AsyncGPMClient` cùng options nhưng AsyncClient, `aclose() -> None`, `__aenter__`, `__aexit__`. Không async constructor; tạo object không thực hiện network.
- `.config: GPMConfig`, internal `._transport`; resources gắn ở Task 5–6, `.profile_session` gắn Task 9.

- [ ] **Step 1 — Viết failing lifecycle tests.** Client tự tạo dùng `trust_env=False`, không retry/follow redirects; context exit đóng đúng một lần. Client inject không bị đóng khi SDK exit/close, kể cả task ném lỗi hoặc async cancel. Close SDK idempotent; gọi operation sau SDK close raise GPMConfigurationError. Không tạo HTTPX Client sync trong AsyncGPMClient. Hai instance không chia sẻ mutable config.

```python
external = httpx.Client(transport=httpx.MockTransport(handler))
with GPMClient(http_client=external) as client:
    assert client.config.port == 9495
assert not external.is_closed
external.close()
```

Viết async equivalent bằng AsyncClient/async with; test http_client sai chế độ bị từ chối sớm.
- [ ] **Step 2 — RED:** `python -m pytest tests/unit/test_clients.py -q`; expected FAIL ở client API mới.
- [ ] **Step 3 — Implement clients, ownership HTTPX và exports.** Không thêm global singleton HTTP client và không đọc env ở import time.
- [ ] **Step 4 — GREEN:** Lặp pytest trên và `python -m pytest tests/unit -q`; expected PASS.
- [ ] **Step 5 — Commit/checkpoint:** `feat: expose reusable sync and async clients`.

### Task 5: Profiles và browser versions, đủ wire contract

**Files:** Create `resources/{__init__.py,profiles.py,browsers.py}`, `tests/contract/{__init__.py,cases.py,test_profiles.py,test_browsers.py}`; Modify clients và exports.

**Interfaces:**

`ProfilesResource` và `AsyncProfilesResource` có cùng arguments/return models, async là coroutine:

```python
list(*, page: int = 1, page_size: int = 30, search: str | None = None,
     sort: SortOrder = SortOrder.NEWEST) -> Page[ProfileSummary]
get(profile_id: str) -> ProfileDetails
create(body: CreateProfileRequest) -> ProfileCreated
update(profile_id: str, body: UpdateProfileRequest) -> ProfileUpdated
soft_delete(profile_id: str) -> None
hard_delete(profile_id: str, *, confirm: bool = False) -> None
start(profile_id: str, options: StartOptions | None = None) -> StartResult
stop(profile_id: str) -> None
```

`BrowsersResource.versions() -> BrowserVersions` và async counterpart. `SortOrder` numeric 0/1/2/3; list page/page_size positive integers, từ chối bool.

- [ ] **Step 1 — Viết failing wire tests cả hai chế độ.** `cases.py` khai báo bảng operation/method/path/query/body/fixture parser; mỗi case có id ổn định. Profiles gồm 7 endpoint unique (delete có 2 case modes), browsers 1. Assert exact request và typed result, không chỉ status.

```python
assert request.method == "GET"
assert request.url.path == "/api/v1/profiles/start/p1"
assert dict(request.url.params) == {"skip_proxy_check": "false", "addition_args": "--mute-audio"}
assert result.profile_id == "p1"
```

Các ca khác: create chỉ name; update không name và null/empty giữ nguyên; delete mode soft/hard; hard_delete không confirm/bool sai → validation error và zero HTTP calls. ID không UUID vẫn hợp lệ, reserved chars được encode đúng raw_path; browser versions dùng `chromium`, không đổi thành `chrome`. start là mutates=True dù GET; malformed launch giữ success_confirmed marker.
- [ ] **Step 2 — RED:** `python -m pytest tests/contract/test_profiles.py tests/contract/test_browsers.py -q`; expected FAIL resource chưa có.
- [ ] **Step 3 — Implement resource classes và gắn `.profiles`/`.browsers` vào hai clients.** Không gọi API phụ trong low-level update/start. Không xuất generic raw-request shortcut để bypass typed contract ở v1.
- [ ] **Step 4 — GREEN:** Lặp pytest trên; expected PASS mọi operation sync/async.
- [ ] **Step 5 — Commit/checkpoint:** `feat: implement profiles and browser versions resources`.

### Task 6: Groups, proxies, extensions và matrix 20 endpoint

**Files:** Create `resources/{groups.py,proxies.py,extensions.py}`, `tests/contract/{test_groups.py,test_proxies.py,test_extensions.py,test_parity.py}`; Modify clients, `cases.py` và exports.

**Interfaces:**

- Groups sync/async: `list` cùng pagination signature Task 5 → Page[Group]; `get(group_id: str) -> Group`; `create(name: str, *, sort_order: int = 0) -> Group`; `update(group_id: str, *, name: str, sort_order: int | None = None) -> Group`; `delete(group_id: str, *, confirm: bool = False) -> None`.
- Proxies sync/async: `list` → Page[Proxy]; `get(proxy_id: str) -> Proxy`; `create(raw_proxy: str) -> Proxy`; `update(proxy_id: str, raw_proxy: str) -> Proxy`; `delete(proxy_id: str, *, confirm: bool = False) -> None`. raw_proxy chuỗi không rỗng cho shared store; không bắt format auth chưa được vendor xác nhận.
- Extensions sync/async: `list() -> list[Extension]`; `set_state(extension_id: str, *, active: bool, group_ids: Sequence[str] | None = None) -> None`.

- [ ] **Step 1 — Viết failing tests.** 5 groups +5 proxies +2 extensions. Assert query/body đúng, update group có name, sort_order=0 không bị bỏ; proxy không tự gắn proxy_id vào profile. Confirm gate mặc định zero calls với shared delete. Extensions array parse khác Page.

```python
assert dict(request.url.params) == {"active": "false", "applied_group_ids": "g1,g2"}
assert result is None
assert [item.id for item in listed_extensions] == ["e1"]
```

Scope None chỉ gửi active; scope [] hoặc group ID rỗng/chứa comma bị từ chối trước HTTP. Từ chối `group_ids="g1"` để không tách chuỗi thành ký tự. Test `active=False`, không biến thành omitted/global.

`test_parity.py`: assert bảng có đúng 20 unique (method,path template), mọi case chạy trên cả sync/async và cho cùng output/error. Delete soft/hard tính một endpoint; không nhầm 21 vì có hai hàm public.
- [ ] **Step 2 — RED:** `python -m pytest tests/contract/test_groups.py tests/contract/test_proxies.py tests/contract/test_extensions.py tests/contract/test_parity.py -q`; expected FAIL ở resources/cases còn thiếu.
- [ ] **Step 3 — Implement và gắn resource groups/proxies/extensions vào clients.** GET delete/state đều mutates=True.
- [ ] **Step 4 — GREEN:** `python -m pytest tests/contract -q`; expected PASS matrix đủ 20 endpoint cả sync/async và confirmation tests.
- [ ] **Step 5 — Commit/checkpoint:** `feat: complete groups proxies and extensions API coverage`.

### Task 7: Lazy pagination và tìm chính xác theo tên

**Files:** Create `helpers/{__init__.py,pagination.py}`, `tests/unit/test_pagination.py`, `tests/contract/test_lookup.py`; Modify profiles/groups/proxies resources và `errors.py`.

**Interfaces:**

- `iterate_pages(fetch: Callable[[int], Page[T]]) -> Iterator[T]`; `iterate_pages_async(fetch: Callable[[int], Awaitable[Page[T]]]) -> AsyncIterator[T]`.
- Profiles/groups/proxies `iter_all(*, page_size: int = 30, search: str | None = None, sort: SortOrder = SortOrder.NEWEST) -> Iterator[Entity]`, async counterpart trả AsyncIterator trực tiếp, **không await trước async for**.
- Profiles `find_by_name(name: str) -> ProfileSummary | None`; Groups → Group | None, async cùng tên; thêm `GPMAmbiguousMatchError`.

- [ ] **Step 1 — Viết failing tests.** Fetch stub 3 trang; tạo iterator chưa có request; next đầu chỉ fetch trang 1, break không tải phần còn lại. End khi last_page đạt hoặc page rỗng. Đặt tên test và assertions:

```python
assert fetched_pages == []
assert next(items).id == "p1"
assert fetched_pages == [1]
assert [p.id for p in items] == ["p2", "p3"]
assert fetched_pages == [1, 2, 3]
```

Test server trả current_page=1 khi yêu cầu page=2 → GPMProtocolError với call count=2; last_page thay đổi theo collection thì dùng metadata mới và không hứa snapshot. Test find không thấy → None, phân biệt hoa thường, partial name không match, trùng ở trang 2 → ambiguous dù trang 1 đã thấy đúng. Duyệt mọi trang trước khi trả unique match; không trả sớm khi tìm thấy đầu tiên.
- [ ] **Step 2 — RED:** `python -m pytest tests/unit/test_pagination.py tests/contract/test_lookup.py -q`; expected FAIL thiếu wrapper.
- [ ] **Step 3 — Implement shared iteration logic thuần và wrappers sync/async.** Forward search/sort/page_size xuyên suốt; reject name rỗng trước request.
- [ ] **Step 4 — GREEN:** Lặp pytest trên; expected PASS cả sync/async.
- [ ] **Step 5 — Commit/checkpoint:** `feat: add lazy pagination and exact name lookup`.

### Task 8: Proxy helpers và options builders

**Files:** Create `helpers/profile_settings.py`, `tests/unit/test_profile_settings.py`, `tests/contract/test_proxy_helpers.py`; Modify profiles resources và public exports.

**Interfaces:**

- `set_proxy(profile_id: str, raw_proxy: str, *, name: str | None = None) -> ProfileUpdated`; `clear_proxy(profile_id: str, *, name: str | None = None) -> ProfileUpdated`, async tương ứng.
- `build_start_options(*, window_size: tuple[int, int] | None = None, window_pos: tuple[int, int] | None = None, window_scale: float | None = None, remote_debugging_port: int | None = None, skip_proxy_check: bool | None = None, addition_args: str | None = None) -> StartOptions`.
- `join_startup_urls(urls: Sequence[str]) -> str`.

- [ ] **Step 1 — Viết failing tests.** Assert helpers tương đương wire contract:

```python
assert build_start_options(window_size=(1280, 800), window_pos=(-100, 0), skip_proxy_check=False) == {
    "window_size": "1280,800", "window_pos": "-100,0", "skip_proxy_check": False
}
assert join_startup_urls(["https://example.com", "https://example.org"]) == "https://example.com\nhttps://example.org"
```

Reject kích thước <=0, tuple sai độ dài, bool làm dimension, scale không hữu hạn/dương, port invalid. startup_urls từ chối string làm Sequence, phần tử rỗng/CR/LF; list rỗng trả `""` tường minh.

set_proxy có name → chỉ một POST; không name → một GET rồi một POST giữ tên; clear body raw_proxy="". GET lỗi không POST; update lỗi không retry. Docstring nêu nguy cơ race rename, không hứa transaction. set_proxy từ chối chuỗi rỗng, caller dùng clear_proxy để biểu đạt ý định.
- [ ] **Step 2 — RED:** `python -m pytest tests/unit/test_profile_settings.py tests/contract/test_proxy_helpers.py -q`; expected FAIL wrappers chưa có.
- [ ] **Step 3 — Implement theo signatures trên.** Không thêm GET ngầm vào low-level update, không lưu/log credential. `addition_args` nhận chuỗi nguyên bản không đổi escaping.
- [ ] **Step 4 — GREEN:** Lặp pytest trên; expected PASS sync/async helpers.
- [ ] **Step 5 — Commit/checkpoint:** `feat: add profile proxy and launch option helpers`.

### Task 9: Profile session, khóa dùng chung và cleanup có giới hạn

**Files:** Create `_ownership.py`, `helpers/session.py`, `tests/unit/test_ownership.py`, `tests/contract/test_session.py`; Modify clients và `errors.py`.

**Interfaces:**

- `acquire_profile(api_key: tuple[str, int], profile_id: str) -> Lease`; `Lease.release() -> None` idempotent. Registry process-wide, threading.Lock chỉ bảo vệ thao tác set ngắn, fail-fast; key host đã normalize ở Task 1.
- `ProfileSession(profile_id: str, launch: StartResult)` dataclass, repr launch an toàn. Không mở browser context/Playwright ở task này.
- `GPMClient.profile_session(profile_id: str, *, exclusive: bool = False, start_options: StartOptions | None = None) -> AbstractContextManager[ProfileSession]`; async trả AbstractAsyncContextManager[ProfileSession].
- Thêm `GPMProfileBusyError`, `GPMCleanupError`; lỗi task gốc giữ nguyên identity và có `cleanup_error: GPMCleanupError | None` được gắn khi có thể; luôn thêm exception note an toàn nếu không thể gắn attribute. Không chain thông điệp raw exception.

- [ ] **Step 1 — Viết failing tests ownership/lifecycle sync và async.** exclusive=False hoặc giá trị không phải True → validation error, zero requests. Thành công: request sequence start, task, stop; đúng một stop; không delete. Busy giữa client sync/async hoặc localhost/127.0.0.1 → fail-fast, không request thứ hai. Khác profile hoặc khác port không tranh khóa.

```python
assert events == ["start", "task", "stop"]
assert stop_calls == 1
assert lock_is_released is True
assert caught.value is original_task_error
assert caught.value.cleanup_error is not None
```

Các nhánh bắt buộc: start success + malformed data (marker Task 3) → stop một lần rồi raise protocol error; start API failure/timeout/non-JSON → không stop; task lỗi + stop lỗi giữ lỗi task; chỉ stop lỗi → GPMCleanupError. Sau mọi nhánh lease được acquire lại. Timeout start không tự retry và state_uncertain=True; caller reconcile ngoài SDK.

Async tests dùng event đồng bộ điều khiển, không sleep theo thời gian thật: cancel trong task → stop await hoàn tất rồi phát lại CancelledError; cancel trong start trước confirmed success → không stop; cancel lặp khi cleanup đang chạy không tạo stop thứ hai, cleanup task kết thúc hoặc bị cancel/await đầy đủ trước nhả khóa. Cleanup HTTP timeout override <=10 giây, dù client timeout=30.
- [ ] **Step 2 — RED:** `python -m pytest tests/unit/test_ownership.py tests/contract/test_session.py -q`; expected FAIL session/registry chưa có.
- [ ] **Step 3 — Implement state machine.** States acquired → start-unconfirmed → started → cleanup-attempted → released. Session chỉ cleanup khi parse thành công hoặc GPMProtocolError success_confirmed=True. Sync cleanup dùng timeout riêng 10 giây; async dùng một cleanup task được shield, monotonic deadline tổng 10 giây, hủy và await task nếu hết hạn, giữ cancellation/error gốc. Không tạo background cleanup bị bỏ mặc.
- [ ] **Step 4 — GREEN:** Lặp pytest trên và `python -m pytest tests/contract -q`; expected PASS, không unhandled task warnings. Xác minh khóa này không được mô tả là distributed hoặc tự chứng minh browser chưa chạy.
- [ ] **Step 5 — Commit/checkpoint:** `feat: add exclusive profile sessions with reliable cleanup`.

### Task 10: Playwright adapter tùy chọn, sync + async

**Files:** Create `integrations/{__init__.py,playwright.py}`, `tests/unit/test_playwright_adapter.py`, `tests/contract/test_playwright_session.py`; Modify `errors.py`.

**Interfaces:**

- `connect(launch: StartResult, playwright: SyncPlaywright, *, browser_kind: BrowserType, timeout_ms: int = 10000) -> AbstractContextManager[PlaywrightAttachment]`.
- `connect_async(launch: StartResult, playwright: AsyncPlaywright, *, browser_kind: BrowserType, timeout_ms: int = 10000) -> AbstractAsyncContextManager[AsyncPlaywrightAttachment]`.
- `BrowserType` IntEnum Task 2: CHROME=1, FIREFOX=2. `browser_kind` required, caller lấy từ profile đã biết; không có default ngầm.
- Attachments `.browser`, `.context`; `get_or_create_page() -> SyncPage` hoặc async → AsyncPage; thêm `GPMIntegrationError`.

- [ ] **Step 1 — Đối chiếu tài liệu Context7 và spike hẹp về lỗi CDP.** Pin Playwright đã kiểm tra. Dùng local disposable Chromium của Playwright, không profile người dùng, chỉ khi có binary; xác nhận public error types/codes, connect/disconnect và readiness failure. Ghi tại compatibility. Nếu chưa có binary thì mock test vẫn chạy, live spike ghi chưa xác minh; retry chỉ cho nguyên nhân từ chối kết nối đã nhận diện chắc chắn, lỗi khác fail ngay. Không tự cài browser hoặc chạy GPM thật để hoàn thành planning.
- [ ] **Step 2 — Viết failing adapter tests.** Dùng fake sync/async Playwright public interface; core-only subprocess chứng minh import gpmlogin_sdk không import Playwright. Gọi integration thiếu dependency → GPMIntegrationError với hướng dẫn cài extra.

```python
assert connected_endpoint == launch.websocket_debugging_url
assert attachment.context is existing_context
assert attachment.get_or_create_page() is existing_page
assert events[-2:] == ["detach", "stop"]
```

Firefox bị từ chối trước connect; URL remote/userinfo/fragment/port sai bị từ chối; ws://localhost và ws://127.0.0.1 hợp lệ. Có WS nhưng sai phải báo lỗi, không âm thầm fallback; thiếu WS nhưng port hợp lệ dùng `http://127.0.0.1:<port>`. Không có context → đóng connection đã attach rồi raise; page trống → new_page trên context cũ, không new_context.

Retry tests dùng fake clock: tổng deadline 10000 ms, khoảng chờ 250 ms, per-attempt timeout không vượt remaining; retry chỉ trước attach thành công. Lỗi auth/protocol/browser không hợp lệ không retry. Không chạy lại user callback, không start lại GPM. Task lỗi và detach lỗi giữ lỗi task như policy Task 9; cancellation vẫn detach và để outer session stop. Adapter chỉ gọi browser.close để ngắt kết nối, không dừng Playwright instance do caller quản lý.
- [ ] **Step 3 — RED:** `python -m pytest tests/unit/test_playwright_adapter.py tests/contract/test_playwright_session.py -q`; expected FAIL adapter chưa có.
- [ ] **Step 4 — Implement bằng public `chromium.connect_over_cdp`.** Type imports dưới TYPE_CHECKING, runtime dependency check khi gọi adapter. Không tạo persistent context mới, không thay đổi browser/profile ownership. Async detach giới hạn 10 giây và giữ cancellation, reuse cleanup policy Task 9 thay vì bỏ task chạy nền.
- [ ] **Step 5 — GREEN:** Lặp pytest trên; expected PASS sync/async và event order detach trước stop. Nếu CDP spike thật chưa chạy, ghi limitation, không gọi đó là verified browser compatibility.
- [ ] **Step 6 — Commit/checkpoint:** `feat: add optional sync and async Playwright CDP adapters`.

### Task 11: Tài liệu, ví dụ, live opt-in và kiểm tra artifact

**Files:** Create `README.md`, `docs/{usage.md,api.md,compatibility.md}`, `examples/{sync_basic.py,async_basic.py,sync_playwright.py,async_playwright.py}`, `tests/unit/test_examples.py`, `tests/contract/test_public_api.py`, `tests/integration/{conftest.py,test_live_read.py,test_live_profile.py}`, `tools/verify_dist.py`; Modify metadata/exports nếu cần.

**Interfaces:**

- `tools/verify_dist.py --wheel <absolute-wheel-path> --sdist <absolute-sdist-path>`: stdlib CLI, tạo venv tạm, cài wheel core-only, kiểm tra imports/type marker/exports, build wheel từ sdist và kiểm tra nội dung; exit nonzero nếu sai. Không publish hoặc giữ venv tạm sau kiểm tra.
- Live test `GPM_RUN_LIVE=1` chỉ bật read-only; `GPM_RUN_LIVE_MUTATIONS=1` mới cho create/update/start/stop/soft delete profile test do fixture tạo. Luôn dùng cấu hình port rõ ràng, không tìm/quản lý profile có sẵn của người dùng.

- [ ] **Step 1 — Viết failing public API/examples tests.** Export đủ clients, errors, DTO/models/enums/builders. Import 4 examples không có network; execution trong `main()` và `if __name__ == "__main__"`. Async example `asyncio.run(main())` chỉ ở entrypoint, không ở SDK. Mock run hai ví dụ basic, assert sync/async cho cùng kết quả.
- [ ] **Step 2 — RED:** `python -m pytest tests/unit/test_examples.py tests/contract/test_public_api.py -q`; expected FAIL docs/examples/exports còn thiếu.
- [ ] **Step 3 — Hoàn thiện examples/docs.** Basic dùng profile ID cấu hình, list/get và profile session rõ exclusive=True; không tự hard delete. Playwright examples lồng attachment bên trong session, giữ existing context, playwright instance ngoài cùng; thông báo yêu cầu profile Chrome dành riêng trước start. Không in raw model/proxy/CDP URL; chỉ in id/name khi cần.

README có cài local `python -m pip install .`, extra `.[playwright]`, sync/async ngắn và ownership warning cụ thể. usage mô tả config precedence, client injection, error handling, pagination/lookup ambiguity, set_proxy rename race, cleanup/cancel, field omitted/null/empty, extension scope và xóa confirm. api có signatures và bảng mapping đủ 20 endpoint; compatibility tách documented/mocked/live, ghi build GPM nếu đã chạy, dependency versions và phạm vi asyncio.
- [ ] **Step 4 — Implement live opt-in tests.** Mặc định collect rồi skip, không kết nối. Read-only list profiles/versions/extensions. Mutation fixture tạo unique name, dùng returned ID, thử get/update/name behavior, start/attach/stop Chrome nếu được cấu hình; finally chỉ soft-delete record do nó tạo sau khi stop đã xác nhận. Start timeout khiến trạng thái không rõ thì ghi ID cần reconcile, không retry/cleanup destructive. Groups/proxies CRUD chỉ khi thêm `GPM_RUN_LIVE_SHARED_MUTATIONS=1`; delete có confirm=True chỉ cho record fixture tạo. Không có test hard-delete/extension state default. Không bật các env này tự động.
- [ ] **Step 5 — GREEN và quality gates offline.**

```powershell
python -m pytest tests/unit tests/contract -q
python -m pytest tests/integration -q
python -m ruff check .
python -m mypy src/gpmlogin_sdk
python -m build
```

Expected: unit/contract PASS; integration SKIPPED khi chưa opt-in; lint/type exit 0; có wheel và sdist version 0.1.0. Chạy privacy regression với sentinel qua repr/errors/traceback/log như Task 2–3, không thay bằng nhận xét thủ công.
- [ ] **Step 6 — Kiểm tra wheel/sdist trong môi trường sạch.**

```powershell
python tools/verify_dist.py --wheel dist/gpmlogin_sdk-0.1.0-py3-none-any.whl --sdist dist/gpmlogin_sdk-0.1.0.tar.gz
```

Expected exit 0; wheel có `py.typed`, core imports cả hai client được và Playwright không được cài. Sdist build lại được wheel có cùng public package contents. Nếu backend tạo filename khác thì lấy filename thực tế của Step 5 trong task này, không giả thành công.
- [ ] **Step 7 — Commit/checkpoint và ghi verification report:** `docs: document SDK usage and verify distributable artifacts`. Report rõ command nào đã chạy, live tests nào chưa chạy, đường dẫn artifacts, không coi skip là pass live.

## Acceptance và handoff

- [ ] Matrix đủ 20 endpoint với sync/async parity; default retry=0 và confirmation gate được kiểm thử.
- [ ] Config, typed DTO/response và secret handling đáp ứng spec; không yêu cầu Playwright khi cài core.
- [ ] Pagination/lookup/settings wrappers hoạt động cả hai chế độ.
- [ ] Session cleanup/cancellation có test, không tự nhận ownership hoặc âm thầm stop sau timeout start.
- [ ] Playwright adapter detach trước GPM stop trong ví dụ composition; chỉ hứa Chrome/Chromium GPM.
- [ ] Wheel/sdist build và clean-install checks thành công; docs phân biệt offline/mock/live.

Không có thao tác publish/merge/deploy trong kế hoạch. Sau khi hoàn tất các task, gửi kết quả kiểm thử và artifact để người dùng chọn cách dùng/phát hành tiếp.

## Self-review của kế hoạch (2026-11-02)

- Spec coverage: package/config/models/transport → Tasks 1–4; 20 endpoint →5–6; wrappers →7–8; ownership/cleanup →9; Playwright →10; docs/live/build →11.
- Type consistency: resource async dùng cùng request/response type; iter_all trả async iterator trực tiếp; session chỉ giữ StartResult, browser kind được truyền tường minh cho adapter.
- Review Focus: cả 5 trường hợp ở đầu kế hoạch đã có assertions/task sở hữu, gồm success-confirmed malformed launch và khóa host aliases.
- Spec ambiguity đã cụ thể hóa: update profile dùng ProfileUpdated vì chưa có schema response ổn định; browser_kind là required keyword; asyncio là async runtime v1; không mở rộng vendor contract.
- Chưa triển khai mã, chưa cài dependency, chưa chạy test SDK hoặc gọi GPM thật. Các lệnh và expected output ở trên là tiêu chí cho người thực hiện.

## Tài liệu thư viện tham khảo

- HTTPX MockTransport đã đối chiếu qua Context7 khi lập kế hoạch: https://github.com/encode/httpx/blob/master/docs/advanced/transports.md
- HTTPX client lifecycle: https://github.com/encode/httpx/blob/master/docs/advanced/clients.md
- HTTPX async lifecycle: https://github.com/encode/httpx/blob/master/docs/async.md
- Khi triển khai tool/test API khác, tiếp tục tra Context7 theo AGENTS.md thay vì suy đoán syntax/version.
