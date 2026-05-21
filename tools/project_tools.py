"""
M.A.Y.D.A.Y Project Tools — v5.0 Codex Mode
===========================================
Handles generation of multi-file projects in a single action.
"""
import logging
import hashlib
from pathlib import Path
from tools.base_tool import BaseTool
from core.gateway import ToolGatewayCore

logger = logging.getLogger("mayday.tools.project")

class ProjectTools(BaseTool):
    @property
    def name(self) -> str: return 'project'
    
    @property
    def description(self) -> str: return 'Generates multi-file projects (Codex Mode)'

    def get_capabilities(self) -> list[str]:
        return ['execute_project']

    def execute(self, parameters: dict) -> dict:
        project_name = parameters.get("project_name", "Untitled")
        files = parameters.get("files", [])
        
        results = []
        for f in files:
            p_path = f.get("path")
            content = f.get("content", "")
            if not p_path:
                continue
                
            path = Path(p_path).resolve()
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                actual = path.read_text(encoding="utf-8", errors="replace")
                if actual != content:
                    raise IOError("post-write verification failed")
                sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
                results.append(
                    {
                        "file": str(path),
                        "status": "success",
                        "bytes": len(content.encode("utf-8")),
                        "sha256": sha256,
                        "verified": True,
                    }
                )
            except Exception as e:
                results.append({"file": str(path), "status": "error", "error": str(e)})
                
        all_verified = bool(results) and all(item.get("verified") for item in results)
        return {
            "status": "success" if all_verified else "error",
            "error": "" if all_verified else "One or more project files failed verification",
            "project": project_name,
            "files_created": len([item for item in results if item.get("status") == "success"]),
            "verified": all_verified,
            "details": results
        }
