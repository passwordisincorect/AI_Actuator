from __future__ import annotations

import json
import os
import secrets
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_NAME = "AI_Actuator"


def _config_base() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def default_config_path() -> Path:
    return _config_base() / APP_NAME / "config.json"


@dataclass
class ActuatorConfig:
    roots: list[str] = field(default_factory=list)
    permission: str = "read-only"  # read-only | workspace-write
    bearer_token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    require_token: bool = True

    # Keep the administration dashboard and MCP transport on separate ports.
    # Both remain bound to loopback only.
    host: str = "127.0.0.1"
    admin_port: int = 8765
    mcp_port: int = 8766

    allowed_hosts: list[str] = field(default_factory=list)

    # Cloudflare Quick Tunnel integration. The path may be left empty for auto-discovery.
    cloudflared_path: str = ""
    tunnel_auto_start: bool = False

    @property
    def write_enabled(self) -> bool:
        return self.permission == "workspace-write"

    def normalized(self) -> "ActuatorConfig":
        roots: list[str] = []
        seen: set[str] = set()
        for raw in self.roots:
            if not raw.strip():
                continue
            p = str(Path(raw).expanduser().resolve())
            key = os.path.normcase(p)
            if key not in seen:
                seen.add(key)
                roots.append(p)
        self.roots = roots

        if self.permission not in {"read-only", "workspace-write"}:
            self.permission = "read-only"

        self.admin_port = int(self.admin_port)
        self.mcp_port = int(self.mcp_port)
        return self


def load_config(path: Path | None = None) -> ActuatorConfig:
    path = path or default_config_path()
    if not path.exists():
        cfg = ActuatorConfig()
        save_config(cfg, path)
        return cfg

    data = json.loads(path.read_text(encoding="utf-8"))

    # v0.1.2 used one shared `port`. Preserve an existing custom value for the
    # local admin dashboard, while the new MCP port defaults to 8766.
    if "port" in data and "admin_port" not in data:
        data["admin_port"] = data["port"]

    known = {f.name for f in ActuatorConfig.__dataclass_fields__.values()}
    cfg = ActuatorConfig(**{k: v for k, v in data.items() if k in known})
    return cfg.normalized()


def save_config(cfg: ActuatorConfig, path: Path | None = None) -> None:
    path = path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    cfg.normalized()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(cfg), indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
