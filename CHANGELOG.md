# Changelog

## [0.2.2] - 2026-09-09

Optimistic-concurrency safety release.

### Added

- `local_read_text_file` returns full-file SHA-256 with the selected numbered content.
- Optional `expected_sha256` guard for `local_edit_text_file`.
- Optional `expected_sha256` guard for overwrite operations in `local_write_text_file`.
- Structured `file_changed` tool errors with expected/actual hashes.
- Immediate live-hash re-check before atomic replacement.
- Backup creation from the exact hash-checked byte snapshot.
- Audit conflict events and expected/before/after SHA-256 metadata.

### Safety behavior

If a file changes after the AI read it, a guarded write/edit is rejected without modifying the live file. The AI should re-read, re-evaluate, and retry with the new hash.

### Compatibility

`expected_sha256` is optional to preserve existing clients. Backup, rollback, audit, split ports, Bearer auth, trusted roots, and Cloudflare Quick Tunnel behavior from v0.2.1 remain available.

## [0.2.1] - 2026-09-09

Safety hardening release for remote/local write workflows.

### Added

- Automatic snapshot before overwriting an existing text file.
- Automatic snapshot before `local_edit_text_file` changes a file.
- `local_list_backups` to inspect retained backups.
- `local_rollback_text_file` to restore one backup.
- Rollback safety snapshot of the current file before restore.
- `local_read_audit_log` for recent mutation events.
- SHA-256 stored with backup metadata and verified before rollback.
- SHA-256 before/after values in mutation audit metadata.
- Per-file retention cap of 20 backups.
- Audit log rotation around 5 MB.

### Security

- Backup files live outside trusted project roots under the AI_Actuator state directory.
- User-controlled paths are never used as backup filenames.
- Audit log stores metadata only; file contents and Bearer tokens are not logged.
- Overwrite is refused when the previous file is too large to snapshot safely.

### Retained from 0.2.0

- Admin `127.0.0.1:8765` and MCP `127.0.0.1:8766` split.
- `/health` endpoint.
- Cloudflare Quick Tunnel integration with Start/Stop/Copy URL.
- Dynamic trycloudflare hostname allowlisting.
- Bearer authentication and trusted-root filesystem policy.

## [0.2.0] - 2026-09-09

- Split local admin and MCP transports onto ports 8765 and 8766.
- Added `/health`.
- Added built-in Cloudflare Quick Tunnel manager and dashboard controls.
- Added dynamic Quick Tunnel host allowlisting in memory.
