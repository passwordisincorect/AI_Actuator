from __future__ import annotations

import contextlib
import hmac
import html
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs

from mcp.server.mcpserver import MCPServer
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from . import __version__
from .config import ConfigStore, WorkspaceConfig
from .ops import LocalOperations
from .security import (
    SecurityError,
    SecurityPolicy,
    validate_workspace_name,
    validate_workspace_root,
)

HOST = "127.0.0.1"
ADMIN_PORT = 8765
MCP_PORT = 8766
# Backward-compatible alias for code that used PORT as the local setup port.
PORT = ADMIN_PORT

store = ConfigStore()
policy = SecurityPolicy(store)
ops = LocalOperations(policy)
mcp = MCPServer("AI_Actuator")


@mcp.tool()
def local_list_roots() -> dict[str, Any]:
    """List trusted workspaces and their permission modes."""
    return ops.list_roots()


@mcp.tool()
def local_list_directory(workspace: str, path: str = ".") -> dict[str, Any]:
    """List a directory inside a trusted workspace."""
    return ops.list_directory(workspace, path)


@mcp.tool()
def local_read_text_file(workspace: str, path: str) -> dict[str, Any]:
    """Read one UTF-8 text file inside a trusted workspace."""
    return ops.read_text_file(workspace, path)


@mcp.tool()
def local_search_text(
    workspace: str,
    query: str,
    path: str = ".",
    case_sensitive: bool = False,
) -> dict[str, Any]:
    """Search UTF-8 text files inside a trusted workspace without running shell commands."""
    return ops.search_text(workspace, query, path, case_sensitive)


@mcp.tool()
def local_write_text_file(
    workspace: str,
    path: str,
    content: str,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Write a UTF-8 file in a workspace-write workspace."""
    return ops.write_text_file(workspace, path, content, overwrite)


@mcp.tool()
def local_edit_text_file(
    workspace: str,
    path: str,
    old_text: str,
    new_text: str,
    expected_replacements: int = 1,
) -> dict[str, Any]:
    """Replace exact text only when the number of matches equals expected_replacements."""
    return ops.edit_text_file(
        workspace,
        path,
        old_text,
        new_text,
        expected_replacements,
    )


@mcp.tool()
def local_git_status(workspace: str) -> dict[str, Any]:
    """Run the fixed, read-only command git status --short for a trusted workspace."""
    return ops.git_status(workspace)


@mcp.tool()
def local_git_diff(workspace: str, path: str | None = None) -> dict[str, Any]:
    """Run the fixed, read-only git diff command for a trusted workspace."""
    return ops.git_diff(workspace, path)


def _request_host(scope: Scope) -> str:
    headers = {key.lower(): value for key, value in scope.get("headers", [])}
    raw_host = headers.get(b"host", b"").decode("ascii", errors="ignore").strip()
    if raw_host.startswith("["):
        closing = raw_host.find("]")
        if closing >= 0:
            return raw_host[: closing + 1].lower()
    return raw_host.split(":", 1)[0].lower()


class HostGuardMiddleware:
    """Keep the administration app local-only, even if routing is misconfigured."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and _request_host(scope) not in {
            "127.0.0.1",
            "localhost",
            "[::1]",
        }:
            response = JSONResponse({"error": "invalid_host"}, status_code=421)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


class MCPPathGuardMiddleware:
    """Expose only the MCP transport path on the MCP server."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path != "/mcp" and not path.startswith("/mcp/"):
                response = JSONResponse({"error": "not_found"}, status_code=404)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


class BearerAuthMiddleware:
    def __init__(self, app: ASGIApp, token_provider: Callable[[], str]) -> None:
        self.app = app
        self.token_provider = token_provider

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = {key.lower(): value for key, value in scope.get("headers", [])}
            supplied = headers.get(b"authorization", b"").decode("utf-8", errors="ignore")
            expected = f"Bearer {self.token_provider()}"
            if not hmac.compare_digest(supplied, expected):
                response = JSONResponse(
                    {"error": "unauthorized"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


async def setup_page(request: Request) -> Response:
    message = request.query_params.get("message", "")
    error = request.query_params.get("error", "")
    config = store.load()
    rows = "".join(
        f"<tr><td><code>{html.escape(item.name)}</code></td>"
        f"<td><code>{html.escape(item.path)}</code></td>"
        f"<td>{html.escape(item.permission)}</td>"
        f"<td><form method='post' action='/setup/workspaces/remove'>"
        f"<input type='hidden' name='name' value='{html.escape(item.name, quote=True)}'>"
        "<button type='submit'>Bỏ quyền</button></form></td></tr>"
        for item in config.workspaces
    ) or "<tr><td colspan='4'>Chưa có workspace.</td></tr>"
    notice = f"<p class='ok'>{html.escape(message)}</p>" if message else ""
    problem = f"<p class='error'>{html.escape(error)}</p>" if error else ""
    page = f"""<!doctype html>
