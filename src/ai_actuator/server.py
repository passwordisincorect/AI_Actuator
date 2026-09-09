from __future__ import annotations

import html
from pathlib import Path
from urllib.parse import parse_qs

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from starlette.routing import Route

from . import __version__
from .config import ActuatorConfig, default_config_path, load_config, save_config
from .ops import WorkspaceOps
from .runtime import RuntimeState, create_runtime
from .security import ActuatorSecurityError
from .tunnel import TunnelError


def _as_tool_error(exc: Exception) -> ToolError:
    return ToolError(str(exc))


def build_mcp(config_path: Path | None = None) -> tuple[MCPServer, ActuatorConfig, WorkspaceOps]:
    path = config_path or default_config_path()
    cfg = load_config(path)
    ops = WorkspaceOps(cfg, state_dir=path.parent)
    mcp = MCPServer("AI_Actuator")

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    def local_list_roots() -> list[dict[str, object]]:
        """List trusted local workspace roots and their root_id values."""
        return ops.list_roots()

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    def local_list_directory(root_id: int = 0, path: str = "") -> list[dict[str, object]]:
        """List files/directories under a trusted root. Paths must be relative."""
        try:
            return ops.list_directory(root_id, path)
        except (ActuatorSecurityError, OSError) as exc:
            raise _as_tool_error(exc)

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    def local_read_text_file(root_id: int, path: str, start_line: int = 1, end_line: int = 400) -> str:
        """Read up to 1000 numbered lines from a UTF-8-ish text file in a trusted workspace."""
        try:
            return ops.read_text(root_id, path, start_line, end_line)
        except (ActuatorSecurityError, OSError, UnicodeError) as exc:
            raise _as_tool_error(exc)

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    def local_search_text(root_id: int, query: str, path: str = "", max_results: int = 50) -> list[dict[str, object]]:
        """Case-insensitive text search inside a trusted workspace; returns file, line, and snippet."""
        try:
            return ops.search_text(root_id, query, path, max_results)
        except (ActuatorSecurityError, OSError) as exc:
            raise _as_tool_error(exc)

    @mcp.tool(
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        )
    )
    def local_write_text_file(root_id: int, path: str, content: str, overwrite: bool = False) -> dict[str, object]:
        """Create or overwrite one text file inside a trusted workspace. Requires workspace-write permission."""
        try:
            return ops.write_text(root_id, path, content, overwrite)
        except (ActuatorSecurityError, OSError) as exc:
            raise _as_tool_error(exc)

    @mcp.tool(
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        )
    )
    def local_edit_text_file(
        root_id: int,
        path: str,
        old_text: str,
        new_text: str,
        expected_replacements: int = 1,
    ) -> dict[str, object]:
        """Exact-match text edit with a required replacement count. No change occurs if the count differs."""
        try:
            return ops.edit_text(root_id, path, old_text, new_text, expected_replacements)
        except (ActuatorSecurityError, OSError, UnicodeError) as exc:
            raise _as_tool_error(exc)

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    def local_list_backups(root_id: int = 0, path: str = "", limit: int = 20) -> list[dict[str, object]]:
        """List automatic text-file backups for a trusted root/path. Paths must be relative."""
        try:
            return ops.list_backups(root_id, path, limit)
        except (ActuatorSecurityError, OSError) as exc:
            raise _as_tool_error(exc)

    @mcp.tool(
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        )
    )
    def local_rollback_text_file(root_id: int, path: str, backup_id: str) -> dict[str, object]:
        """Restore a text file from one AI_Actuator backup. The current file is backed up first."""
        try:
            return ops.rollback_text(root_id, path, backup_id)
        except (ActuatorSecurityError, OSError, UnicodeError) as exc:
            raise _as_tool_error(exc)

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    def local_read_audit_log(limit: int = 50) -> list[dict[str, object]]:
        """Read recent AI_Actuator write/edit/rollback audit events. File contents are never logged."""
        try:
            return ops.read_audit_log(limit)
        except OSError as exc:
            raise _as_tool_error(exc)

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    def local_git_status(root_id: int = 0, path: str = "") -> str:
        """Run 'git status --short --branch' in a trusted workspace. Does not execute arbitrary shell commands."""
        try:
            return ops.git_status(root_id, path)
        except (ActuatorSecurityError, OSError) as exc:
            raise _as_tool_error(exc)

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    def local_git_diff(root_id: int = 0, path: str = "") -> str:
        """Return the current Git working-tree diff for a trusted workspace."""
        try:
            return ops.git_diff(root_id, path)
        except (ActuatorSecurityError, OSError) as exc:
            raise _as_tool_error(exc)

    return mcp, cfg, ops


