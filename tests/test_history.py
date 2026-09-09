from pathlib import Path

import pytest

from ai_actuator.history import AuditLog, BackupStore, sha256_bytes


def test_backup_integrity_and_scope(tmp_path: Path):
    state = tmp_path / "state"
    source = tmp_path / "x.txt"
    source.write_text("hello", encoding="utf-8")
    store = BackupStore(state)

    record = store.create(0, str(tmp_path), "x.txt", source)
    loaded, data = store.read_bytes(record.backup_id, 0, str(tmp_path), "x.txt")
    assert loaded.sha256 == record.sha256
    assert data == b"hello"

    with pytest.raises(ValueError):
        store.read_bytes(record.backup_id, 0, str(tmp_path), "other.txt")

    with pytest.raises(ValueError):
        store.read_bytes(record.backup_id, 0, str(tmp_path / "different-root"), "x.txt")


def test_create_bytes_backs_up_exact_checked_snapshot(tmp_path: Path):
    store = BackupStore(tmp_path / "state")
    snapshot = b"checked snapshot\n"
    record = store.create_bytes(0, str(tmp_path), "x.txt", snapshot)
    loaded, data = store.read_bytes(record.backup_id, 0, str(tmp_path), "x.txt")
    assert data == snapshot
    assert loaded.sha256 == sha256_bytes(snapshot)


def test_audit_log_newest_first(tmp_path: Path):
    audit = AuditLog(tmp_path / "state")
    audit.append("write_text", status="ok", path="a.txt")
    audit.append("edit_text", status="ok", path="a.txt")
    events = audit.read(10)
    assert [event["action"] for event in events] == ["edit_text", "write_text"]
