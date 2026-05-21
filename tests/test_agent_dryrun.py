from __future__ import annotations

import json
import shutil
from pathlib import Path

from core.orchestrator import Orchestrator
from runtime.engine import ExecutionEngine


class SequenceRouter:
    def __init__(self, responses: list[dict]):
        self._responses = list(responses)

    def route(self, _messages):
        if not self._responses:
            return json.dumps({"action": "respond", "text": "done"}), "mock"
        return json.dumps(self._responses.pop(0)), "mock"


def test_agent_dryrun_scaffold_then_done():
    project_dir = Path("projects") / "test_app"
    if project_dir.exists():
        shutil.rmtree(project_dir)

    router = SequenceRouter(
        [
            {
                "action": "scaffold",
                "project_name": "test_app",
                "stack": "flask",
                "files": [
                    {
                        "path": "app.py",
                        "content": "from flask import Flask\napp = Flask(__name__)\n",
                    }
                ],
            },
            {"action": "respond", "text": "done"},
        ]
    )

    engine = ExecutionEngine()
    engine.gateway.session_allow_always = True
    orchestrator = Orchestrator(router, engine)
    response = orchestrator.run("build me a flask app")

    assert response == "done"
    assert project_dir.exists()
    assert (project_dir / "app.py").exists()


def test_agent_loop_guard_stops_repeated_identical_actions():
    router = SequenceRouter(
        [
            {"action": "shell_run", "command": "echo hi"},
            {"action": "shell_run", "command": "echo hi"},
            {"action": "shell_run", "command": "echo hi"},
            {"action": "shell_run", "command": "echo hi"},
        ]
    )
    engine = ExecutionEngine()
    orchestrator = Orchestrator(router, engine)
    response = orchestrator.run("run the server now")
    assert "repeated identical actions" in response.lower()


def test_repeated_identical_action_executes_only_once():
    class CountingEngine:
        def __init__(self):
            self.calls = 0

        def execute(self, tool_name, parameters):
            self.calls += 1
            return {"status": "success", "tool": tool_name}

    router = SequenceRouter(
        [
            {"action": "shell_run", "command": "echo hi"},
            {"action": "shell_run", "command": "echo hi"},
            {"action": "respond", "text": "done"},
        ]
    )
    engine = CountingEngine()
    orchestrator = Orchestrator(router, engine)

    response = orchestrator.run("run the server now")

    assert "repeated identical actions" in response.lower()
    assert engine.calls == 1
