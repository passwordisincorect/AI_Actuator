# Upgrade AI_Actuator v0.2.1 → v0.2.2

v0.2.2 adds SHA-256 optimistic concurrency guards to write/edit workflows.

## Install the patch

1. Stop AI_Actuator with `Ctrl+C`.
2. Copy the v0.2.2 patch files over `D:\AI_Actuator`.
3. Keep your existing `.venv`, `cloudflared.exe`, and `%LOCALAPPDATA%\AI_Actuator\config.json`.
4. Reinstall the editable package:

```powershell
cd D:\AI_Actuator
.\.venv\Scripts\python.exe -m pip install -e .
```

5. Start AI_Actuator:

```powershell
.\.venv\Scripts\python.exe -m ai_actuator
```

6. Reconnect MCP Inspector so it reloads the updated tool schemas.

## What changed

`local_read_text_file` now returns an object containing numbered `content` plus `sha256` for the whole file.

Both mutation tools now accept:

```text
expected_sha256
```

Use the SHA-256 from the latest read when calling `local_edit_text_file`, or when calling `local_write_text_file` with `overwrite=true`.

On stale state, the tool returns a `file_changed` error containing expected and actual SHA-256 values, and makes no change.

The field remains optional so older MCP clients still work, but guarded edits are the recommended workflow.
