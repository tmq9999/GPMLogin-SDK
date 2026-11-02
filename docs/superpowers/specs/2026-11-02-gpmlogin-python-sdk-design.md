# Thiết kế GPMLogin SDK cho Python

Ngày: 2026-11-02. Trạng thái: người dùng đã duyệt và yêu cầu chuyển thành kế hoạch theo task; chưa triển khai.

## 1. Mục tiêu và quyết định đã thống nhất

Xây dựng SDK Python có thể cài và tái sử dụng giữa các project, bao phủ local HTTP API `/api/v1` và cung cấp wrapper cho tác vụ thường gặp. Người dùng đã chọn Python trước và hỗ trợ sync + async ngay từ đầu.

Nguồn hợp đồng API: `GPM Login API Documentation.md` ở gốc dự án, gồm 20 endpoint. Tài liệu chưa được kiểm chứng với ứng dụng GPM đang chạy. Không coi các ví dụ hoặc khuyến nghị trong tài liệu là hành vi vendor đã xác nhận.

Các quyết định còn lại dưới đây do người thiết kế đề xuất và đã được người dùng duyệt cùng bản thiết kế. Chi tiết triển khai được cụ thể hóa trong `../plans/2026-11-02-gpmlogin-python-sdk.md`.

## 2. Các hướng đã cân nhắc

- Chỉ sync: ít mã và ít test hơn, nhưng không phù hợp với yêu cầu sync + async ngay từ đầu.
- Sync + async với hai bộ SDK độc lập: linh hoạt nhưng dễ lệch request, model và validation.
- **Đề xuất: hai client tường minh, dùng chung hợp đồng và logic thuần.** `GPMClient` và `AsyncGPMClient` dùng HTTPX, chung model, validation, serialization và định nghĩa operation; chỉ tách phần I/O và orchestration cần await. Không gọi `asyncio.run()` bên trong sync client và không chạy HTTP sync trên event loop.

## 3. Phạm vi và giới hạn

V1 gồm toàn bộ 20 endpoint, pagination, cấu hình port, lỗi có kiểu, helper profile/proxy/window, session quản lý vòng đời và adapter Playwright tùy chọn cho sync + async.

Không gồm GUI, dịch vụ web, scheduler, hệ thống phân phối worker, Selenium/Puppeteer adapter, tự launch ứng dụng GPM, tự dò toàn bộ port 8000–10000, tự phát minh endpoint trạng thái browser, cài extension hoặc clone fingerprint. Không tự publish PyPI. Không cần tạo Postman workspace hoặc OpenAPI để hoàn thành SDK này.

## 4. Nền tảng và đóng gói

- Python >=3.11; kiểm tra phiên bản Python còn được hỗ trợ tại thời điểm triển khai và pin ma trận CI cụ thể khi scaffold.
- Tên distribution dự kiến `gpmlogin-sdk`, import `gpmlogin_sdk`; cần kiểm tra tên trước khi publish, không mặc định tên còn trống.
- Core dependency: HTTPX. Model dùng dataclass, TypedDict, IntEnum và validation tường minh; không bắt buộc Pydantic.
- Extra `playwright`; core import/cài đặt vẫn hoạt động khi thiếu Playwright. Extra `dev` chứa công cụ build, pytest, async tests, lint và type check.
- `pyproject.toml`, cấu trúc `src/`, `py.typed`, wheel và sdist. Bắt đầu phiên bản 0.1.0; ghi rõ public API thử nghiệm trước 1.0.
- Cài từ đường dẫn hoặc Git để dùng nội bộ; build artifact và kiểm tra cài wheel trong môi trường sạch trước khi phát hành.

## 5. Kiến trúc và public API

Hai client có nhóm resource đối xứng: `.profiles`, `.groups`, `.proxies`, `.extensions`, `.browsers`. Sync trả model trực tiếp; async trả cùng model qua `await`. Helper iterator sync trả Iterator, async trả AsyncIterator.

Client options: host mặc định `127.0.0.1`, port tùy chọn, đường dẫn `http.port` tùy chọn, timeout mặc định 30 giây, và HTTPX client tùy chọn để inject. Không đóng client được caller inject; client tự tạo được đóng bởi `close()`/`aclose()` hoặc `with`/`async with`.

