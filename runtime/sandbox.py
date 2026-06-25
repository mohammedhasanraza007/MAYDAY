from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any


class SandboxError(RuntimeError):
    pass


class SandboxRunResult(dict):
    """Dict result that also compares equal to stdout for legacy probes."""

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.get("stdout") == other
        return super().__eq__(other)


class ProcessSandbox:
    def __init__(self, config_path: str | Path | None = None) -> None:
        root = Path(__file__).resolve().parent.parent
        self.config_path = Path(config_path) if config_path else root / "config" / "mayday_config.json"
        self._sandboxes: dict[str, dict[str, Any]] = {}

    def create(self) -> str:
        self._assert_enabled()
        sandbox_id = uuid.uuid4().hex[:12]
        tempdir = Path(tempfile.mkdtemp(prefix="mayday_process_sandbox_"))
        process = subprocess.Popen(
            [sys.executable, "-i", "-q"],
            cwd=str(tempdir),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self._sandboxes[sandbox_id] = {"tempdir": tempdir, "process": process}
        return sandbox_id

    def run_command(self, sandbox_id: str, cmd: str, timeout: int = 30) -> SandboxRunResult:
        self._assert_enabled()
        if sandbox_id not in self._sandboxes:
            raise SandboxError(f"Unknown sandbox id: {sandbox_id}")
        if not isinstance(cmd, str) or not cmd.strip():
            raise SandboxError("cmd must be a non-empty string")
        tempdir: Path = self._sandboxes[sandbox_id]["tempdir"]
        try:
            completed = subprocess.run(
                cmd,
                cwd=str(tempdir),
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=self._minimal_env(),
            )
            return SandboxRunResult(
                {
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                    "returncode": completed.returncode,
                }
            )
        except subprocess.TimeoutExpired as exc:
            return SandboxRunResult(
                {
                    "stdout": exc.stdout or "",
                    "stderr": exc.stderr or "Process sandbox command timed out",
                    "returncode": 124,
                }
            )

    def destroy(self, sandbox_id: str) -> None:
        state = self._sandboxes.pop(sandbox_id, None)
        if not state:
            return
        process: subprocess.Popen = state["process"]
        if process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        shutil.rmtree(state["tempdir"], ignore_errors=True)

    def run_isolated(self, code: str, timeout: int = 30) -> SandboxRunResult:
        sandbox_id = self.create()
        try:
            state = self._sandboxes[sandbox_id]
            script = Path(state["tempdir"]) / "snippet.py"
            script.write_text(code, encoding="utf-8")
            command = f'"{sys.executable}" "{script.name}"'
            return self.run_command(sandbox_id, command, timeout=timeout)
        finally:
            self.destroy(sandbox_id)

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        code = str(payload.get("code", payload.get("python_source", "")))
        return dict(self.run_isolated(code, int(payload.get("timeout", 30))))

    def _assert_enabled(self) -> None:
        if not self._enabled():
            raise SandboxError(
                "Process sandbox disabled. Set config/mayday_config.json process_sandbox=true."
            )

    def _enabled(self) -> bool:
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return data.get("process_sandbox") is True

    def _minimal_env(self) -> dict[str, str]:
        allowed = {
            "PATH",
            "PATHEXT",
            "SYSTEMROOT",
            "TEMP",
            "TMP",
            "USERNAME",
            "USERPROFILE",
            "WINDIR",
        }
        return {key: value for key, value in os.environ.items() if key.upper() in allowed}


def run_isolated(code: str, timeout: int = 30) -> SandboxRunResult:
    return ProcessSandbox().run_isolated(code, timeout=timeout)

