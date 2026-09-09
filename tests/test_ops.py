from pathlib import Path

from ai_actuator.config import ActuatorConfig
from ai_actuator.ops import WorkspaceOps


def make_ops(tmp_path: Path) -> WorkspaceOps:
    cfg = ActuatorConfig(roots=[str(tmp_path / "workspace")], permission="workspace-write")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return WorkspaceOps(cfg, state_dir=tmp_path / "state")


def test_exact_edit_creates_backup_and_rollback(tmp_path: Path):
    ops = make_ops(tmp_path)
    f = tmp_path / "workspace" / "main.c"
    f.write_text("speed = 1000;\n", encoding="utf-8")

    result = ops.edit_text(0, "main.c", "speed = 1000;", "speed = 2000;")
    assert result["replacements"] == 1
    assert result["backup_id"]
    assert "2000" in f.read_text(encoding="utf-8")

    backups = ops.list_backups(0, "main.c")
    assert backups[0]["backup_id"] == result["backup_id"]

    rolled = ops.rollback_text(0, "main.c", str(result["backup_id"]))
    assert rolled["restored_backup_id"] == result["backup_id"]
    assert rolled["safety_backup_id"]
    assert f.read_text(encoding="utf-8") == "speed = 1000;\n"


def test_overwrite_creates_backup(tmp_path: Path):
    ops = make_ops(tmp_path)
    f = tmp_path / "workspace" / "a.txt"
    f.write_text("old\n", encoding="utf-8")

    result = ops.write_text(0, "a.txt", "new\n", overwrite=True)
    assert result["overwritten"] is True
    assert result["backup_id"]
    assert f.read_text(encoding="utf-8") == "new\n"

    ops.rollback_text(0, "a.txt", str(result["backup_id"]))
    assert f.read_text(encoding="utf-8") == "old\n"


def test_new_write_is_audited_without_backup(tmp_path: Path):
    ops = make_ops(tmp_path)
    result = ops.write_text(0, "new.txt", "hello\n")
    assert result["backup_id"] is None

    events = ops.read_audit_log(10)
    assert events[0]["action"] == "write_text"
    assert events[0]["status"] == "ok"
    assert events[0]["path"] == "new.txt"
    assert "content" not in events[0]


def test_failed_edit_is_audited_and_does_not_change_file(tmp_path: Path):
    ops = make_ops(tmp_path)
    f = tmp_path / "workspace" / "a.txt"
    f.write_text("same\nsame\n", encoding="utf-8")

    try:
        ops.edit_text(0, "a.txt", "same", "changed", expected_replacements=1)
        assert False, "expected edit to fail"
    except ValueError:
        pass

    assert f.read_text(encoding="utf-8") == "same\nsame\n"
    events = ops.read_audit_log(10)
    assert events[0]["action"] == "edit_text"
    assert events[0]["status"] == "error"


def test_read_has_line_numbers(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    f = workspace / "a.txt"
    f.write_text("one\ntwo\nthree\n", encoding="utf-8")
    cfg = ActuatorConfig(roots=[str(workspace)])
    ops = WorkspaceOps(cfg, state_dir=tmp_path / "state")
    assert ops.read_text(0, "a.txt", 2, 3) == "2: two\n3: three"
