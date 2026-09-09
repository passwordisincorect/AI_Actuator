# Changelog

Tất cả thay đổi đáng chú ý của AI_Actuator sẽ được ghi lại tại đây.

## [0.2.0] - 2026-09-09

Bản 0.2.0 đồng bộ với phần đã hoàn thiện trong quá trình phát triển AI_Actuator.

### Thay đổi

- Nâng version project và package lên `0.2.0`.
- Tách Admin dashboard và MCP transport thành hai cổng riêng:
  - Admin: `http://127.0.0.1:8765/setup`
  - MCP: `http://127.0.0.1:8766/mcp`
  - Health: `http://127.0.0.1:8766/health`
- Port MCP không phục vụ `/setup`; port Admin không phục vụ `/mcp`.
- `/mcp` vẫn yêu cầu `Authorization: Bearer <token>`.
- Thêm CORS giới hạn cho MCP Inspector chạy từ origin loopback.
- Giữ nguyên trusted workspace, `read-only` / `workspace-write`, exact edit và các lớp SecurityPolicy hiện có.

### Phạm vi hiện tại

- MCP server local trên Windows.
- Bearer authentication.
- Trusted workspaces với `read-only` và `workspace-write`.
- Đọc, tìm kiếm, ghi và exact-edit file văn bản.
- `git status` và `git diff` read-only.
- SecurityPolicy chống path traversal, symlink/reparse point và truy cập đường dẫn nhạy cảm.
- Admin/MCP split-port để chuẩn bị tunnel chỉ vào port `8766`.

### Chưa triển khai trong v0.2.0

- Cloudflare Tunnel / remote MCP hoàn chỉnh cho ChatGPT.
- Claude Desktop Extension `.mcpb`.
- GUI Windows, system tray và auto-start.
- Windows installer hoàn chỉnh.

## [0.1.2] - 2026-09-09

Bản cập nhật maintenance cho nhánh 0.1.x.

### Thay đổi

- Đồng bộ phiên bản package và project lên `0.1.2`.
- Giữ nguyên phạm vi chức năng local MCP đã có ở v0.1.0.
- Chuẩn hóa mốc phát hành tiếp theo cho quá trình phát triển Cloudflare / remote MCP.

### Chưa thuộc v0.1.2

- Cloudflare / remote MCP cho ChatGPT.
- Claude Desktop Extension `.mcpb`.
- GUI Windows, system tray và auto-start.
- Windows installer hoàn chỉnh.

## [0.1.0] - 2026-09-09

Bản phát hành đầu tiên của AI_Actuator: MCP server Python chạy cục bộ trên Windows, cho phép AI thao tác an toàn trong các workspace được người dùng cấp quyền.

### Hoàn thiện

- MCP server Streamable HTTP chạy tại `127.0.0.1:8765`.
- Trang `/setup` để quản lý Bearer token và trusted workspaces.
- Quyền workspace `read-only` và `workspace-write`.
- Các MCP tool:
  - `local_list_roots`
  - `local_list_directory`
  - `local_read_text_file`
  - `local_search_text`
  - `local_write_text_file`
  - `local_edit_text_file`
  - `local_git_status`
  - `local_git_diff`
- Exact-edit với `expected_replacements` để tránh sửa nhầm vị trí.
- Bảo vệ path traversal, absolute path, symlink và Windows reparse point.
- Chặn các đường dẫn/file nhạy cảm như `.env`, `.ssh`, `.git`, credential và private key.
- Giới hạn đọc/ghi mỗi file ở mức 1 MiB.
- Git chỉ chạy các lệnh read-only đã cố định, không cung cấp arbitrary shell.
- Lưu cấu hình tại `%LOCALAPPDATA%\AI_Actuator\config.json` và hỗ trợ migrate từ `AIArmBridge`.
- Có test cho operations và security policy.
- Có script chạy Windows và script build EXE bằng PyInstaller.
