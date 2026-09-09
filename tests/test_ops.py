from __future__ import annotations

from pathlib import Path

import pytest

from ai_actuator.config import ConfigStore, WorkspaceConfig
from ai_actuator.ops import LocalOperations
from ai_actuator.security import SecurityError, SecurityPolicy


def make_ops(tmp_path: Path, permission: str = "workspace-write") -> tuple[LocalOperations, Path]:
    workspace = tmp_path / "project"
    workspace.mkdir()
    store = ConfigStore(tmp_path / "appdata")
    store.add_workspace(WorkspaceConfig("demo", str(workspace), permission))
    return LocalOperations(SecurityPolicy(store)), workspace


def test_write_read_search_and_exact_edit(tmp_path: Path) -> None:
    ops, workspace = make_ops(tmp_path)
    result = ops.write_text_file("demo", "src/main.c", "speed = 1000;\n")
    assert result["bytes_written"] == 14
    assert ops.read_text_file("demo", "src/main.c")["content"] == "speed = 1000;\n"
    matches = ops.search_text("demo", "speed")
    assert matches["matches"][0]["path"] == "src/main.c"
    edited = ops.edit_text_file("demo", "src/main.c", "1000", "2000", 1)
    assert edited["replacements"] == 1
    assert (workspace / "src" / "main.c").read_text(encoding="utf-8") == "speed = 2000;\n"


def test_exact_edit_fails_without_changing_file(tmp_path: Path) -> None:
    ops, workspace = make_ops(tmp_path)
    file_path = workspace / "values.txt"
    file_path.write_text("x x", encoding="utf-8")
    with pytest.raises(SecurityError, match="found 2"):
        ops.edit_text_file("demo", "values.txt", "x", "y", 1)
    assert file_path.read_text(encoding="utf-8") == "x x"


def test_read_only_ops_reject_write(tmp_path: Path) -> None:
    ops, _ = make_ops(tmp_path, "read-only")
    with pytest.raises(SecurityError, match="read-only"):
        ops.write_text_file("demo", "file.txt", "data")