Thứ tự chọn port: tham số `port` > biến `GPM_API_PORT` > file `http.port` được cấu hình > 9495. Đường dẫn file: tham số > `GPM_HTTP_PORT_FILE`; không tự đoán vị trí cài đặt. Nguồn cấu hình được chọn nhưng sai, file thiếu/không đọc được hoặc nội dung không hợp lệ phải báo `GPMConfigurationError`, không âm thầm fallback. Chỉ cho host `localhost`, `127.0.0.1` ở v1; không hỗ trợ remote bridge. Không đọc proxy hệ thống cho local API (`trust_env=False` với client tự tạo); caller inject client chịu trách nhiệm cấu hình tương đương.

Các endpoint resource:

| Resource | Hàm sync (async giữ cùng tên) | Wire operation |
|---|---|---|
| profiles | `list`, `get`, `create`, `update` | GET list/get; POST create/update |
| profiles | `soft_delete`, `hard_delete` | GET delete, mode tường minh |
| profiles | `start`, `stop` | GET start/stop |
| groups | `list`, `get`, `create`, `update`, `delete` | 5 endpoint groups |
| proxies | `list`, `get`, `create`, `update`, `delete` | 5 endpoint proxies |
| extensions | `list`, `set_state` | GET list/update-state |
| browsers | `versions` | GET browsers/versions |

Resources trả typed data đã unwrap envelope. Các thao tác có `data: null` trả `None`. `Page[T]` giữ metadata và danh sách `data`. Extension list trả `list[Extension]`, không ép thành Page. `StartResult` có thông tin launch; fingerprint và metadata không có schema dùng `dict[str, object]`/`object`, không bịa cấu trúc. Các field bổ sung giữ trong `extra`; field chưa được hợp đồng đảm bảo có thể optional. Kiểm tra các field bắt buộc theo từng operation trước khi trả cho caller.

Input DTO riêng cho create, update và start. DTO giữ tên snake_case đúng wire contract; helper mới nhận cấu trúc tiện dụng. Enum request dùng số đã có trong tài liệu. ID phải là chuỗi không rỗng và encode như một path segment. Không bắt ID phải là UUID.

## 6. Wrapper v1

### Pagination và tìm kiếm

- `profiles/groups/proxies.iter_all(...)`: lazy pagination từ page 1, không tải toàn bộ vào RAM; kiểm tra page metadata nhất quán, không lặp vô hạn, dừng khi trang rỗng hoặc hết `last_page`. Báo protocol error nếu server trả sai `current_page` hoặc metadata thiếu/sai kiểu. Không hứa snapshot nhất quán khi collection bị thay đổi đồng thời.
- `profiles/groups.find_by_name(name)`: dùng search làm bộ lọc ban đầu, duyệt mọi trang và so sánh chính xác có phân biệt hoa thường; không có thì `None`, nhiều kết quả trùng thì `GPMAmbiguousMatchError`.
- Không có `get_or_create`/`ensure` ở v1: API không đảm bảo unique name hoặc create idempotent, nên helper kiểu này dễ tạo hiểu nhầm về concurrency.

### Cấu hình profile

- `profiles.set_proxy(profile_id, raw_proxy, *, name=None)` và `clear_proxy(profile_id, *, name=None)`: clear gửi `raw_proxy=""`; nếu không truyền name thì GET profile để lấy tên, sau đó update kèm name cho tương thích bảng vendor. Đây là best effort, không phải transaction; ghi rõ nguy cơ ghi đè tên khi caller khác rename đồng thời. Low-level update không tự GET hoặc bổ sung name.
- `build_start_options(window_size=(width, height), window_pos=(x, y), ...)`: validate tuple, serialize thành chuỗi `width,height` và `x,y`; kích thước dương, tọa độ được phép âm; giữ đúng key `addition_args`. Flags nhận chuỗi nguyên bản; không tự ghép list khi chưa có quy tắc escape.
- `join_startup_urls(urls: Sequence[str]) -> str`: nối bằng newline; từ chối phần tử rỗng hoặc chứa CR/LF; không tự mở URL.
- Validation có ngữ cảnh: create với WebRTC fixed cần IP; update chỉ đòi IP cùng request khi request đặt `webrtc_mode=2`, không suy luận đầy đủ trạng thái hiện có. Phân biệt omitted, None, chuỗi rỗng, False và 0; không loại bỏ False/0. Không chuẩn hóa các field chưa có định dạng được vendor xác nhận.

### Vòng đời profile

