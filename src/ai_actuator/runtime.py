from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from mcp.server.transport_security import TransportSecuritySettings

from .config import ActuatorConfig, default_config_path, load_config
from .tunnel import QuickTunnelManager, TunnelStatus

_LOCAL_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
_LOCAL_ORIGINS = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


@dataclass
class RuntimeState:
    config_path: Path
    cfg: ActuatorConfig
    transport_security: TransportSecuritySettings
    tunnel: QuickTunnelManager

    def __post_init__(self) -> None:
        self._lock = threading.RLock()
        self._runtime_tunnel_hosts: set[str] = set()

    def _set_runtime_tunnel_host(self, hostname: str | None) -> None:
        with self._lock:
            # Remove only hosts that were dynamically added by this runtime.
            if self._runtime_tunnel_hosts:
                current = [
                    value
                    for value in self.transport_security.allowed_hosts
                    if value not in self._runtime_tunnel_hosts
                ]
                self.transport_security.allowed_hosts[:] = current
                self._runtime_tunnel_hosts.clear()

            if hostname:
                dynamic = {hostname, f"{hostname}:*"}
                self.transport_security.allowed_hosts.extend(
                    value
                    for value in dynamic
                    if value not in self.transport_security.allowed_hosts
                )
                self._runtime_tunnel_hosts.update(dynamic)

    def start_quick_tunnel(self) -> TunnelStatus:
        status = self.tunnel.start()
        self._set_runtime_tunnel_host(self.tunnel.hostname)
        return status

    def stop_quick_tunnel(self) -> TunnelStatus:
        status = self.tunnel.stop()
        self._set_runtime_tunnel_host(None)
        return status


def create_runtime(config_path: Path | None = None) -> RuntimeState:
    path = config_path or default_config_path()
    cfg = load_config(path)
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_dedupe(_LOCAL_HOSTS + cfg.allowed_hosts),
        allowed_origins=_dedupe(_LOCAL_ORIGINS),
    )
    tunnel = QuickTunnelManager(
        origin_url=f"http://{cfg.host}:{cfg.mcp_port}",
        configured_cloudflared_path=cfg.cloudflared_path,
    )
    return RuntimeState(
        config_path=path,
        cfg=cfg,
        transport_security=security,
        tunnel=tunnel,
    )
