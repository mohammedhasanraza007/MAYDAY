"""
MAYDAY Test Runner - auto-test execution loop.
Runs pytest or npm test in a project directory and returns structured results.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

from tools.base_tool import BaseTool

logger = logging.getLogger("mayday.tools.test_runner")


class TestRunnerTool(BaseTool):
    @property
    def name(self) -> str:
        return "test_runner"

    @property
    def description(self) -> str:
        return "Run test suites in a project directory"

    def get_capabilities(self) -> list[str]:
        return ["run_tests", "run_pytest", "run_npm_test"]

    def execute(self, parameters: dict) -> dict:
        action = parameters.get("_tool_name", "run_tests")
        project_dir = Path(parameters.get("project_dir", "."))
        if not project_dir.exists():
            return {"status": "error", "error": f"Directory not found: {project_dir}"}
        if "pytest" in action or self._has_pytest(project_dir):
            return self._run_pytest(project_dir)
        if "npm" in action or (project_dir / "package.json").exists():
            return self._run_npm_test(project_dir)
        return {"status": "error", "error": "No test suite detected. Add pytest tests or package.json."}

    def _has_pytest(self, directory: Path) -> bool:
        return any(directory.glob("test_*.py")) or any(directory.glob("tests/"))

    def _run_pytest(self, directory: Path) -> dict:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", str(directory), "--tb=short", "-q", "--timeout=30"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(directory),
            )
            return {
                "status": "ok" if result.returncode == 0 else "failed",
                "returncode": result.returncode,
                "stdout": result.stdout[-2000:],
                "stderr": result.stderr[-500:],
                "passed": result.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            return {"status": "error", "error": "Test run timed out after 60 seconds"}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _run_npm_test(self, directory: Path) -> dict:
        try:
            result = subprocess.run(
                ["npm", "test", "--", "--watchAll=false"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(directory),
            )
            return {
                "status": "ok" if result.returncode == 0 else "failed",
                "returncode": result.returncode,
                "stdout": result.stdout[-2000:],
                "stderr": result.stderr[-500:],
                "passed": result.returncode == 0,
            }
        except FileNotFoundError:
            return {"status": "error", "error": "npm not found on PATH"}
        except subprocess.TimeoutExpired:
            return {"status": "error", "error": "npm test timed out"}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}
