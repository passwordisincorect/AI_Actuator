from pathlib import Path

import pytest

from ai_actuator.config import ActuatorConfig
from ai_actuator.ops import FileChangedError, WorkspaceOps


def make_ops(tmp_path: Path) -> WorkspaceOps:
    cfg = ActuatorConfig(roots=[str(tmp_path / "workspace")], permission="workspace-write")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return WorkspaceOps(cfg, state_dir=tmp_path / "state")


def test_exact_edit_creates_backup_and_rollback(tmp_path: Path):
    ops = make_ops(tmp_path)
    f = tmp_path / "workspace" / "main.c"
    f.write_text("speed = 1000;\n", encoding="utf-8")

    read = ops.read_text(0, "main.c")
    result = ops.edit_text(
        0,
        "main.c",
        "speed = 1000;",
        "speed = 2000;",
        expected_sha256=str(read["sha256"]),
    )
    assert result["replacements"] == 1
    assert result["backup_id"]
    assert result["guarded"] is True
    assert result["before_sha256"] == read["sha256"]
    assert "2000" in f.read_text(encoding="utf-8")

    backups = ops.list_backups(0, "main.c")
    assert backups[0]["backup_id"] == result["backup_id"]

    rolled = ops.rollback_text(0, "main.c", str(result["backup_id"]))
    assert rolled["restored_backup_id"] == result["backup_id"]
    assert rolled["safety_backup_id"]
    assert f.read_text(encoding="utf-8") == "speed = 1000;\n"


def test_stale_edit_is_rejected_before_backup_or_write(tmp_path: Path):
    ops = make_ops(tmp_path)
    f = tmp_path / "workspace" / "main.c"
    f.write_text("speed = 1000;\n", encoding="utf-8")
    stale_sha = str(ops.read_text(0, "main.c")["sha256"])

    f.write_text("speed = 1500;\n", encoding="utf-8")

    with pytest.raises(FileChangedError) as caught:
        ops.edit_text(
            0,
            "main.c",
            "speed = 1000;",
            "speed = 2000;",
            expected_sha256=stale_sha,
        )

    assert caught.value.expected_sha256 == stale_sha
    assert caught.value.actual_sha256 != stale_sha
    assert f.read_text(encoding="utf-8") == "speed = 1500;\n"
    assert ops.list_backups(0, "main.c") == []

    event = ops.read_audit_log(10)[0]
    assert event["action"] == "edit_text"
    assert event["status"] == "conflict"
    assert event["error"] == "file_changed"
    assert event["expected_sha256"] == stale_sha
    assert event["actual_sha256"] == caught.value.actual_sha256


def test_overwrite_creates_backup_and_respects_expected_sha(tmp_path: Path):
    ops = make_ops(tmp_path)
    f = tmp_path / "workspace" / "a.txt"
    f.write_text("old\n", encoding="utf-8")
    read = ops.read_text(0, "a.txt")

    result = ops.write_text(
        0,
        "a.txt",
        "new\n",
        overwrite=True,
        expected_sha256=str(read["sha256"]),
    )
    assert result["overwritten"] is True
    assert result["backup_id"]
    assert result["guarded"] is True
    assert result["before_sha256"] == read["sha256"]
    assert f.read_text(encoding="utf-8") == "new\n"

    ops.rollback_text(0, "a.txt", str(result["backup_id"]))
    assert f.read_text(encoding="utf-8") == "old\n"


def test_stale_overwrite_is_rejected(tmp_path: Path):
    ops = make_ops(tmp_path)
    f = tmp_path / "workspace" / "a.txt"
    f.write_text("old\n", encoding="utf-8")
    stale_sha = str(ops.read_text(0, "a.txt")["sha256"])
    f.write_text("changed elsewhere\n", encoding="utf-8")

    with pytest.raises(FileChangedError):
        ops.write_text(
            0,
            "a.txt",
            "AI replacement\n",
            overwrite=True,
            expected_sha256=stale_sha,
        )

    assert f.read_text(encoding="utf-8") == "changed elsewhere\n"
    assert ops.list_backups(0, "a.txt") == []


def test_expected_sha_for_missing_file_is_conflict(tmp_path: Path):
    ops = make_ops(tmp_path)
    with pytest.raises(FileChangedError) as caught:
        ops.write_text(
            0,
            "missing.txt",
            "new\n",
            overwrite=True,
            expected_sha256="0" * 64,
        )
    assert caught.value.actual_sha256 is None
    assert not (tmp_path / "workspace" / "missing.txt").exists()


def test_invalid_expected_sha_is_rejected(tmp_path: Path):
    ops = make_ops(tmp_path)
    f = tmp_path / "workspace" / "a.txt"
    f.write_text("old\n", encoding="utf-8")
    with pytest.raises(ValueError):
        ops.edit_text(0, "a.txt", "old", "new", expected_sha256="not-a-hash")
    assert f.read_text(encoding="utf-8") == "old\n"


def test_new_write_is_audited_without_backup(tmp_path: Path):
    ops = make_ops(tmp_path)
    result = ops.write_text(0, "new.txt", "hello\n")
    assert result["backup_id"] is None
    assert result["guarded"] is False

    events = ops.read_audit_log(10)
    assert events[0]["action"] == "write_text"
    assert events[0]["status"] == "ok"
    assert events[0]["path"] == "new.txt"
    assert "content" not in events[0]


def test_failed_edit_is_audited_and_does_not_change_file(tmp_path: Path):
    ops = make_ops(tmp_path)
    f = tmp_path / "workspace" / "a.txt"
    f.write_text("same\nsame\n", encoding="utf-8")

    with pytest.raises(ValueError):
        ops.edit_text(0, "a.txt", "same", "changed", expected_replacements=1)

    assert f.read_text(encoding="utf-8") == "same\nsame\n"
    events = ops.read_audit_log(10)
    assert events[0]["action"] == "edit_text"
    assert events[0]["status"] == "error"


def test_read_returns_numbered_content_and_full_file_sha(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    f = workspace / "a.txt"
    f.write_text("one\ntwo\nthree\n", encoding="utf-8")
    cfg = ActuatorConfig(roots=[str(workspace)])
    ops = WorkspaceOps(cfg, state_dir=tmp_path / "state")

    result = ops.read_text(0, "a.txt", 2, 3)
    assert result["content"] == "2: two\n3: three"
    assert result["bytes"] == len(b"one\ntwo\nthree\n")
    assert result["start_line"] == 2
    assert result["end_line"] == 3
    assert result["total_lines"] == 3
    assert len(str(result["sha256"])) == 64
