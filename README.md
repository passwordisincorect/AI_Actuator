# AI_Actuator v0.2.2

AI_Actuator is a safe local MCP actuator for Windows. The AI remains the reasoning layer; AI_Actuator provides constrained filesystem and Git tools inside explicitly trusted workspaces.

## v0.2.2 highlights

v0.2.2 adds **optimistic concurrency protection** so an AI does not silently edit an out-of-date copy of a file.

- `local_read_text_file` now returns the selected numbered content plus the **SHA-256 of the complete file**.
- `local_edit_text_file` accepts optional `expected_sha256`.
- `local_write_text_file` accepts optional `expected_sha256` when overwriting.
- If the live file hash differs from the expected hash, AI_Actuator raises a structured `file_changed` tool error and **does not modify the file**.
- The live file is checked again immediately before the atomic replacement to reduce read/check/write race risk.
- Backups are created from the exact byte snapshot that was hash-checked, rather than re-reading the live file.
- Audit events record `expected_sha256`, `before_sha256`, and `after_sha256` on guarded success, and expected/actual hashes on conflicts.

v0.2.1 safety history remains:

- Automatic backup before overwrite/edit.
- Rollback with a safety backup of the current file.
- Append-only audit log.
- SHA-256 backup integrity validation.
- Up to 20 backups retained per file.

v0.2.0 remote architecture remains:

- Local-only admin dashboard on `127.0.0.1:8765`.
- MCP + health endpoint on `127.0.0.1:8766`.
- Built-in Cloudflare Quick Tunnel manager.
- Dashboard Start/Stop/Copy URL controls.
- Dynamic Quick Tunnel hostname allowlisting in memory.
- Bearer authentication and trusted-root security policy.
- No arbitrary shell, delete tool, Codex task runner, or Claude Code agent.

## Recommended guarded edit flow

```text
local_read_text_file
  ↓
content + sha256
  ↓
AI reasons about the file
  ↓
local_edit_text_file(expected_sha256=<sha from read>)
  ↓
AI_Actuator checks the live SHA-256
  ├─ mismatch → file_changed, no write
  └─ match    → exact-match check → backup → re-check → atomic edit → audit
```

Example read result:

```json
{
  "path": "src/main.c",
  "content": "1: int main(void) { ... }",
  "sha256": "8e77...",
  "bytes": 1234,
  "start_line": 1,
  "end_line": 80,
  "total_lines": 80
}
```

Use that hash when editing:

```text
root_id: 0
path: src/main.c
old_text: speed = 1000;
new_text: speed = 2000;
expected_replacements: 1
expected_sha256: <sha256 returned by the read>
```

If VS Code, a build step, Git, or another program changes the file after the read, the edit is rejected. Re-read the file, reason again using the new content, then retry with the new SHA-256.

`expected_sha256` is optional for backward compatibility. For AI-driven edits and overwrites, passing it is strongly recommended.

## MCP tools

- `local_list_roots`
- `local_list_directory`
- `local_read_text_file` — returns content + full-file SHA-256
- `local_search_text`
- `local_write_text_file` — supports `expected_sha256` for overwrite
- `local_edit_text_file` — supports `expected_sha256`
- `local_list_backups`
- `local_rollback_text_file`
- `local_read_audit_log`
- `local_git_status`
- `local_git_diff`

## Backup / rollback / audit storage

Normally stored under:

```text
%LOCALAPPDATA%\AI_Actuator\backups\
%LOCALAPPDATA%\AI_Actuator\audit.jsonl
```

They are outside the trusted project workspace. Audit records contain metadata and hashes, never file contents or Bearer tokens.

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

From `/setup`, click **Start Tunnel** and use the generated URL in the MCP client:

```text
https://random-name.trycloudflare.com/mcp
```

Header:

```text
Authorization: Bearer <token>
```

Quick Tunnel URLs change after restart and are intended for development/testing.

## Security defaults

- Servers bind only to `127.0.0.1`.
- `/setup` stays isolated on port 8765 and is not exposed by the built-in tunnel.
- MCP Host validation remains enabled.
- Default workspace permission is `read-only`.
- Paths must be relative to a configured trusted root.
- Path traversal, sensitive paths, symlinks/junctions/reparse points are blocked.
- Read/write text size is limited to about 1 MB per file.
- Existing files too large for a safety backup are refused for overwrite/edit.
- No arbitrary shell or permanent delete tool.

Do not grant an entire drive such as `D:\` with `workspace-write`; grant only the project folders the AI actually needs.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

v0.2.2 adds tests for stale edit rejection, stale overwrite rejection, guarded success, missing-file conflicts, hash validation, exact checked-snapshot backups, and existing backup/rollback/audit/security/tunnel behavior.
