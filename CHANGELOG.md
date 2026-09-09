# Changelog

Tất cả thay đổi đáng chú ý của AI_Actuator sẽ được ghi lại tại đây.

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
- Giới hạn đọc/ghi file ở mức 1 MiB.
- Git chỉ chạy các lệnh read-only đã cố định, không cung cấp arbitrary shell.
- Lưu cấu hình tại `%LOCALAPPDATA%\AI_Actuator\config.json` và hỗ trợ migrate từ `AIArmBridge`.
- Có test cho operations và security policy.
- Có script chạy Windows và script build EXE bằng PyInstaller.

### Chưa thuộc v0.1.0

- Cloudflare / remote MCP cho ChatGPT.
- Claude Desktop Extension `.mcpb`.
- GUI Windows, system tray và auto-start.
- Windows installer hoàn chỉnh.

### Ghi chú

Bản v0.1.0 nên được xem là bản phát hành đầu tiên của local MCP prototype. Cần chạy lại kiểm thử end-to-end trên Windows trước khi coi là bản production-ready.
