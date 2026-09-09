from __future__ import annotations

import threading

import uvicorn

from .server import ADMIN_PORT, HOST, MCP_PORT, admin_app, mcp_app


def main() -> None:
    print(f"AI_Actuator Admin: http://{HOST}:{ADMIN_PORT}/setup")
    print(f"AI_Actuator MCP:   http://{HOST}:{MCP_PORT}/mcp")
    print(f"AI_Actuator Health:http://{HOST}:{MCP_PORT}/health")

    def run_mcp() -> None:
        uvicorn.run(mcp_app, host=HOST, port=MCP_PORT, log_level="info")

    mcp_thread = threading.Thread(
        target=run_mcp,
        name="AI_Actuator-MCP",
        daemon=True,
    )
    mcp_thread.start()

    # Keep the admin server on the main thread so Ctrl+C stops the application.
    uvicorn.run(admin_app, host=HOST, port=ADMIN_PORT, log_level="info")


if __name__ == "__main__":
    main()
