from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

from core.exceptions import ServerStartError


def find_free_port(start: int = 5000, end: int = 5999) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if probe.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise ServerStartError(f"No free port found in range {start}-{end}")


class ServerRunner:
    def __init__(self) -> None:
        self._processes: dict[str, dict] = {}

    def execute(self, parameters: dict) -> dict:
        action = parameters.get("_tool_name", "")
        project_dir = parameters.get("project_dir", parameters.get("path", ""))
        if "stop" in action:
            return {"status": "success", **self.stop(project_dir)}
        if "status" in action:
            return {"status": "success", **self.status(project_dir)}
        stack = parameters.get("stack", "flask")
        return {"status": "success", **self.launch(project_dir, stack)}

    def launch(self, project_dir: str, stack: str) -> dict:
        project_path = Path(project_dir).resolve()
        if not project_path.exists():
            raise ServerStartError(f"Project directory does not exist: {project_path}")
        if not project_path.is_dir():
            raise ServerStartError(f"Project path is not a directory: {project_path}")

        normalized_stack = (stack or "").strip().lower()
        if not normalized_stack:
            raise ServerStartError("Stack is required")

        port = find_free_port()
        url = f"http://127.0.0.1:{port}"
        command = self._command_for_stack(normalized_stack, port)
        environment = os.environ.copy()
        environment["PORT"] = str(port)
        if normalized_stack == "flask":
            environment.setdefault("FLASK_APP", "app.py")

        process = subprocess.Popen(
            command,
            cwd=str(project_path),
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            self._wait_until_ready(process, url, timeout_seconds=15.0)
        except Exception as exc:
            self._kill_process(process)
            if isinstance(exc, ServerStartError):
                raise
            raise ServerStartError(str(exc)) from exc

        self._processes[str(project_path)] = {
            "process": process,
            "port": port,
            "pid": process.pid,
            "url": url,
            "stack": normalized_stack,
        }
        return {"url": url, "port": port, "pid": process.pid}

    def stop(self, project_dir: str) -> dict:
        key = str(Path(project_dir).resolve())
        process_data = self._processes.get(key)
        if not process_data:
            return {"port": None, "pid": None, "running": False}

        process: subprocess.Popen = process_data["process"]
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

        running = process.poll() is None
        return {
            "port": process_data["port"],
            "pid": process_data["pid"],
            "running": running,
        }

    def status(self, project_dir: str) -> dict:
        key = str(Path(project_dir).resolve())
        process_data = self._processes.get(key)
        if not process_data:
            return {"port": None, "pid": None, "running": False}

        process: subprocess.Popen = process_data["process"]
        return {
            "port": process_data["port"],
            "pid": process_data["pid"],
            "running": process.poll() is None,
        }

    def _command_for_stack(self, stack: str, port: int) -> list[str]:
        if stack == "flask":
            return [
                sys.executable,
                "-m",
                "flask",
                "run",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ]
        if stack == "fastapi":
            return [
                sys.executable,
                "-m",
                "uvicorn",
                "app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ]
        if stack == "static":
            return [
                sys.executable,
                "-m",
                "http.server",
                str(port),
                "--bind",
                "127.0.0.1",
            ]
        raise ServerStartError(f"Unsupported stack: {stack}")

    def _wait_until_ready(self, process: subprocess.Popen, url: str, timeout_seconds: float) -> None:
        deadline = time.time() + timeout_seconds
        last_status = None
        with httpx.Client(timeout=1.0) as client:
            while time.time() < deadline:
                if process.poll() is not None:
                    stderr = ""
                    if process.stderr:
                        stderr = process.stderr.read() or ""
                    raise ServerStartError(f"Server process exited early: {stderr.strip()}")
                try:
                    response = client.get(url)
                    last_status = response.status_code
                    if response.status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(0.3)
        raise ServerStartError(
            f"Server did not return HTTP 200 within {int(timeout_seconds)}s "
            f"(last status: {last_status})"
        )

    def _kill_process(self, process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        process.kill()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
