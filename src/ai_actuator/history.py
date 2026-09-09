from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_BACKUP_BYTES = 1_000_000
MAX_BACKUPS_PER_FILE = 20
MAX_AUDIT_BYTES = 5_000_000


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class BackupRecord:
    backup_id: str
    created_at: str
    root_id: int
    root_path: str
    relative_path: str
    bytes: int
    sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "backup_id": self.backup_id,
            "created_at": self.created_at,
            "root_id": self.root_id,
            "root_path": self.root_path,
            "path": self.relative_path,
            "bytes": self.bytes,
            "sha256": self.sha256,
        }


class BackupStore:
    """Stores opaque file snapshots outside trusted workspaces.

    Backup contents and metadata live next to config.json under the AI_Actuator state
    directory. Filenames are generated identifiers, never user-supplied paths.
    """

    def __init__(self, state_dir: Path) -> None:
        self.directory = Path(state_dir) / "backups"
        self._lock = threading.RLock()

    def create(self, root_id: int, root_path: str, relative_path: str, source: Path) -> BackupRecord:
        return self.create_bytes(root_id, root_path, relative_path, source.read_bytes())

    def create_bytes(
        self, root_id: int, root_path: str, relative_path: str, data: bytes
    ) -> BackupRecord:
        """Persist an already-read snapshot without re-reading the live file.

        v0.2.2 uses this so the SHA-256 checked for optimistic concurrency is
        exactly the same byte snapshot that is stored as the safety backup.
        """
        with self._lock:
            if len(data) > MAX_BACKUP_BYTES:
                raise ValueError(
                    f"Existing file is too large to back up safely (> {MAX_BACKUP_BYTES} bytes)."
                )

            self.directory.mkdir(parents=True, exist_ok=True)
            created_at = utc_now_iso()
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup_id = f"{stamp}-{uuid.uuid4().hex[:10]}"
            content_path = self.directory / f"{backup_id}.bak"
            metadata_path = self.directory / f"{backup_id}.json"

            record = BackupRecord(
                backup_id=backup_id,
                created_at=created_at,
                root_id=int(root_id),
                root_path=str(root_path),
                relative_path=str(relative_path),
                bytes=len(data),
                sha256=sha256_bytes(data),
            )

            self._atomic_write_bytes(content_path, data)
            self._atomic_write_text(
                metadata_path,
                json.dumps(record.to_dict(), ensure_ascii=False, indent=2) + "\n",
            )
            self._prune(root_id, root_path, relative_path)
            return record

    def list(
        self,
        root_id: int,
        root_path: str,
        relative_path: str | None = None,
        limit: int = 20,
    ) -> list[BackupRecord]:
        with self._lock:
            if not self.directory.exists():
                return []
            records: list[BackupRecord] = []
            for metadata_path in self.directory.glob("*.json"):
                record = self._read_record(metadata_path)
                if (
                    record is None
                    or record.root_id != int(root_id)
                    or record.root_path != str(root_path)
                ):
                    continue
                if relative_path is not None and record.relative_path != str(relative_path):
                    continue
                records.append(record)
            records.sort(key=lambda item: item.backup_id, reverse=True)
            return records[: max(1, min(int(limit), 100))]

    def read_bytes(
        self, backup_id: str, root_id: int, root_path: str, relative_path: str
    ) -> tuple[BackupRecord, bytes]:
        with self._lock:
            self._validate_backup_id(backup_id)
            metadata_path = self.directory / f"{backup_id}.json"
            content_path = self.directory / f"{backup_id}.bak"
            record = self._read_record(metadata_path)
            if record is None or not content_path.is_file():
                raise ValueError("Backup not found.")
            if (
                record.root_id != int(root_id)
                or record.root_path != str(root_path)
                or record.relative_path != str(relative_path)
            ):
                raise ValueError("Backup does not belong to the requested trusted root/path.")
            data = content_path.read_bytes()
            if len(data) != record.bytes or sha256_bytes(data) != record.sha256:
                raise ValueError("Backup integrity check failed.")
            return record, data

    def _prune(self, root_id: int, root_path: str, relative_path: str) -> None:
        records = self.list(root_id, root_path, relative_path, limit=100)
        for record in records[MAX_BACKUPS_PER_FILE:]:
            for suffix in (".bak", ".json"):
                try:
                    (self.directory / f"{record.backup_id}{suffix}").unlink(missing_ok=True)
                except OSError:
                    pass

    @staticmethod
    def _validate_backup_id(backup_id: str) -> None:
        if not backup_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in backup_id):
            raise ValueError("Invalid backup_id.")

    @staticmethod
    def _read_record(metadata_path: Path) -> BackupRecord | None:
        try:
            raw = json.loads(metadata_path.read_text(encoding="utf-8"))
            return BackupRecord(
                backup_id=str(raw["backup_id"]),
                created_at=str(raw["created_at"]),
                root_id=int(raw["root_id"]),
                root_path=str(raw.get("root_path", "")),
                relative_path=str(raw.get("path", raw.get("relative_path", ""))),
                bytes=int(raw["bytes"]),
                sha256=str(raw["sha256"]),
            )
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None

    @staticmethod
    def _atomic_write_bytes(target: Path, data: bytes) -> None:
        tmp = target.with_suffix(target.suffix + ".tmp")
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)

    @staticmethod
    def _atomic_write_text(target: Path, text: str) -> None:
        tmp = target.with_suffix(target.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)


class AuditLog:
    """Append-only JSONL audit trail. File contents are never logged."""

    def __init__(self, state_dir: Path) -> None:
        self.path = Path(state_dir) / "audit.jsonl"
        self.rotated_path = Path(state_dir) / "audit.1.jsonl"
        self._lock = threading.RLock()

    def append(self, action: str, *, status: str, **fields: Any) -> dict[str, object]:
        event: dict[str, object] = {
            "timestamp": utc_now_iso(),
            "action": action,
            "status": status,
        }
        for key, value in fields.items():
            if value is not None:
                event[key] = value

        line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._rotate_if_needed(len(line.encode("utf-8")))
            with open(self.path, "a", encoding="utf-8", newline="") as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())
        return event

    def read(self, limit: int = 50) -> list[dict[str, object]]:
        with self._lock:
            if not self.path.is_file():
                return []
            lines = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
        events: list[dict[str, object]] = []
        for line in reversed(lines[-max(1, min(int(limit), 500)) :]):
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    events.append(value)
            except json.JSONDecodeError:
                continue
        return events

    def _rotate_if_needed(self, incoming_bytes: int) -> None:
        try:
            current = self.path.stat().st_size if self.path.exists() else 0
        except OSError:
            current = 0
        if current + incoming_bytes <= MAX_AUDIT_BYTES:
            return
        try:
            self.rotated_path.unlink(missing_ok=True)
            if self.path.exists():
                os.replace(self.path, self.rotated_path)
        except OSError:
            pass
