from pathlib import Path
import pytest

from ai_actuator.security import ActuatorSecurityError, resolve_in_root


def test_allows_normal_relative_path(tmp_path: Path):
    p = tmp_path / "src"
    p.mkdir()
    f = p / "main.c"
    f.write_text("int main(void) {}", encoding="utf-8")
    assert resolve_in_root(tmp_path, "src/main.c") == f.resolve()


def test_blocks_parent_traversal(tmp_path: Path):
    with pytest.raises(ActuatorSecurityError):
        resolve_in_root(tmp_path, "../secret.txt", allow_missing=True)


def test_blocks_absolute_path(tmp_path: Path):
    with pytest.raises(ActuatorSecurityError):
        resolve_in_root(tmp_path, str((tmp_path / "x").resolve()), allow_missing=True)


def test_blocks_sensitive_env(tmp_path: Path):
    f = tmp_path / ".env"
    f.write_text("SECRET=x", encoding="utf-8")
    with pytest.raises(ActuatorSecurityError):
        resolve_in_root(tmp_path, ".env")
