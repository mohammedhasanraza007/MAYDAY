"""
M.A.Y.D.A.Y PowerShell Tools — Real command execution
=====================================================
Handles execution of PowerShell commands and Python scripts.
"""
import logging
import subprocess
import os
from pathlib import Path
from tools.base_tool import BaseTool

logger = logging.getLogger("mayday.tools.powershell")

class PowerShellTools(BaseTool):
    @property
    def name(self) -> str: return 'powershell'
    
    @property
    def description(self) -> str: return 'Execute PowerShell commands and Python scripts'

    def get_capabilities(self) -> list[str]:
        return ['powershell_run', 'powershell_python_script']

    def execute(self, parameters: dict) -> dict:
        name = parameters.get('_tool_name', '')
        if 'python' in name:
            return self._run_python(parameters)
        return self._run_powershell(parameters)

    def _run_powershell(self, params: dict) -> dict:
        command = params.get('command', '')
        cwd = params.get('cwd') or str(Path(__file__).resolve().parent.parent / 'workspace')
        
        if not command:
            return {"status": "error", "error": "No command provided"}

        try:
            # Create workspace if it doesn't exist
            Path(cwd).mkdir(parents=True, exist_ok=True)
            
            result = subprocess.run(
                ["powershell", "-Command", command],
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=60
            )
            
            return {
                "status": "success" if result.returncode == 0 else "error",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "cwd": str(Path(cwd).resolve()),
                "verified": result.returncode == 0 and Path(cwd).exists(),
                "error": "" if result.returncode == 0 else result.stderr or result.stdout or "Command failed",
            }
        except subprocess.TimeoutExpired:
            return {"status": "error", "error": "Command timed out after 60s"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _run_python(self, params: dict) -> dict:
        script_path = params.get('script_path', '')
        args = params.get('args', [])
        cwd = params.get('cwd') or str(Path(__file__).resolve().parent.parent / 'workspace')

        if not script_path:
            return {"status": "error", "error": "No script_path provided"}

        try:
            full_cmd = [os.sys.executable, script_path] + args
            
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=60
            )
            
            return {
                "status": "success" if result.returncode == 0 else "error",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "cwd": str(Path(cwd).resolve()),
                "verified": result.returncode == 0 and Path(cwd).exists(),
                "error": "" if result.returncode == 0 else result.stderr or result.stdout or "Script failed",
            }
        except subprocess.TimeoutExpired:
            return {"status": "error", "error": "Script timed out after 60s"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
