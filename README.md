# AI_Actuator v0.2.1

AI_Actuator is a safe local MCP actuator for Windows. The AI remains the reasoning layer; AI_Actuator provides constrained filesystem and Git tools inside explicitly trusted workspaces.

## v0.2.1 highlights

v0.2.1 keeps the v0.2.0 split-port + Cloudflare remote MCP architecture and adds a safety history layer for write operations:

- **Automatic backup before overwrite/edit**.
- **Rollback tool** that restores a selected backup.
- Rollback first creates a **safety backup of the current file**, so a rollback itself can be reversed.
- **Append-only audit log** for write/edit/rollback success and failures.
- Audit entries contain metadata and SHA-256 hashes, **never file contents or Bearer tokens**.
- Backup integrity is checked using SHA-256 before restore.
- Up to 20 automatic backups are retained per file.
- Audit log rotates at roughly 5 MB.

v0.2.0 features remain:

- Local-only admin dashboard on `127.0.0.1:8765`.
- MCP + health endpoint on `127.0.0.1:8766`.
- Built-in Cloudflare Quick Tunnel manager.
- Dashboard **Start Tunnel / Stop Tunnel / Copy URL** controls.
- Dynamic Quick Tunnel hostname allowlisting in memory.
- Optional tunnel auto-start.
- Bearer authentication enabled by default.
- No arbitrary shell, delete tool, Codex task runner, or Claude Code agent.

## MCP tools

- `local_list_roots`
- `local_list_directory`
- `local_read_text_file`
- `local_search_text`
- `local_write_text_file`
- `local_edit_text_file`
- `local_list_backups` **new in v0.2.1**
- `local_rollback_text_file` **new in v0.2.1**
- `local_read_audit_log` **new in v0.2.1**
- `local_git_status`
- `local_git_diff`

## Backup / rollback flow

When an existing file is overwritten or exact-edited:

```text
existing file
   ↓
automatic backup + SHA-256
   ↓
atomic write/edit
   ↓
audit event
```

To restore an older version:

1. Call `local_list_backups` with `root_id` and a relative `path`.
2. Copy the desired `backup_id`.
3. Call `local_rollback_text_file` with the same root/path and `backup_id`.
4. AI_Actuator backs up the current file before restoring the older snapshot.

Backups and audit history are stored next to the AI_Actuator config, normally:

```text
%LOCALAPPDATA%\AI_Actuator\backups\
%LOCALAPPDATA%\AI_Actuator\audit.jsonl
```

They are not stored inside the trusted project workspace.

## Install / upgrade

```powershell
cd D:\AI_Actuator
.\.venv\Scripts\python.exe -m pip install -e .
```

Run:

```powershell
.\.venv\Scripts\python.exe -m ai_actuator
```

Dashboard:

```text
http://127.0.0.1:8765/setup
```

Local MCP:

```text
http://127.0.0.1:8766/mcp
```

Health:

```text
http://127.0.0.1:8766/health
```

## Cloudflare Quick Tunnel

From `/setup`, click **Start Tunnel**. The dashboard displays a URL such as:

```text
https://random-name.trycloudflare.com/mcp
```

Use the Bearer token from the local dashboard:

```text
Authorization: Bearer <token>
```

Quick Tunnel URLs change after restart and are intended for testing/development.

## Security defaults

- Servers bind only to `127.0.0.1`.
- `/setup` is isolated on port 8765 and is not exposed by the built-in tunnel.
- MCP Host validation remains enabled.
- Default workspace permission is `read-only`.
- Paths must be relative to a configured trusted root.
- Path traversal, sensitive paths, symlinks/junctions/reparse points remain blocked.
- Read/write text size is limited to about 1 MB per file.
- Existing files larger than the backup safety limit are refused for overwrite because they cannot be safely snapshotted.
- No arbitrary shell or permanent delete tool.

Do not grant an entire drive such as `D:\` with `workspace-write`; grant only the project folders the AI actually needs.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

The v0.2.1 source package includes tests for backup integrity, rollback, audit logging, existing security rules, and Quick Tunnel parsing/management.
