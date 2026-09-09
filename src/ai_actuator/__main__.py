from __future__ import annotations

import uvicorn

from .server import HOST, PORT, app


def main() -> None:
    print(f"AI_Actuator setup: http://{HOST}:{PORT}/setup")
    print(f"AI_Actuator MCP:   http://{HOST}:{PORT}/mcp")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()

