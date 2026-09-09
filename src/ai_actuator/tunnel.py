from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

_TRYCLOUDFLARE_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)


class TunnelError(RuntimeError):
    """Raised when cloudflared cannot start or a public URL cannot be obtained."""


@dataclass(frozen=True)
class TunnelStatus:
    running: bool
    public_url: str | None
    public_mcp_url: str | None
    cloudflared_path: str | None
    error: str | None


def _extract_trycloudflare_url(text: str) -> str | None:
    match = _TRYCLOUDFLARE_RE.search(text)
    return match.group(0).rstrip("/") if match else None


def discover_cloudflared(configured_path: str = "") -> Path | None:
    candidates: list[Path] = []

    if configured_path.strip():
        candidates.append(Path(configured_path).expanduser())

    env_path = os.environ.get("AI_ACTUATOR_CLOUDFLARED", "").strip()
    if env_path:
        candidates.append(Path(env_path).expanduser())

    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "cloudflared.exe")

    candidates.append(Path.cwd() / ("cloudflared.exe" if os.name == "nt" else "cloudflared"))

    try:
        project_root = Path(__file__).resolve().parents[2]
        candidates.append(project_root / ("cloudflared.exe" if os.name == "nt" else "cloudflared"))
    except IndexError:
        pass

    on_path = shutil.which("cloudflared")
    if on_path:
        candidates.append(Path(on_path))

    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        key = os.path.normcase(str(resolved))
        if key in seen:
            continue
        seen.add(key)
        if resolved.is_file():
            return resolved

    return None


class QuickTunnelManager:
    """Own one Cloudflare Quick Tunnel subprocess."""

    def __init__(self, origin_url: str, configured_cloudflared_path: str = "") -> None:
        self.origin_url = origin_url.rstrip("/")
        self.configured_cloudflared_path = configured_cloudflared_path
        self._process: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self._url_ready = threading.Event()
        self._lock = threading.RLock()
        self._public_url: str | None = None
        self._error: str | None = None
        self._logs: list[str] = []
        self._cloudflared_path: Path | None = None

    @property
    def public_url(self) -> str | None:
        with self._lock:
            return self._public_url

    @property
    def public_mcp_url(self) -> str | None:
        with self._lock:
            return f"{self._public_url}/mcp" if self._public_url else None

    @property
    def hostname(self) -> str | None:
        url = self.public_url
        if not url:
            return None
        return url.removeprefix("https://").split("/", 1)[0]

    def is_running(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def recent_logs(self, limit: int = 12) -> list[str]:
        with self._lock:
            return self._logs[-max(1, limit):]

    def status(self) -> TunnelStatus:
        with self._lock:
            running = self._process is not None and self._process.poll() is None
            public_url = self._public_url if running else None
            return TunnelStatus(
                running=running,
                public_url=public_url,
                public_mcp_url=f"{public_url}/mcp" if public_url else None,
                cloudflared_path=str(self._cloudflared_path) if self._cloudflared_path else None,
                error=self._error,
            )

    def _append_log(self, line: str) -> None:
        clean = line.rstrip("\r\n")
        if not clean:
            return
        with self._lock:
            self._logs.append(clean)
            if len(self._logs) > 200:
                del self._logs[:-200]
            url = _extract_trycloudflare_url(clean)
            if url and not self._public_url:
                self._public_url = url
                self._url_ready.set()

    def _read_output(self, process: subprocess.Popen[str]) -> None:
        stream = process.stdout
        if stream is None:
            return
        try:
            for line in stream:
                self._append_log(line)
        finally:
            code = process.poll()
            with self._lock:
                if code not in (None, 0) and not self._public_url:
                    self._error = f"cloudflared exited with code {code}."
            self._url_ready.set()

    def start(self, timeout: float = 20.0) -> TunnelStatus:
        with self._lock:
            if self._process is not None and self._process.poll() is None and self._public_url:
                return self.status()

            cloudflared = discover_cloudflared(self.configured_cloudflared_path)
            if cloudflared is None:
                self._error = (
                    "cloudflared not found. Put cloudflared.exe in the AI_Actuator folder, "
                    "set its path in /setup, or add it to PATH."
                )
                raise TunnelError(self._error)

            self._cloudflared_path = cloudflared
            self._public_url = None
            self._error = None
            self._logs.clear()
            self._url_ready.clear()

            command = [
                str(cloudflared),
                "tunnel",
                "--url",
                self.origin_url,
                "--no-autoupdate",
            ]

            kwargs: dict[str, object] = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "bufsize": 1,
            }
            if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            try:
                process = subprocess.Popen(command, **kwargs)  # type: ignore[arg-type]
            except OSError as exc:
                self._error = f"Could not start cloudflared: {exc}"
                raise TunnelError(self._error) from exc

            self._process = process
            self._reader_thread = threading.Thread(
                target=self._read_output,
                args=(process,),
                name="AI_Actuator-cloudflared-log-reader",
                daemon=True,
            )
            self._reader_thread.start()

        self._url_ready.wait(timeout)

        with self._lock:
            if self._public_url and self._process is not None and self._process.poll() is None:
                return self.status()
            logs = "\n".join(self._logs[-8:])
            error = self._error or f"Timed out after {timeout:.0f}s waiting for a Quick Tunnel URL."
            if logs:
                error = f"{error}\n{logs}"
            self._error = error

        self.stop()
        raise TunnelError(error)

    def stop(self) -> TunnelStatus:
        with self._lock:
            process = self._process

        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                    process.wait(timeout=3)
                except (OSError, subprocess.TimeoutExpired):
                    pass

        with self._lock:
            self._process = None
            self._public_url = None
            return self.status()
