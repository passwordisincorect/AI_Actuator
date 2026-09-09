# Kiến trúc AI_Actuator

## Vai trò

AI_Actuator chỉ là lớp thực thi công cụ cục bộ. Nó không tự suy luận và không gọi AI khác.

```text
MCP client
   │  Streamable HTTP + Bearer token
   ▼
AI_Actuator (127.0.0.1:8765)
   ├── ConfigStore
   ├── SecurityPolicy
   └── LocalOperations
          ├── filesystem giới hạn
          └── git status / diff cố định
```

## Thành phần

- `config.py`: tạo token, lưu cấu hình, nhập cấu hình tên cũ.
- `security.py`: giải quyết workspace/path và áp dụng sandbox.
- `ops.py`: thao tác file, tìm kiếm và Git; không chứa arbitrary shell.
- `server.py`: đăng ký MCP tools, Bearer middleware và dashboard `/setup`.
- `__main__.py`: entry point Uvicorn bind localhost.

## Quyền workspace

| Chế độ | List/read/search | Git status/diff | Write/edit |
| --- | ---: | ---: | ---: |
| `read-only` | Có | Có | Không |
| `workspace-write` | Có | Có | Có |

Mỗi tool nhận `workspace` là tên đã cấu hình và `path` tương đối bên trong workspace.
Đường dẫn tuyệt đối không được MCP tool chấp nhận.

## Phạm vi cố ý loại trừ

- Không gọi Codex/Claude Code hoặc agent phụ.
- Không chạy lệnh shell tùy ý.
- Không xóa file.
- Không cấp toàn bộ filesystem theo mặc định.
- Không public server ra Internet trong bản local.

