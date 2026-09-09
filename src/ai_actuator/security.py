from __future__ import annotations

import os
import stat
from pathlib import Path


class ActuatorSecurityError(ValueError):
    pass


SENSITIVE_EXACT = {
    ".env",
    ".ssh",
    ".aws",
    ".gnupg",
    "credentials",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
}
SENSITIVE_SUFFIXES = {".pem", ".p12", ".pfx", ".key"}


def _is_reparse_point(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        if hasattr(path, "is_junction") and path.is_junction():  # Python 3.12+
            return True
        attrs = getattr(path.lstat(), "st_file_attributes", 0)
        flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        return bool(flag and attrs & flag)
    except FileNotFoundError:
        return False


def _check_sensitive(relative: Path) -> None:
    for part in relative.parts:
        low = part.lower()
        if low in SENSITIVE_EXACT:
            raise ActuatorSecurityError(f"Sensitive path is blocked: {part}")
        if any(low.endswith(suffix) for suffix in SENSITIVE_SUFFIXES):
            raise ActuatorSecurityError(f"Sensitive key/certificate file is blocked: {part}")


def resolve_in_root(root: Path, user_path: str, *, allow_missing: bool = False) -> Path:
    root = root.expanduser().resolve()
    raw = Path(user_path or ".")
    if raw.is_absolute():
        raise ActuatorSecurityError("Absolute paths are not allowed; use a path relative to the trusted root.")
    if any(part == ".." for part in raw.parts):
        raise ActuatorSecurityError("Path traversal ('..') is not allowed.")

    _check_sensitive(raw)
    candidate = (root / raw).resolve(strict=False)

    root_key = os.path.normcase(str(root))
    candidate_key = os.path.normcase(str(candidate))
    try:
        if os.path.commonpath([root_key, candidate_key]) != root_key:
            raise ActuatorSecurityError("Path escapes the trusted root.")
    except ValueError as exc:
        raise ActuatorSecurityError("Path is on a different drive than the trusted root.") from exc

    # Reject symlinks/junctions/reparse points anywhere in the existing path chain.
    current = root
    if _is_reparse_point(current):
        raise ActuatorSecurityError("Trusted root cannot be a symlink/junction/reparse point.")
    for part in raw.parts:
        if part in {"", "."}:
            continue
        current = current / part
        if current.exists() and _is_reparse_point(current):
            raise ActuatorSecurityError(f"Symlink/junction/reparse point is blocked: {part}")

    if not allow_missing and not candidate.exists():
        raise ActuatorSecurityError(f"Path does not exist: {user_path}")
    return candidate