- `client.profile_session(profile_id, *, exclusive=False, start_options=None)` là context manager; async tương ứng dùng `async with`. Bắt buộc `exclusive=True` để start và tự stop; đây là lời cam kết của caller rằng profile dành riêng cho tác vụ và chưa chạy, không phải trạng thái SDK đã kiểm chứng.
- Khóa in-process theo profile và API address dùng chung giữa các SDK client trong một process, kể cả sync + async; acquisition fail-fast nếu đã được giữ, không block event loop. Không bảo vệ giữa process/máy; caller phải dùng khóa bên ngoài nếu cần.
- Sau start thành công: validate launch rồi yield session. Nếu nhận envelope success nhưng launch malformed, vẫn thử stop vì caller đã cam kết độc quyền. Nếu timeout/start lỗi hoặc chưa xác nhận success: không tự retry/start/stop, báo khả năng trạng thái chưa xác định và yêu cầu caller reconcile bằng GPM.
- Khi thoát context: stop tối đa một lần, không xóa profile. Nếu task lỗi và cleanup cũng lỗi thì giữ lỗi task làm lỗi chính, đính kèm cleanup error đã lọc thông tin; nếu chỉ cleanup lỗi thì raise `GPMCleanupError`. Async cancellation: cleanup có thời hạn riêng 10 giây, shield khỏi cancellation của task đang chạy và phát lại cancellation sau cleanup; vẫn nhả khóa trong finally. Không đảm bảo cleanup khi process bị kill.
- `create_and_start`, batch start và bulk delete hoãn sau v1 để không che khuất trường hợp tạo thành công nhưng launch không rõ trạng thái.

### Playwright tùy chọn

- `gpmlogin_sdk.integrations.playwright` cung cấp `connect(launch, playwright, *, timeout_ms=10000)` và `connect_async(...)`; playwright instance do caller quản lý. Dùng API public `chromium.connect_over_cdp`.
- Adapter chỉ hỗ trợ GPM Chrome/Chromium. Nhận `StartResult` cùng browser kind đã xác định từ profile, từ chối Firefox trước khi attach; không giả định mọi profile là Chrome.
- Ưu tiên WebSocket URL được launch trả về, nếu không có dùng HTTP loopback từ port; kiểm tra endpoint và port hợp lệ. Không chuyển sang host ngoài loopback. Không log debugging URL.
- Dùng context có sẵn `browser.contexts[0]`, báo lỗi nếu không có; không tự tạo context thay thế. `get_or_create_page()` trả page hiện có đầu tiên hoặc tạo page trong context hiện có.
- Attachment là context manager riêng: thoát thì đóng kết nối Playwright, không gọi GPM stop; composition với `profile_session` bảo đảm detach trước stop. Caller vẫn có thể dùng adapter để attach mà không SDK start/stop.
- Bounded CDP retry chỉ cho lỗi kết nối tạm thời trước khi attach thành công, theo tổng timeout 10 giây, khoảng chờ 250 ms; không retry callback/tác vụ và không retry GPM start. Phân loại lỗi cụ thể cần xác nhận trong spike của adapter bằng phiên bản Playwright đã pin.

## 7. Transport, lỗi và an toàn

- Kiểm tra HTTP status, JSON, `success is True`, rồi shape của `data`. Không ép kiểu `success` từ chuỗi hoặc số. Query boolean thành `true`/`false`, URL encode ID/query, chỉ thêm Content-Type khi có JSON body.
- Lỗi public: `GPMError`, `GPMConfigurationError`, `GPMValidationError`, `GPMTransportError`, `GPMTimeoutError`, `GPMHTTPError`, `GPMAPIError`, `GPMProtocolError`, `GPMAmbiguousMatchError`, `GPMProfileBusyError`, `GPMCleanupError` và `GPMIntegrationError`.
- Không tự retry HTTP ở v1, kể cả GET. Phân loại operation read/mutation tường minh để mở rộng sau; start/stop/delete/extension state tuyệt đối không bị xem là read chỉ vì GET.
- Không log body, query, raw response, raw_proxy, CDP URL hoặc storage path. Lỗi mặc định chỉ có operation, HTTP status và thông điệp an toàn; vendor message/error details coi là untrusted, không đưa thẳng vào str/repr/log. Không chain raw HTTPX exception chứa request URL vào traceback public; giữ metadata đã lọc. Model chứa raw_proxy hoặc debugging endpoint dùng repr=False cho field nhạy cảm. Caller vẫn có thể chủ động đọc secret để sử dụng.
- `profiles.hard_delete(id, *, confirm=False)` chỉ gửi request khi `confirm=True`; soft delete là hàm riêng. Đây là xác nhận của chương trình gọi, SDK không hỏi qua stdin. `groups.delete` và `proxies.delete` cũng yêu cầu `confirm=True` vì tác động tài nguyên dùng chung. Không tự xóa trong finally.
- Extension scope: `group_ids=None` nghĩa global; list không rỗng được nối bằng dấu phẩy; list rỗng bị từ chối để tránh vô tình chuyển thành global. `active=False` phải được giữ nguyên.

