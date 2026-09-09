from __future__ import annotations

import argparse
import threading
from pathlib import Path

import uvicorn

from .config import default_config_path
from .runtime import create_runtime
from .server import build_admin_app, build_mcp_app
from .tunnel import TunnelError


def main() -> None:
    parser = argparse.ArgumentParser(description="AI_Actuator - safe local MCP file actuator")
    parser.add_argument("--config", type=Path, default=default_config_path(), help="Path to config.json")
    parser.add_argument("--show-config", action="store_true", help="Print config path and exit")
    args = parser.parse_args()

    if args.show_config:
        print(args.config)
        return

    runtime = create_runtime(args.config)
    cfg = runtime.cfg
    admin_app, _ = build_admin_app(runtime)
    mcp_app, _ = build_mcp_app(runtime)

    print(f"AI_Actuator Admin: http://{cfg.host}:{cfg.admin_port}/setup")
    print(f"MCP endpoint:      http://{cfg.host}:{cfg.mcp_port}/mcp")
    print(f"Health endpoint:   http://{cfg.host}:{cfg.mcp_port}/health")
    print("Default mode is read-only. Configure trusted roots in /setup.")

    def run_mcp() -> None:
        uvicorn.run(
            mcp_app,
            host=cfg.host,
            port=cfg.mcp_port,
            log_level="info",
        )

    mcp_thread = threading.Thread(
        target=run_mcp,
        name="AI_Actuator-MCP",
        daemon=True,
    )
    mcp_thread.start()

    if cfg.tunnel_auto_start:
        try:
            status = runtime.start_quick_tunnel()
            if status.public_mcp_url:
                print(f"Quick Tunnel:      {status.public_mcp_url}")
        except TunnelError as exc:
            print(f"Quick Tunnel error: {exc}")

    try:
        uvicorn.run(
            admin_app,
            host=cfg.host,
            port=cfg.admin_port,
            log_level="info",
        )
    finally:
        runtime.stop_quick_tunnel()


if __name__ == "__main__":
    main()