class BearerGuard:
    """Protect only the MCP endpoint with the configured Bearer token."""

    def __init__(self, app, cfg: ActuatorConfig):
        self.app = app
        self.cfg = cfg

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope.get("headers", [])}

        if path.startswith("/mcp") and self.cfg.require_token:
            expected = f"Bearer {self.cfg.bearer_token}"
            if headers.get("authorization", "") != expected:
                response = JSONResponse(
                    {"error": "unauthorized"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


class LocalAdminGuard:
    """Defense in depth: reject the admin dashboard when Host is not loopback."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope.get("headers", [])}
        host = headers.get("host", "").split(":", 1)[0].strip("[]").lower()

        if host not in {"127.0.0.1", "localhost", "::1"}:
            response = PlainTextResponse("Dashboard is local-only.", status_code=403)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


def build_mcp_app(runtime_or_path: RuntimeState | Path | None = None):
    runtime = runtime_or_path if isinstance(runtime_or_path, RuntimeState) else create_runtime(runtime_or_path)
    mcp, cfg, _ops = build_mcp(runtime.config_path)

    app = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        host=cfg.host,
        transport_security=runtime.transport_security,
    )

    async def health(_request: Request):
        tunnel_status = runtime.tunnel.status()
        return JSONResponse(
            {
                "status": "ok",
                "name": "AI_Actuator",
                "version": __version__,
                "permission": cfg.permission,
                "roots": len(cfg.roots),
                "tunnel": "connected" if tunnel_status.running else "disconnected",
            }
        )

    app.routes.insert(0, Route("/health", health, methods=["GET"]))
    guarded = BearerGuard(app, cfg)

    cors_app = CORSMiddleware(
        guarded,
        allow_origin_regex=r"^https?://(?:127\.0\.0\.1|localhost|\[::1\])(?::\d+)?$",
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Accept",
            "Mcp-Session-Id",
            "Mcp-Protocol-Version",
            "Mcp-Method",
            "Mcp-Name",
            "Last-Event-ID",
        ],
        expose_headers=["Mcp-Session-Id"],
        max_age=600,
    )
    return cors_app, cfg


def build_admin_app(runtime_or_path: RuntimeState | Path | None = None):
    runtime = runtime_or_path if isinstance(runtime_or_path, RuntimeState) else create_runtime(runtime_or_path)
    path = runtime.config_path
    cfg = runtime.cfg

    async def home(_request: Request):
        return RedirectResponse("/setup")

    async def setup(request: Request):
        if request.method == "POST":
            raw = (await request.body()).decode("utf-8", errors="replace")
            form = parse_qs(raw, keep_blank_values=True)
            action = form.get("action", ["save"])[0]

            if action == "start_tunnel":
                try:
                    runtime.start_quick_tunnel()
                except TunnelError:
                    pass
                return RedirectResponse("/setup", status_code=303)

            if action == "stop_tunnel":
                runtime.stop_quick_tunnel()
                return RedirectResponse("/setup", status_code=303)

            roots_text = form.get("roots", [""])[0]
            permission = form.get("permission", ["read-only"])[0]
            require_token = form.get("require_token", [""])[0] == "on"
            allowed_hosts_text = form.get("allowed_hosts", [""])[0]
            cloudflared_path = form.get("cloudflared_path", [""])[0].strip()
            tunnel_auto_start = form.get("tunnel_auto_start", [""])[0] == "on"

            cfg.roots = [line.strip() for line in roots_text.splitlines() if line.strip()]
            cfg.permission = permission if permission in {"read-only", "workspace-write"} else "read-only"
            cfg.require_token = require_token
            cfg.allowed_hosts = [line.strip() for line in allowed_hosts_text.splitlines() if line.strip()]
            cfg.cloudflared_path = cloudflared_path
            cfg.tunnel_auto_start = tunnel_auto_start
            runtime.tunnel.configured_cloudflared_path = cloudflared_path
            save_config(cfg, path)
            return RedirectResponse("/setup?saved=1", status_code=303)

        roots = "\n".join(cfg.roots)
        allowed_hosts = "\n".join(cfg.allowed_hosts)
        checked_ro = "selected" if cfg.permission == "read-only" else ""
        checked_wr = "selected" if cfg.permission == "workspace-write" else ""
        token_checked = "checked" if cfg.require_token else ""
        auto_start_checked = "checked" if cfg.tunnel_auto_start else ""

        tunnel_status = runtime.tunnel.status()
        tunnel_label = "Connected" if tunnel_status.running else "Disconnected"
        tunnel_class = "ok" if tunnel_status.running else "muted"
        public_mcp_url = tunnel_status.public_mcp_url or "—"
        cloudflared_display = tunnel_status.cloudflared_path or cfg.cloudflared_path or "auto-discover"
        tunnel_error = tunnel_status.error or ""
        tunnel_error_html = f"<p class='warn'><b>Tunnel error:</b> {html.escape(tunnel_error)}</p>" if tunnel_error else ""
        logs = "\n".join(runtime.tunnel.recent_logs(8))
        logs_html = f"<details><summary>Recent cloudflared logs</summary><pre>{html.escape(logs)}</pre></details>" if logs else ""
        start_disabled = "disabled" if tunnel_status.running else ""
        stop_disabled = "" if tunnel_status.running else "disabled"

        body = f"""
<!doctype html><html><head><meta charset='utf-8'><title>AI_Actuator</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;max-width:960px;margin:40px auto;padding:0 20px;background:#f6f7f9;color:#16181d}}
.card{{background:white;border:1px solid #d9dde5;border-radius:14px;padding:22px;margin:16px 0;box-shadow:0 2px 8px #0000000d}}
textarea,input,select{{width:100%;box-sizing:border-box;padding:10px;border:1px solid #bcc3ce;border-radius:8px;font:inherit}}
label{{font-weight:600;display:block;margin:14px 0 6px}} button{{padding:10px 18px;border:0;border-radius:8px;background:#16181d;color:white;font-weight:600;cursor:pointer;margin-right:8px}}
button:disabled{{opacity:.45;cursor:not-allowed}} code{{background:#eef0f4;padding:2px 6px;border-radius:5px;overflow-wrap:anywhere}}
.warn{{color:#9b4d00}} .ok{{color:#166534}} .muted,small{{color:#616975}} pre{{white-space:pre-wrap;word-break:break-word}}
.row{{display:flex;gap:10px;flex-wrap:wrap;align-items:center}} .copy{{background:#374151}}
</style></head><body>
<h1>AI_Actuator <small>v{html.escape(__version__)}</small></h1>
<p>Local MCP “cánh tay” cho AI: đọc, tìm, sửa file và xem Git diff. Không có Agent/task runner.</p>
<div class='card'>
<b>Admin dashboard:</b> <code>http://{html.escape(cfg.host)}:{cfg.admin_port}/setup</code><br><br>
<b>Local MCP:</b> <code>http://{html.escape(cfg.host)}:{cfg.mcp_port}/mcp</code><br><br>
<b>Health:</b> <code>http://{html.escape(cfg.host)}:{cfg.mcp_port}/health</code><br><br>
<b>Bearer token:</b> <code>{html.escape(cfg.bearer_token)}</code><br>
<small>Giữ token này bí mật nếu bạn đưa MCP endpoint ra ngoài máy.</small>
</div>

<div class='card'>
<h2>Safety History — v0.2.1</h2>
<p><b>Automatic backups:</b> <code>{html.escape(str(path.parent / 'backups'))}</code></p>
<p><b>Audit log:</b> <code>{html.escape(str(path.parent / 'audit.jsonl'))}</code></p>
<p class='muted'>Mỗi lần overwrite/edit sẽ tạo backup trước khi ghi. Rollback cũng tạo safety backup của trạng thái hiện tại, nên có thể hoàn tác lần rollback tiếp theo.</p>
</div>

<div class='card'>
<h2>Remote Access — Cloudflare Quick Tunnel</h2>
<p>Status: <b class='{tunnel_class}'>{tunnel_label}</b></p>
<p>cloudflared: <code>{html.escape(cloudflared_display)}</code></p>
<p>Public MCP URL: <code id='public-mcp'>{html.escape(public_mcp_url)}</code></p>
<div class='row'>
<form method='post'><input type='hidden' name='action' value='start_tunnel'><button type='submit' {start_disabled}>Start Tunnel</button></form>
<form method='post'><input type='hidden' name='action' value='stop_tunnel'><button type='submit' {stop_disabled}>Stop Tunnel</button></form>
<button class='copy' type='button' onclick="copyMcp()" {'disabled' if not tunnel_status.running else ''}>Copy URL</button>
</div>
{tunnel_error_html}
{logs_html}
<p class='muted'>Quick Tunnel URL thay đổi mỗi lần khởi động. AI_Actuator tự thêm hostname hiện tại vào MCP Host allowlist trong RAM.</p>
</div>

<form method='post' class='card'>
<input type='hidden' name='action' value='save'>
<h2>Configuration</h2>
<label>Trusted workspace roots — mỗi dòng một thư mục</label>
<textarea name='roots' rows='6' placeholder='D:\\STM32\\MyProject'>{html.escape(roots)}</textarea>
<label>Quyền</label><select name='permission'><option value='read-only' {checked_ro}>read-only (khuyên dùng lúc đầu)</option><option value='workspace-write' {checked_wr}>workspace-write</option></select>
<label><input style='width:auto' type='checkbox' name='require_token' {token_checked}> Yêu cầu Bearer token cho /mcp</label>
<label>Allowed hosts cố định cho named tunnel/domain — mỗi dòng một host</label>
<textarea name='allowed_hosts' rows='3' placeholder='mcp.example.com\nmcp.example.com:*'>{html.escape(allowed_hosts)}</textarea>
<label>cloudflared path (để trống để auto-discover)</label>
<input name='cloudflared_path' value='{html.escape(cfg.cloudflared_path, quote=True)}' placeholder='D:\\AI_Actuator\\cloudflared.exe'>
<label><input style='width:auto' type='checkbox' name='tunnel_auto_start' {auto_start_checked}> Tự khởi động Quick Tunnel cùng AI_Actuator</label>
<p class='warn'>Thay đổi trusted roots, permission hoặc allowed hosts cố định cần restart AI_Actuator để MCP tools áp dụng đầy đủ. Start/Stop Quick Tunnel không cần restart.</p>
<button type='submit'>Lưu cấu hình</button></form>
<div class='card'><b>Tools:</b><pre>local_list_roots\nlocal_list_directory\nlocal_read_text_file\nlocal_search_text\nlocal_write_text_file\nlocal_edit_text_file\nlocal_list_backups\nlocal_rollback_text_file\nlocal_read_audit_log\nlocal_git_status\nlocal_git_diff</pre></div>
<script>
async function copyMcp(){{
  const value = document.getElementById('public-mcp').textContent.trim();
  if (!value || value === '—') return;
  try {{ await navigator.clipboard.writeText(value); }}
  catch (_) {{ window.prompt('Copy MCP URL:', value); }}
}}
</script>
</body></html>"""
        return HTMLResponse(body)

    app = Starlette(
        routes=[
            Route("/", home, methods=["GET"]),
            Route("/setup", setup, methods=["GET", "POST"]),
        ]
    )
    return LocalAdminGuard(app), cfg
