from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from .security import MAX_FILE_BYTES, SecurityError, SecurityPolicy, is_sensitive_path

MAX_DIRECTORY_ENTRIES = 500
MAX_SEARCH_MATCHES = 200


class LocalOperations:
    def __init__(self, policy: SecurityPolicy) -> None:
        self.policy = policy

    def list_roots(self) -> dict[str, Any]:
        roots = [
            {"name": item.name, "path": item.path, "permission": item.permission}
            for item in self.policy.store.load().workspaces
        ]
        return {"roots": roots}

    def list_directory(self, workspace: str, path: str = ".") -> dict[str, Any]:
        _, directory = self.policy.resolve(workspace, path)
        if not directory.is_dir():
            raise SecurityError("Path is not a directory.")
        entries: list[dict[str, Any]] = []
        for child in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
            if len(entries) >= MAX_DIRECTORY_ENTRIES:
                break
            if is_sensitive_path(Path(child.name)) or child.is_symlink():
                continue
            entries.append(
                {
                    "name": child.name,
                    "type": "directory" if child.is_dir() else "file",
                    "size": child.stat().st_size if child.is_file() else None,
                }
            )
        return {"workspace": workspace, "path": path, "entries": entries}

    def read_text_file(self, workspace: str, path: str) -> dict[str, Any]:
        _, file_path = self.policy.resolve(workspace, path)
        if not file_path.is_file():
            raise SecurityError("Path is not a file.")
        size = file_path.stat().st_size
        if size > MAX_FILE_BYTES:
            raise SecurityError(f"File exceeds the {MAX_FILE_BYTES}-byte read limit.")
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise SecurityError("Only UTF-8 text files can be read.") from exc
        return {"workspace": workspace, "path": path, "size": size, "content": content}

    def search_text(
        self,
        workspace: str,
        query: str,
        path: str = ".",
        case_sensitive: bool = False,
    ) -> dict[str, Any]:
        if not query:
            raise SecurityError("Search query cannot be empty.")
        root_workspace, target = self.policy.resolve(workspace, path)
        root = Path(root_workspace.path).resolve(strict=True)
        files = [target] if target.is_file() else target.rglob("*")
        needle = query if case_sensitive else query.casefold()
        matches: list[dict[str, Any]] = []
        for file_path in files:
            if len(matches) >= MAX_SEARCH_MATCHES:
                break
            if not file_path.is_file() or file_path.is_symlink():
                continue
            relative = file_path.relative_to(root)
            if is_sensitive_path(relative) or file_path.stat().st_size > MAX_FILE_BYTES:
                continue
            try:
                with file_path.open("r", encoding="utf-8") as handle:
                    for line_number, line in enumerate(handle, start=1):
                        haystack = line if case_sensitive else line.casefold()
                        if needle in haystack:
                            matches.append(
                                {
                                    "path": relative.as_posix(),
                                    "line": line_number,
                                    "text": line.rstrip("\r\n")[:500],
                                }
                            )
                            if len(matches) >= MAX_SEARCH_MATCHES:
                                break
            except (UnicodeDecodeError, OSError):
                continue
        return {"query": query, "matches": matches, "truncated": len(matches) >= MAX_SEARCH_MATCHES}

    def write_text_file(
        self,
        workspace: str,
        path: str,
        content: str,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_FILE_BYTES:
            raise SecurityError(f"Content exceeds the {MAX_FILE_BYTES}-byte write limit.")
        _, file_path = self.policy.resolve(
            workspace,
            path,
            require_write=True,
            must_exist=False,
        )
        if file_path.exists() and not overwrite:
            raise SecurityError("File already exists; set overwrite=true to replace it.")
        if file_path.exists() and not file_path.is_file():
            raise SecurityError("Path is not a file.")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = file_path.with_name(file_path.name + ".ai-actuator.tmp")
        temporary.write_text(content, encoding="utf-8", newline="")
        os.replace(temporary, file_path)
        return {"workspace": workspace, "path": path, "bytes_written": len(encoded)}

    def edit_text_file(
        self,
        workspace: str,
        path: str,
        old_text: str,
        new_text: str,
        expected_replacements: int = 1,
    ) -> dict[str, Any]:
        if not old_text:
            raise SecurityError("old_text cannot be empty.")
        if expected_replacements < 1:
            raise SecurityError("expected_replacements must be at least 1.")
        self.policy.resolve(workspace, path, require_write=True)
        current = self.read_text_file(workspace, path)["content"]
        actual = current.count(old_text)
        if actual != expected_replacements:
            raise SecurityError(
                f"Expected {expected_replacements} replacement(s), but found {actual}; file unchanged."
            )
        updated = current.replace(old_text, new_text)
        result = self.write_text_file(workspace, path, updated, overwrite=True)
        return {**result, "replacements": actual}

    def git_status(self, workspace: str) -> dict[str, Any]:
        workspace_config = self.policy.workspace(workspace)
        output = self._run_git(Path(workspace_config.path), ["status", "--short"])
        return {"workspace": workspace, "status": output}

    def git_diff(self, workspace: str, path: str | None = None) -> dict[str, Any]:
        workspace_config = self.policy.workspace(workspace)
        root = Path(workspace_config.path)
        args = ["diff", "--no-ext-diff"]
        if path:
            _, resolved = self.policy.resolve(workspace, path)
            args.extend(["--", resolved.relative_to(root.resolve()).as_posix()])
        output = self._run_git(root, args)
        return {"workspace": workspace, "path": path, "diff": output}

    @staticmethod
    def _run_git(root: Path, args: list[str]) -> str:
        try:
            completed = subprocess.run(
                ["git", "-C", str(root), *args],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                shell=False,
            )
        except FileNotFoundError as exc:
            raise SecurityError("Git is not installed or not available in PATH.") from exc
        except subprocess.TimeoutExpired as exc:
            raise SecurityError("Git command timed out.") from exc
        if completed.returncode != 0:
            message = completed.stderr.strip() or "Git command failed."
            raise SecurityError(message[:2000])
        return completed.stdout[:MAX_FILE_BYTES]

