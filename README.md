# AI_Actuator

AI_Actuator là MCP server Python chạy cục bộ trên Windows, đóng vai trò **“cánh tay”**
cho ChatGPT hoặc Claude. AI chính là “bộ não”: AI đọc mã nguồn, suy luận rồi gọi các
MCP tool của AI_Actuator để thao tác trong những workspace đã được người dùng cho phép.

```text
Người dùng → ChatGPT / Claude → MCP → AI_Actuator → filesystem / Git
```

AI_Actuator không gọi thêm Codex CLI, Claude Code, coding agent, local AI/Ollama hay
API mô hình khác. Dự án cũng cố ý không cung cấp arbitrary shell và không có tool xóa file.

## Chức năng

- `local_list_roots`: liệt kê workspace được tin cậy.
- `local_list_directory`: liệt kê thư mục trong workspace.
- `local_read_text_file`: đọc file văn bản.
- `local_search_text`: tìm chuỗi trong file văn bản.
- `local_write_text_file`: tạo hoặc ghi file khi workspace có quyền ghi.
- `local_edit_text_file`: thay thế chính xác văn bản với số lần khớp bắt buộc.
- `local_git_status`: xem `git status --short`.
- `local_git_diff`: xem diff chưa commit.

## Mô hình bảo mật

- Chỉ bind tại `127.0.0.1:8765`.
- MCP yêu cầu `Authorization: Bearer <token>`.
- Chỉ truy cập các workspace được thêm tại trang setup.
- Workspace mặc định là `read-only`; phải chủ động bật `workspace-write` mới được sửa.
- Chặn path traversal, đường dẫn tuyệt đối, symlink và Windows junction/reparse point.
- Chặn `.env`, `.ssh`, `.git`, khóa/chứng thư và các đường dẫn giống credential.
- Giới hạn đọc/ghi mỗi file ở mức 1 MiB.
- Lệnh Git được cố định bằng danh sách tham số; không chạy shell tùy ý.
- Không có tool xóa file.

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

Mở trang cấu hình:

```text
http://127.0.0.1:8765/setup
```

Tại đây:

1. Thêm đường dẫn workspace cụ thể.
2. Chọn `read-only` hoặc `workspace-write`.
3. Sao chép Bearer token để cấu hình MCP client.

Cấu hình được lưu sau khi khởi động lại Windows tại:

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
| URL | `http://127.0.0.1:8765/mcp` |
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

Nguyên mẫu trước khi đưa lên repository đã kết nối MCP Inspector và thử thành công
`local_list_roots`, đọc file, exact edit trên file Windows thật. Bản mã nguồn tái tạo
trong repository cần được chạy lại bài kiểm thử end-to-end trên Windows trước khi phát hành.

Ưu tiên tiếp theo:

1. Kết nối Claude Desktop bằng local MCP.
2. Đóng gói Claude Desktop Extension `AI_Actuator.mcpb`.
3. GUI Windows: Browse Folder, Start/Stop, trạng thái kết nối, system tray và auto-start.
4. Windows installer / EXE.
5. ChatGPT remote MCP qua tunnel bảo mật ở giai đoạn sau.

Xem thêm [kiến trúc](docs/ARCHITECTURE.md) và [chính sách bảo mật](docs/SECURITY.md).

