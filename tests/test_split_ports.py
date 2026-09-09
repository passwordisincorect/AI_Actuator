from __future__ import annotations

from starlette.testclient import TestClient

from ai_actuator import __version__
from ai_actuator.server import ADMIN_PORT, MCP_PORT, admin_app, mcp_app


def test_v020_version_and_ports() -> None:
    assert __version__ == "0.2.0"
    assert ADMIN_PORT == 8765
    assert MCP_PORT == 8766


def test_admin_port_exposes_setup_but_not_mcp() -> None:
    client = TestClient(admin_app, base_url="http://127.0.0.1:8765")
    assert client.get("/setup").status_code == 200
    assert client.get("/mcp").status_code == 404


def test_mcp_port_hides_setup_and_requires_bearer() -> None:
    client = TestClient(mcp_app, base_url="http://127.0.0.1:8766")
    assert client.get("/setup").status_code == 404
    assert client.get("/mcp").status_code == 401


def test_health_is_public_on_mcp_port() -> None:
    client = TestClient(mcp_app, base_url="http://127.0.0.1:8766")
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["name"] == "AI_Actuator"
    assert payload["version"] == "0.2.0"
