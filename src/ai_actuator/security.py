from __future__ import annotations

import os
import re
import stat
from pathlib import Path, PureWindowsPath

from .config import ConfigStore, WorkspaceConfig

MAX_FILE_BYTES = 1024 * 1024

_BLOCKED_PARTS = {
    ".git",
    ".ssh",
    ".gnupg",
    ".aws",
    ".azure",
    ".kube",
    "credentials",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
}
_BLOCKED_SUFFIXES = {".pem", ".key", ".pfx", ".p12"}
_SAFE_WORKSPACE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class SecurityError(ValueError):
    pass


def validate_workspace_name(name: str) -> str:
    if not _SAFE_WORKSPACE_NAME.fullmatch(name):
        raise SecurityError(
            "Workspace name must use 1-64 letters, numbers, dot, underscore, or hyphen."
        )
    return name


def validate_workspace_root(path_text: str) -> Path:
    root = Path(path_text).expanduser()
    if not root.is_absolute():
        raise SecurityError("Workspace root must be an absolute path.")
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise SecurityError("Workspace root must be an existing directory.")
    if root.parent == root:
        raise SecurityError("A filesystem or drive root cannot be trusted as a workspace.")
    _reject_reparse_components(root)
    return root


def is_sensitive_path(path: Path) -> bool:
    for part in path.parts:
        lowered = part.casefold()
        if lowered in _BLOCKED_PARTS or lowered == ".env" or lowered.startswith(".env."):
            return True
        if Path(lowered).suffix in _BLOCKED_SUFFIXES:
            return True
    return False


class SecurityPolicy:
    def __init__(self, store: ConfigStore) -> None:
        self.store = store

    def workspace(self, name: str, *, require_write: bool = False) -> WorkspaceConfig:
        validate_workspace_name(name)
        match = next((item for item in self.store.load().workspaces if item.name == name), None)
        if match is None:
            raise SecurityError(f"Unknown workspace: {name}")
        if require_write and match.permission != "workspace-write":
            raise SecurityError(f"Workspace '{name}' is read-only.")
        validate_workspace_root(match.path)
        return match

    def resolve(
        self,
        workspace_name: str,
        relative_path: str = ".",
        *,
        require_write: bool = False,
        must_exist: bool = True,
    ) -> tuple[WorkspaceConfig, Path]:
        workspace = self.workspace(workspace_name, require_write=require_write)
        root = Path(workspace.path).resolve(strict=True)
        _validate_relative_path(relative_path)
        candidate = root / Path(relative_path)
        resolved = candidate.resolve(strict=must_exist)
        try:
            if os.path.commonpath([str(root), str(resolved)]) != str(root):
                raise SecurityError("Path escapes the trusted workspace.")
        except ValueError as exc:
            raise SecurityError("Path is on a different filesystem root.") from exc
        relative = resolved.relative_to(root)
        if is_sensitive_path(relative):
            raise SecurityError("Access to sensitive paths is blocked.")
        _reject_reparse_components(root)
        _reject_reparse_components(resolved, stop_at=root)
        return workspace, resolved


def _validate_relative_path(value: str) -> None:
    if "\x00" in value:
        raise SecurityError("NUL bytes are not allowed in paths.")
    native = Path(value)
    windows = PureWindowsPath(value)
    if native.is_absolute() or windows.is_absolute() or windows.drive:
        raise SecurityError("Tool paths must be relative to the workspace.")
    if any(part == ".." for part in native.parts) or any(part == ".." for part in windows.parts):
        raise SecurityError("Parent traversal is not allowed.")


def _reject_reparse_components(path: Path, stop_at: Path | None = None) -> None:
    current = path
    items: list[Path] = []
    while True:
        items.append(current)
        if stop_at is not None and current == stop_at:
            break
        if current.parent == current:
            break
        current = current.parent
    for item in reversed(items):
        if not item.exists():
            continue
        info = item.lstat()
        attributes = getattr(info, "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if stat.S_ISLNK(info.st_mode) or bool(attributes & reparse_flag):
            raise SecurityError(f"Symlink or reparse point is blocked: {item}")

