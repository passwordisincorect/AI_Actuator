from __future__ import annotations

import json
import os
import secrets
import shutil
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

Permission = Literal["read-only", "workspace-write"]


@dataclass(frozen=True)
class WorkspaceConfig:
    name: str
    path: str
    permission: Permission = "read-only"


@dataclass(frozen=True)
class AppConfig:
    token: str
    workspaces: list[WorkspaceConfig] = field(default_factory=list)


def _default_local_app_data() -> Path:
    value = os.environ.get("LOCALAPPDATA")
    if value:
        return Path(value)
    return Path.home() / ".local" / "share"


class ConfigStore:
    def __init__(self, base_dir: Path | None = None) -> None:
        local_app_data = base_dir or _default_local_app_data()
        self.directory = local_app_data / "AI_Actuator"
        self.path = self.directory / "config.json"
        self.legacy_path = local_app_data / "AIArmBridge" / "config.json"
        self._lock = threading.RLock()

    def load(self) -> AppConfig:
        with self._lock:
            self._ensure_exists()
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            token = str(raw.get("token") or secrets.token_urlsafe(32))
            workspaces: list[WorkspaceConfig] = []
            for item in raw.get("workspaces", []):
                permission = item.get("permission", "read-only")
                if permission not in ("read-only", "workspace-write"):
                    permission = "read-only"
                workspaces.append(
                    WorkspaceConfig(
                        name=str(item["name"]),
                        path=str(item["path"]),
                        permission=permission,
                    )
                )
            config = AppConfig(token=token, workspaces=workspaces)
            if raw.get("token") != token:
                self.save(config)
            return config

    def save(self, config: AppConfig) -> None:
        with self._lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".json.tmp")
            payload = {
                "token": config.token,
                "workspaces": [asdict(workspace) for workspace in config.workspaces],
            }
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self.path)

    def add_workspace(self, workspace: WorkspaceConfig) -> AppConfig:
        with self._lock:
            current = self.load()
            kept = [item for item in current.workspaces if item.name != workspace.name]
            updated = AppConfig(current.token, [*kept, workspace])
            self.save(updated)
            return updated

    def remove_workspace(self, name: str) -> AppConfig:
        with self._lock:
            current = self.load()
            updated = AppConfig(
                current.token,
                [item for item in current.workspaces if item.name != name],
            )
            self.save(updated)
            return updated

    def regenerate_token(self) -> AppConfig:
        with self._lock:
            current = self.load()
            updated = AppConfig(secrets.token_urlsafe(32), current.workspaces)
            self.save(updated)
            return updated

    def _ensure_exists(self) -> None:
        if self.path.exists():
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.legacy_path.is_file():
            shutil.copy2(self.legacy_path, self.path)
            return
        self.save(AppConfig(token=secrets.token_urlsafe(32)))

