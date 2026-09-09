# AI_Actuator

AI_Actuator là MCP server Python chạy cục bộ trên Windows, đóng vai trò **“cánh tay”**
cho ChatGPT hoặc Claude. AI chính là “bộ não”: AI đọc mã nguồn, suy luận rồi gọi các
MCP tool của AI_Actuator để thao tác trong những workspace đã được người dùng cho phép.

```text
Người dùng → ChatGPT / Claude → MCP → AI_Actuator → filesystem / Git
```

AI_Actuator không gọi thêm Codex CLI, Claude Code, coding agent, local AI/Ollama hay
API mô hình khác. Dự án cũng cố ý không cung cấp arbitrary shell và không có tool xóa file.

## Phiên bản hiện tại

`0.2.0`

## Chức năng

- `local_list_roots`: liệt kê workspace được tin cậy.
- `local_list_directory`: liệt kê thư mục trong workspace.
- `local_read_text_file`: đọc file văn bản.
- `local_search_text`: tìm chuỗi trong file văn bản.
- `local_write_text_file`: tạo hoặc ghi file khi workspace có quyền ghi.
- `local_edit_text_file`: thay thế chính xác văn bản với số lần khớp bắt buộc.
- `local_git_status`: xem `git status --short`.
- `local_git_diff`: xem diff chưa commit.

## Endpoint v0.2.0

AI_Actuator tách riêng Admin và MCP để tunnel không bao giờ phải expose trang setup:

```text
Admin:  http://127.0.0.1:8765/setup
MCP:    http://127.0.0.1:8766/mcp
Health: http://127.0.0.1:8766/health
```

Kiểm tra mong đợi:

```text
http://127.0.0.1:8766/setup  -> 404
http://127.0.0.1:8765/mcp    -> 404
http://127.0.0.1:8766/mcp    -> 401 nếu không có Bearer token
```

Nếu dùng Cloudflare Tunnel ở bước tiếp theo, tunnel phải trỏ vào `127.0.0.1:8766`,
không phải port Admin `8765`.

## Mô hình bảo mật

- Cả hai server chỉ bind loopback tại `127.0.0.1`.
- Admin dashboard ở port `8765` và được HostGuard giới hạn local-only.
- MCP ở port `8766` và yêu cầu `Authorization: Bearer <token>`.
- Chỉ truy cập các workspace được thêm tại trang setup.
- Workspace mặc định là `read-only`; phải chủ động bật `workspace-write` mới được sửa.
- Chặn path traversal, đường dẫn tuyệt đối, symlink và Windows junction/reparse point.
- Chặn `.env`, `.ssh`, `.git`, khóa/chứng thư và các đường dẫn giống credential.
- Giới hạn đọc/ghi mỗi file ở mức 1 MiB.
- Lệnh Git được cố định bằng danh sách tham số; không chạy shell tùy ý.
- Không có tool xóa file.
- MCP Inspector từ browser chỉ được CORS cho origin loopback.

Không nên cấp toàn bộ ổ `C:\` hoặc `D:\`. Hãy chỉ cấp thư mục dự án cụ thể, ví dụ
`D:\STM32\StepperMotorLCD`.

## Cài đặt trên Windows

Yêu cầu Python 3.10 trở lên.

```powershell
cd D:\AI_Actuator
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Chạy server:

```powershell
.\.venv\Scripts\python.exe -m ai_actuator
```

Hoặc nhấp đúp `run.bat`.

Khi chạy đúng v0.2.0, terminal sẽ hiển thị các endpoint Admin, MCP và Health riêng biệt.

Mở trang cấu hình:

```text
http://127.0.0.1:8765/setup
```

Tại đây:

1. Thêm đường dẫn workspace cụ thể.
2. Chọn `read-only` hoặc `workspace-write`.
3. Sao chép Bearer token để cấu hình MCP client.

Cấu hình được lưu tại:

```text
%LOCALAPPDATA%\AI_Actuator\config.json
```

Nếu chỉ có cấu hình cũ tại `%LOCALAPPDATA%\AIArmBridge\config.json`, chương trình sẽ
nhập cấu hình đó vào vị trí mới trong lần chạy đầu tiên.

## Kết nối MCP Inspector

```powershell
npx @modelcontextprotocol/inspector
```

Thiết lập:

| Trường | Giá trị |
| --- | --- |
| Transport | `Streamable HTTP` |
| URL | `http://127.0.0.1:8766/mcp` |
| Header | `Authorization` |
| Value | `Bearer <token-trên-trang-setup>` |

Nếu mở `/mcp` trực tiếp bằng Chrome và thấy `{"error":"unauthorized"}` thì đó là
hành vi đúng: trình duyệt không tự gửi Bearer token.

## Quy trình chỉnh sửa khuyến nghị

```text
local_search_text
  → local_read_text_file
  → AI phân tích
  → local_edit_text_file
  → local_read_text_file
  → local_git_diff
```

`local_edit_text_file` chỉ ghi khi số lần `old_text` xuất hiện đúng bằng
`expected_replacements`, nhờ đó tránh thay nhầm nhiều vị trí.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

## Build EXE

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

File dự kiến:

```text
dist\AI_Actuator.exe
```

## Trạng thái và hướng phát triển

Đã xác nhận trong quá trình phát triển local: MCP Inspector kết nối được, `local_list_roots`,
đọc file và exact edit trên file Windows thật đã hoạt động. v0.2.0 bổ sung kiến trúc split-port
để chuẩn bị tunnel an toàn chỉ vào MCP port `8766`.

Ưu tiên tiếp theo:

1. Hoàn thiện Cloudflare / secure tunnel vào `127.0.0.1:8766`.
2. Kiểm tra remote MCP end-to-end.
3. Claude Desktop Extension `AI_Actuator.mcpb`.
4. GUI Windows: Browse Folder, Start/Stop, trạng thái kết nối, system tray và auto-start.
5. Windows installer / EXE.

Xem thêm [kiến trúc](docs/ARCHITECTURE.md) và [chính sách bảo mật](docs/SECURITY.md).