## 8. Cấu trúc dự kiến

```text
pyproject.toml
README.md
src/gpmlogin_sdk/
  __init__.py, py.typed
  client.py, async_client.py
  config.py, errors.py, models.py, enums.py
  _serialization.py, _validation.py, _operations.py
  _transport.py, _async_transport.py, _ownership.py
  resources/
    profiles.py, groups.py, proxies.py, extensions.py, browsers.py
  helpers/
    pagination.py, profile_settings.py, session.py
  integrations/
    playwright.py
tests/
  unit/, contract/, integration/
examples/
  sync_basic.py, async_basic.py
  sync_playwright.py, async_playwright.py
docs/
  usage.md, api.md, compatibility.md
```

Mỗi resource module có cả class sync và async tường minh. Chỉ chia nhỏ module tiếp khi trách nhiệm thực tế đòi hỏi; không tạo framework/generator để tránh vài dòng lặp I/O.

## 9. Kiểm thử và tiêu chí hoàn thành

1. Unit/contract test cả sync + async cho 20 endpoint bằng HTTPX test transport: exact method/path/query/body, envelope, schema cần thiết và parity kết quả/lỗi.
2. Test config precedence, file port lỗi, False/0/empty string, unknown fields, duplicate names nhiều trang, pagination sai, extension scope rỗng và hard-delete gate.
3. Fault tests: refused connection, timeout sau mutation có thể đã được áp dụng, HTTP lỗi, non-JSON, success false và success true nhưng data sai. Không có retry mutation ngầm.
4. Session tests: khóa qua hai client sync/async cùng process, start failure, malformed launch sau success, task failure, stop failure, cancellation; chỉ stop khi có explicit exclusivity và confirmed success. Không mất lỗi ban đầu và không rò secret qua traceback/repr/log.
5. Adapter tests sync + async: thiếu optional dependency, Firefox, endpoint ngoài loopback, readiness timeout, context trống, page tồn tại/tạo mới, attach error và detach trước stop.
6. Live integration là opt-in, mặc định skip khi không có GPM; chỉ thao tác record test được cho phép. Không chạy hard-delete hoặc thay đổi extension global mặc định. Ghi riêng bằng chứng quan sát theo build GPM; không coi mock pass là live compatibility.
7. Lint/type check, build wheel/sdist, cài sạch và chạy ví dụ import sync/async; import core không yêu cầu Playwright. Mọi public function có type hints và mô tả ownership/side effects.

## 10. Trình tự triển khai dự kiến

1. Package, config, model và transport sync/async cùng contract tests lỗi.
2. Đầy đủ resources và bảng coverage 20 endpoint.
3. Wrapper pagination, name lookup và profile settings.
4. Session ownership, cleanup và cancellation.
5. Adapter Playwright sync/async độc lập core.
6. Ví dụ, tài liệu, kiểm tra build/install và live smoke test opt-in.

Kế hoạch chi tiết sau duyệt sẽ chỉ rõ file, signatures, test assertions, lệnh kiểm tra và điểm hoàn thành từng task. Không triển khai code trước khi người dùng duyệt thiết kế.

## 11. Điểm chưa được vendor bảo đảm

Đường dẫn http.port; update có bắt buộc name hay không; browser start khi đã chạy; giới hạn concurrency; schema fingerprint; clear field bằng null/empty; định dạng bypass_proxy_extensions/port_protect; thời gian sẵn sàng CDP. Không mở rộng lời hứa của SDK vượt các điểm có tài liệu hoặc bằng chứng live. Không có API kiểm tra process state, nên SDK không thể tự chứng minh ownership của browser.

## 12. Tham chiếu thư viện đã đối chiếu qua Context7

- HTTPX reusable clients: https://github.com/encode/httpx/blob/master/docs/advanced/clients.md
- HTTPX async lifecycle: https://github.com/encode/httpx/blob/master/docs/async.md
- Playwright Python public async API (CDP và browser lifecycle): https://github.com/microsoft/playwright-python/blob/main/playwright/async_api/_generated.py

Đây là thiết kế, không phải báo cáo đã chạy kiểm thử. Thư mục hiện chưa là Git repository; không tự init hoặc tạo commit chỉ để lưu thiết kế.
