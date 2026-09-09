# Upgrade AI_Actuator v0.2.0 → v0.2.1

1. Stop AI_Actuator with `Ctrl+C`.
2. If a manually started cloudflared process is still running, stop it too.
3. Copy the v0.2.1 patch files over `D:\AI_Actuator`.
4. Keep your existing `.venv`, `cloudflared.exe`, and `%LOCALAPPDATA%\AI_Actuator\config.json`.
5. Reinstall editable package metadata:

```powershell
cd D:\AI_Actuator
.\.venv\Scripts\python.exe -m pip install -e .
```

6. Start v0.2.1:

```powershell
.\.venv\Scripts\python.exe -m ai_actuator
```

7. Open `http://127.0.0.1:8765/setup` and verify the dashboard shows `v0.2.1` and the Safety History paths.
8. Reconnect MCP Inspector. Three new tools should appear:

```text
local_list_backups
local_rollback_text_file
local_read_audit_log
```

## Safe test

Create or edit a small test file, then run:

```text
local_list_backups
```

Select the returned `backup_id`, then test:

```text
local_rollback_text_file
```

Finally inspect:

```text
local_read_audit_log
```

Expected local state files:

```text
%LOCALAPPDATA%\AI_Actuator\backups\
%LOCALAPPDATA%\AI_Actuator\audit.jsonl
```
