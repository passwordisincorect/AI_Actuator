from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

from .config import ActuatorConfig, default_config_path
from .history import AuditLog, BackupStore
from .security import ActuatorSecurityError, resolve_in_root

MAX_READ_BYTES = 1_000_000
MAX_WRITE_BYTES = 1_000_000
MAX_LIST_ENTRIES = 300
MAX_SEARCH_RESULTS = 100
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "build", "dist", "__pycache__"}


class WorkspaceOps:
    def __init__(self, config: ActuatorConfig, state_dir: Path | None = None):
        self.config = config
        self.state_dir = Path(state_dir) if state_dir is not None else default_config_path().parent
        self.backups = BackupStore(self.state_dir)
        self.audit = AuditLog(self.state_dir)

    def roots(self) -> list[Path]:
        return [Path(p) for p in self.config.roots]

    def root(self, root_id: int) -> Path:
        roots = self.roots()
        if not roots:
            raise ActuatorSecurityError("No trusted workspace configured. Open /setup first.")
        if root_id < 0 or root_id >= len(roots):
            raise ActuatorSecurityError(f"Invalid root_id={root_id}; valid range is 0..{len(roots)-1}.")
        root = roots[root_id]
        if not root.exists() or not root.is_dir():
            raise ActuatorSecurityError(f"Trusted root is missing or not a directory: {root}")
        return root

    def resolve(self, root_id: int, path: str, *, allow_missing: bool = False) -> Path:
        return resolve_in_root(self.root(root_id), path, allow_missing=allow_missing)

    def _relative(self, root_id: int, target: Path) -> str:
        return str(target.relative_to(self.root(root_id)))

    @staticmethod
    def _sha256_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def _audit_event(self, action: str, *, status: str, **fields: object) -> None:
        try:
            self.audit.append(action, status=status, **fields)
        except OSError:
            pass

    def list_roots(self) -> list[dict[str, object]]:
        return [
            {"root_id": i, "path": str(p), "exists": p.exists(), "permission": self.config.permission}
            for i, p in enumerate(self.roots())
        ]

    def list_directory(self, root_id: int, path: str = "") -> list[dict[str, object]]:
        target = self.resolve(root_id, path or ".")
        if not target.is_dir():
            raise ActuatorSecurityError("Target is not a directory.")
        rows: list[dict[str, object]] = []
        for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:MAX_LIST_ENTRIES]:
            if child.name in SKIP_DIRS:
                continue
            rows.append(
                {
                    "name": child.name,
                    "type": "directory" if child.is_dir() else "file",
                    "size": child.stat().st_size if child.is_file() else None,
                }
            )
        return rows

    def read_text(self, root_id: int, path: str, start_line: int = 1, end_line: int = 400) -> str:
        target = self.resolve(root_id, path)
        if not target.is_file():
            raise ActuatorSecurityError("Target is not a file.")
        if target.stat().st_size > MAX_READ_BYTES:
            raise ActuatorSecurityError(f"File is too large (> {MAX_READ_BYTES} bytes).")
        data = target.read_bytes()
        if b"\x00" in data[:8192]:
            raise ActuatorSecurityError("Binary files are not supported.")
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        start = max(1, int(start_line))
        end = max(start, min(int(end_line), start + 999))
        selected = lines[start - 1 : end]
        return "\n".join(f"{i}: {line}" for i, line in enumerate(selected, start=start))

    def search_text(self, root_id: int, query: str, path: str = "", max_results: int = 50) -> list[dict[str, object]]:
        if not query:
            raise ActuatorSecurityError("query must not be empty.")
        base = self.resolve(root_id, path or ".")
        limit = max(1, min(int(max_results), MAX_SEARCH_RESULTS))
        results: list[dict[str, object]] = []
        files = [base] if base.is_file() else base.rglob("*")
        root = self.root(root_id)
        for file in files:
            if len(results) >= limit:
                break
            if not file.is_file() or any(part in SKIP_DIRS for part in file.parts):
                continue
            try:
                rel = file.relative_to(root)
                safe_file = resolve_in_root(root, str(rel))
                if safe_file.stat().st_size > MAX_READ_BYTES:
                    continue
                data = safe_file.read_bytes()
                if b"\x00" in data[:8192]:
                    continue
                text = data.decode("utf-8", errors="replace")
            except (OSError, UnicodeError, ActuatorSecurityError):
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                if query.lower() in line.lower():
                    results.append({"path": str(rel), "line": line_no, "text": line[:500]})
                    if len(results) >= limit:
                        break
        return results

    def _require_write(self) -> None:
        if not self.config.write_enabled:
            raise ActuatorSecurityError("Write permission is disabled. Set permission=workspace-write in /setup.")

    def write_text(self, root_id: int, path: str, content: str, overwrite: bool = False) -> dict[str, object]:
        action = "write_text"
        try:
            self._require_write()
            encoded = content.encode("utf-8")
            if len(encoded) > MAX_WRITE_BYTES:
                raise ActuatorSecurityError(f"Content is too large (> {MAX_WRITE_BYTES} bytes).")
            target = self.resolve(root_id, path, allow_missing=True)
            relative = self._relative(root_id, target)
            existed_before = target.exists()
            if existed_before and not overwrite:
                raise ActuatorSecurityError("File already exists. Set overwrite=true to replace it.")
            if existed_before and not target.is_file():
                raise ActuatorSecurityError("Target exists and is not a file.")

            backup = None
            before_sha = None
            if existed_before:
                before_sha = self._sha256_file(target)
                try:
                    backup = self.backups.create(root_id, str(self.root(root_id)), relative, target)
                except ValueError as exc:
                    raise ActuatorSecurityError(str(exc)) from exc

            target.parent.mkdir(parents=True, exist_ok=True)
            self.resolve(root_id, str(target.parent.relative_to(self.root(root_id))))
            self._atomic_write(target, content)
            after_sha = self._sha256_file(target)
            result = {
                "path": path,
                "bytes": len(encoded),
                "overwritten": existed_before,
                "backup_id": backup.backup_id if backup else None,
                "sha256": after_sha,
            }
            self._audit_event(
                action,
                status="ok",
                root_id=root_id,
                root_path=str(self.root(root_id)),
                path=relative,
                overwritten=existed_before,
                bytes=len(encoded),
                backup_id=backup.backup_id if backup else None,
                before_sha256=before_sha,
                after_sha256=after_sha,
            )
            return result
        except Exception as exc:
            self._audit_event(action, status="error", root_id=root_id, path=path, error=str(exc))
            raise

    def edit_text(self, root_id: int, path: str, old_text: str, new_text: str, expected_replacements: int = 1) -> dict[str, object]:
        action = "edit_text"
        try:
            self._require_write()
            if not old_text:
                raise ActuatorSecurityError("old_text must not be empty.")
            target = self.resolve(root_id, path)
            relative = self._relative(root_id, target)
            if not target.is_file():
                raise ActuatorSecurityError("Target is not a file.")
            if target.stat().st_size > MAX_READ_BYTES:
                raise ActuatorSecurityError("File is too large to edit safely.")
            text = target.read_text(encoding="utf-8", errors="strict")
            count = text.count(old_text)
            expected = int(expected_replacements)
            if count != expected:
                raise ActuatorSecurityError(f"Expected {expected} exact match(es), found {count}; no changes made.")
            updated = text.replace(old_text, new_text)
            if len(updated.encode("utf-8")) > MAX_WRITE_BYTES:
                raise ActuatorSecurityError("Edited file would exceed the write-size limit.")

            before_sha = self._sha256_file(target)
            try:
                backup = self.backups.create(root_id, str(self.root(root_id)), relative, target)
            except ValueError as exc:
                raise ActuatorSecurityError(str(exc)) from exc
            self._atomic_write(target, updated)
            after_sha = self._sha256_file(target)
            result = {
                "path": path,
                "replacements": count,
                "backup_id": backup.backup_id,
                "sha256": after_sha,
            }
            self._audit_event(
                action,
                status="ok",
                root_id=root_id,
                root_path=str(self.root(root_id)),
                path=relative,
                replacements=count,
                backup_id=backup.backup_id,
                before_sha256=before_sha,
                after_sha256=after_sha,
            )
            return result
        except Exception as exc:
            self._audit_event(action, status="error", root_id=root_id, path=path, error=str(exc))
            raise

    def list_backups(self, root_id: int, path: str = "", limit: int = 20) -> list[dict[str, object]]:
        self.root(root_id)
        relative: str | None = None
        if path.strip():
            target = self.resolve(root_id, path, allow_missing=True)
            relative = self._relative(root_id, target)
        return [
            record.to_dict()
            for record in self.backups.list(root_id, str(self.root(root_id)), relative, limit)
        ]

    def rollback_text(self, root_id: int, path: str, backup_id: str) -> dict[str, object]:
        action = "rollback_text"
        try:
            self._require_write()
            target = self.resolve(root_id, path, allow_missing=True)
            relative = self._relative(root_id, target)
            try:
                record, data = self.backups.read_bytes(
                    backup_id, root_id, str(self.root(root_id)), relative
                )
            except ValueError as exc:
                raise ActuatorSecurityError(str(exc)) from exc
            if b"\x00" in data[:8192]:
                raise ActuatorSecurityError("Binary backups cannot be restored through the text rollback tool.")
            try:
                data.decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                raise ActuatorSecurityError("Backup is not valid UTF-8 text.") from exc

            current_backup = None
            before_sha = None
            if target.exists():
                if not target.is_file():
                    raise ActuatorSecurityError("Target exists and is not a file.")
                before_sha = self._sha256_file(target)
                try:
                    current_backup = self.backups.create(root_id, str(self.root(root_id)), relative, target)
                except ValueError as exc:
                    raise ActuatorSecurityError(str(exc)) from exc
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                self.resolve(root_id, str(target.parent.relative_to(self.root(root_id))))

            self._atomic_write_bytes(target, data)
            after_sha = self._sha256_file(target)
            result = {
                "path": path,
                "restored_backup_id": record.backup_id,
                "safety_backup_id": current_backup.backup_id if current_backup else None,
                "bytes": len(data),
                "sha256": after_sha,
            }
            self._audit_event(
                action,
                status="ok",
                root_id=root_id,
                root_path=str(self.root(root_id)),
                path=relative,
                restored_backup_id=record.backup_id,
                safety_backup_id=current_backup.backup_id if current_backup else None,
                bytes=len(data),
                before_sha256=before_sha,
                after_sha256=after_sha,
            )
            return result
        except Exception as exc:
            self._audit_event(
                action,
                status="error",
                root_id=root_id,
                path=path,
                backup_id=backup_id,
                error=str(exc),
            )
            raise

    def read_audit_log(self, limit: int = 50) -> list[dict[str, object]]:
        return self.audit.read(limit)

    @staticmethod
    def _atomic_write(target: Path, content: str) -> None:
        fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, target)
        finally:
            try:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)
            except OSError:
                pass

    @staticmethod
    def _atomic_write_bytes(target: Path, content: bytes) -> None:
        fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, target)
        finally:
            try:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)
            except OSError:
                pass

    def _git(self, root_id: int, path: str, args: list[str]) -> str:
        cwd = self.resolve(root_id, path or ".")
        if cwd.is_file():
            cwd = cwd.parent
        try:
            cp = subprocess.run(
                ["git", *args],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=10,
                shell=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except FileNotFoundError as exc:
            raise ActuatorSecurityError("Git is not installed or not on PATH.") from exc
        except subprocess.TimeoutExpired as exc:
            raise ActuatorSecurityError("Git command timed out.") from exc
        if cp.returncode != 0:
            raise ActuatorSecurityError((cp.stderr or cp.stdout or "Git command failed.").strip())
        return cp.stdout.strip()

    def git_status(self, root_id: int, path: str = "") -> str:
        return self._git(root_id, path, ["status", "--short", "--branch"])

    def git_diff(self, root_id: int, path: str = "") -> str:
        out = self._git(root_id, path, ["diff", "--", "."])
        return out[:200_000]
