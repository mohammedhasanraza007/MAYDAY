from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx
import psutil

import runtime.scaffold_engine as scaffold_module
from runtime.scaffold_engine import ScaffoldEngine
from runtime.server_runner import ServerRunner


def test_flask_scaffold_launch_and_stop(tmp_path, monkeypatch):
    sys.path.insert(0, str(tmp_path))

    projects_root = tmp_path / "projects"
    monkeypatch.setattr(scaffold_module, "PROJECT_ROOT", projects_root)

    scaffold = ScaffoldEngine()
    scaffold_result = scaffold.execute(
        {
            "project_name": "launch_demo",
            "stack": "flask",
            "files": [
                {
                    "path": "app.py",
                    "content": (
                        "from flask import Flask\n"
                        "app = Flask(__name__)\n\n"
                        "@app.get('/')\n"
                        "def home():\n"
                        "    return 'ok'\n"
                    ),
                }
            ],
        }
    )

    project_dir = scaffold_result["project_dir"]
    runner = ServerRunner()
    launch_result = runner.launch(project_dir, "flask")

    response = httpx.get(launch_result["url"], timeout=5.0)
    assert response.status_code == 200

    state = runner.status(project_dir)
    assert state["running"] is True
    assert state["pid"] == launch_result["pid"]
    assert psutil.pid_exists(launch_result["pid"]) is True

    stop_state = runner.stop(project_dir)
    assert stop_state["running"] is False

    for _ in range(30):
        if not psutil.pid_exists(launch_result["pid"]):
            break
        time.sleep(0.1)
    assert psutil.pid_exists(launch_result["pid"]) is False
