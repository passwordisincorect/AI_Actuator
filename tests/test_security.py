from __future__ import annotations

from pathlib import Path

import pytest

from ai_actuator.config import ConfigStore, WorkspaceConfig
from ai_actuator.security import SecurityError, SecurityPolicy, is_sensitive_path


def make_policy(tmp_path: Path, permission: str = "read-only") -> tuple[SecurityPolicy, Path]:
    workspace = tmp_path / "project"
    workspace.mkdir()
    store = ConfigStore(tmp_path / "appdata")
    store.add_workspace(WorkspaceConfig("demo", str(workspace), permission))
    return SecurityPolicy(store), workspace


def test_resolve_valid_relative_path(tmp_path: Path) -> None:
    policy, workspace = make_policy(tmp_path)
    file_path = workspace / "main.c"
    file_path.write_text("int main(void) {}", encoding="utf-8")
    _, resolved = policy.resolve("demo", "main.c")
    assert resolved == file_path


@pytest.mark.parametrize("value", ["../secret.txt", "C:\\secret.txt", "/etc/passwd"])
def test_rejects_traversal_and_absolute_paths(tmp_path: Path, value: str) -> None:
    policy, _ = make_policy(tmp_path)
    with pytest.raises(SecurityError):
        policy.resolve("demo", value, must_exist=False)


@pytest.mark.parametrize("value", [".env", ".ssh/id_ed25519", "certs/device.pem", ".git/config"])
def test_sensitive_paths_are_blocked(value: str) -> None:
    assert is_sensitive_path(Path(value))


def test_read_only_workspace_rejects_write(tmp_path: Path) -> None:
    policy, _ = make_policy(tmp_path, "read-only")
    with pytest.raises(SecurityError, match="read-only"):
        policy.resolve("demo", "new.txt", require_write=True, must_exist=False)


def test_symlink_is_blocked(tmp_path: Path) -> None:
    policy, workspace = make_policy(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = workspace / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symlinks are unavailable on this platform.")
    with pytest.raises(SecurityError):
        policy.resolve("demo", "link", must_exist=True)