<html lang='vi'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>
<title>AI_Actuator Setup</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:920px;margin:32px auto;padding:0 16px;color:#17202a}}
code,input,select{{font-family:ui-monospace,monospace}}table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #d5d8dc;padding:8px;text-align:left}}label{{display:block;margin:12px 0 4px}}
input[type=text]{{width:100%;box-sizing:border-box;padding:8px}}button,select{{padding:8px}}
.token{{overflow-wrap:anywhere;background:#f4f6f7;padding:12px}}.ok{{color:#196f3d}}.error{{color:#b03a2e}}
</style></head><body>
<h1>AI_Actuator <small>v{html.escape(__version__)}</small></h1>
<p>Admin: <code>http://{HOST}:{ADMIN_PORT}/setup</code></p>
<p>MCP: <code>http://{HOST}:{MCP_PORT}/mcp</code></p>
<p>Health: <code>http://{HOST}:{MCP_PORT}/health</code></p>
{notice}{problem}
<h2>Bearer token</h2><p class='token'><code>{html.escape(config.token)}</code></p>
<form method='post' action='/setup/token'><button type='submit'>Tạo token mới</button></form>
<h2>Trusted workspaces</h2>
<table><thead><tr><th>Tên</th><th>Đường dẫn</th><th>Quyền</th><th></th></tr></thead>
<tbody>{rows}</tbody></table>
<h3>Thêm hoặc cập nhật workspace</h3>
<form method='post' action='/setup/workspaces'>
<label for='name'>Tên ngắn</label><input id='name' name='name' type='text' required placeholder='StepperMotorLCD'>
<label for='path'>Đường dẫn tuyệt đối</label><input id='path' name='path' type='text' required placeholder='D:\\STM32\\StepperMotorLCD'>
<label for='permission'>Quyền</label><select id='permission' name='permission'>
<option value='read-only' selected>read-only</option><option value='workspace-write'>workspace-write</option>
</select> <button type='submit'>Lưu workspace</button></form>
<p><strong>Không cấp toàn bộ ổ C:\\ hoặc D:\\.</strong></p>
</body></html>"""
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})


async def add_workspace(request: Request) -> Response:
    form = await _read_form(request)
    try:
        name = validate_workspace_name(form.get("name", ""))
        root = validate_workspace_root(form.get("path", ""))
        permission = form.get("permission", "read-only")
        if permission not in {"read-only", "workspace-write"}:
            raise SecurityError("Invalid permission mode.")
        store.add_workspace(WorkspaceConfig(name, str(root), permission))
        return _setup_redirect(message=f"Đã lưu workspace {name}.")
    except (SecurityError, OSError) as exc:
        return _setup_redirect(error=str(exc))


async def remove_workspace(request: Request) -> Response:
    form = await _read_form(request)
    name = form.get("name", "")
    store.remove_workspace(name)
    return _setup_redirect(message=f"Đã bỏ quyền workspace {name}.")


async def regenerate_token(request: Request) -> Response:
    store.regenerate_token()
    return _setup_redirect(message="Đã tạo token mới; hãy cập nhật MCP client.")


async def health(_request: Request) -> Response:
    config = store.load()
    return JSONResponse(
        {
            "status": "ok",
            "name": "AI_Actuator",
            "version": __version__,
            "workspaces": len(config.workspaces),
        },
        headers={"Cache-Control": "no-store"},
    )


async def _read_form(request: Request) -> dict[str, str]:
    body = (await request.body()).decode("utf-8", errors="strict")
    parsed = parse_qs(body, keep_blank_values=True, max_num_fields=20)
    return {key: values[-1] for key, values in parsed.items()}


def _setup_redirect(*, message: str = "", error: str = "") -> RedirectResponse:
    from urllib.parse import urlencode

    query = urlencode({key: value for key, value in {"message": message, "error": error}.items() if value})
    return RedirectResponse(f"/setup?{query}", status_code=303)


sdk_mcp_app = mcp.streamable_http_app(json_response=True)
protected_mcp_app = MCPPathGuardMiddleware(
    BearerAuthMiddleware(sdk_mcp_app, lambda: store.load().token)
)


@contextlib.asynccontextmanager
async def mcp_lifespan(app: Starlette):
    store.load()
    async with mcp.session_manager.run():
        yield


_admin_starlette_app = Starlette(
    routes=[
        Route("/setup", setup_page, methods=["GET"]),
        Route("/setup/workspaces", add_workspace, methods=["POST"]),
        Route("/setup/workspaces/remove", remove_workspace, methods=["POST"]),
        Route("/setup/token", regenerate_token, methods=["POST"]),
    ]
)
admin_app = HostGuardMiddleware(_admin_starlette_app)

_mcp_starlette_app = Starlette(
    routes=[
        Route("/health", health, methods=["GET"]),
        Mount("/", app=protected_mcp_app),
    ],
    lifespan=mcp_lifespan,
)

# MCP Inspector runs in a browser on another localhost port. Allow only loopback
# browser origins while keeping arbitrary websites blocked by CORS.
mcp_app = CORSMiddleware(
    _mcp_starlette_app,
    allow_origin_regex=r"^https?://(?:127\.0\.0\.1|localhost|\[::1\])(?::\d+)?$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "Mcp-Session-Id",
        "Last-Event-ID",
    ],
    expose_headers=["Mcp-Session-Id"],
    max_age=600,
)

# Backward compatibility for code that imports ai_actuator.server:app.
# The public MCP transport is intentionally NOT served by this alias.
app = admin_app
