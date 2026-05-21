"""
M.A.Y.D.A.Y Tool Gateway Core — v5.0 Unified Safety & UI Permission
=====================================================================
Intercepts all tool calls, enforces path-based safety, and blocks execution
until explicit user approval is granted via the UI.
"""
import logging
import os
from pathlib import Path

from runtime.world_state import world_state

logger = logging.getLogger("mayday.gateway")

class GatewayPermissionDenied(Exception):
    """Raised when user denies permission for an action."""
    pass

class SafetyViolationError(Exception):
    """Raised when an action violates hard-coded safety constraints."""
    pass


class ToolGatewayCore:
    def __init__(self, allowed_root=None):
        if allowed_root is None:
            allowed_root = Path(__file__).resolve().parent.parent
        self.allowed_root = Path(allowed_root).resolve()
        system_drive = os.environ.get("SystemDrive", "")
        windows_root = Path(os.environ.get("SystemRoot", system_drive + "\\Windows")).resolve()
        program_files = Path(os.environ.get("ProgramFiles", system_drive + "\\Program Files")).resolve()
        program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", system_drive + "\\Program Files (x86)")).resolve()
        users_root = Path(system_drive + "\\Users").resolve() if system_drive else Path.home().parent.resolve()
        self.hard_block_paths = [
            windows_root,
            program_files,
            program_files_x86,
            users_root,
            "system32",
            "boot",
            "registry"
        ]
        self.permission_callback = None
        self.session_allow_always = False
        self.session_denied_scopes: dict[str, str] = {}

    def set_permission_callback(self, callback):
        """
        Callback should be a function: cb(action_type: str, details: str) -> bool
        that blocks until the user provides a response.
        """
        self.permission_callback = callback

    def reset_denials(self) -> None:
        self.session_denied_scopes.clear()
        world_state.clear_permission_blocks()

    def _validate_path_safety(self, raw_path: str):
        if not raw_path:
            return
            
        # Check against string hard-blocks first (e.g., 'system32')
        lower_path = raw_path.lower()
        for block in self.hard_block_paths:
            if isinstance(block, str) and block in lower_path:
                raise SafetyViolationError(f"Path contains blocked keyword: {block}")
                
        # Resolve and check against allowed_root
        try:
            p = Path(raw_path).resolve()
            
            # Check blocked root paths
            for block in self.hard_block_paths:
                if isinstance(block, Path):
                    try:
                        if p.is_relative_to(block):
                            raise SafetyViolationError(f"Path is inside hard-blocked directory: {block}")
                    except ValueError:
                        pass # is_relative_to can raise in older pythons if different drives, handle carefully below
                    
                    # Safer check for different drives or older python
                    if str(p).startswith(str(block)):
                        raise SafetyViolationError(f"Path is inside hard-blocked directory: {block}")

            if not str(p).startswith(str(self.allowed_root)):
                raise SafetyViolationError(f"Path '{p}' is outside allowed root '{self.allowed_root}'")
                
        except Exception as e:
            if isinstance(e, SafetyViolationError):
                raise
            raise SafetyViolationError(f"Invalid path format: {raw_path}")

    def validate_safety(self, tool_name: str, parameters: dict) -> bool:
        """Validate path safety without prompting the UI."""
        for path in self._paths_to_check(tool_name, parameters):
            if path:
                self._validate_path_safety(path)
        return True

    def validate_and_request_permission(self, tool_name: str, parameters: dict) -> bool:
        """
        Validates safety constraints and requests user permission.
        Raises GatewayPermissionDenied or SafetyViolationError if blocked.
        """
        # 1. Classify action type & extract details
        action_type = "System/Model Operation"
        details = f"Executing {tool_name} with params: {parameters}"
        scope = tool_name or "tool"

        if scope in self.session_denied_scopes:
            reason = self.session_denied_scopes[scope]
            raise GatewayPermissionDenied(
                f"User previously denied {scope} access ({reason}). "
                "Reset permission blocks explicitly before retrying."
            )
        
        # Determine specific paths to check
        paths_to_check = self._paths_to_check(tool_name, parameters)
        if tool_name == "file":
            sub_name = parameters.get("_tool_name", "read")
            path = parameters.get("path", parameters.get("file_path", parameters.get("directory", "")))
            action_label = str(sub_name).removeprefix("file_").replace("_", " ").title()
            action_type = f"File {action_label}"
            
            if "write" in sub_name:
                content_preview = str(parameters.get("content", ""))[:100]
                details = f"File: {path}\nPreview: {content_preview}..."
            else:
                details = f"File/Dir: {path}"
                
        elif tool_name == "project":
            action_type = "Project Generation (Codex Mode)"
            details = f"Project: {parameters.get('project_name', 'Unknown')}\n"
            files = parameters.get("files", [])
            details += f"Generating {len(files)} files.\n"

        elif tool_name == "scaffold":
            action_type = "Project Scaffold"
            details = f"Project: {parameters.get('project_name', 'Unknown')}\n"
            files = parameters.get("files", [])
            details += f"Generating {len(files)} files.\n"
                
        elif tool_name in {"system", "powershell", "shell"}:
            action_type = "System Command Execution"
            cmd = parameters.get("command", "")
            details = f"Command: {cmd}"

        elif tool_name == "browser":
            sub_name = parameters.get("_tool_name", "browser_action")
            action_label = str(sub_name).removeprefix("browser_").replace("_", " ").title()
            action_type = f"Browser {action_label}"
            details = f"URL: {parameters.get('url', '')}"

        # 2. Check Safety Layer
        for path in paths_to_check:
            if path:
                self._validate_path_safety(path)

        # 3. Trigger UI Permission
        if self.session_allow_always:
            logger.info(f"Gateway: Auto-allowing {action_type} (Session Allow Always)")
            return True

        if not self.permission_callback:
            logger.warning(f"Gateway: No permission callback set. Denying {action_type} by default.")
            raise GatewayPermissionDenied(f"Permission required for {action_type} but UI is not connected.")

        logger.info(f"Gateway: Requesting permission for {action_type}")
        # permission_callback should return "ALLOW", "DENY", or "ALLOW_ALWAYS"
        response = self.permission_callback(action_type, details)
        
        if response == "ALLOW_ALWAYS":
            self.session_allow_always = True
            logger.info("Gateway: User selected ALLOW ALWAYS.")
            return True
        elif response == "ALLOW":
            logger.info("Gateway: User allowed action.")
            return True
        else:
            logger.warning(f"Gateway: User denied {action_type}")
            self.session_denied_scopes[scope] = action_type
            world_state.set_permission_blocked(scope, action_type)
            raise GatewayPermissionDenied(f"User denied execution of {action_type}.")

    def _paths_to_check(self, tool_name: str, parameters: dict) -> list[str]:
        if tool_name == "file":
            return [parameters.get("path", parameters.get("file_path", parameters.get("directory", "")))]
        if tool_name in {"project", "scaffold"}:
            return [f.get("path", "") for f in parameters.get("files", []) if isinstance(f, dict)]
        if tool_name in {"system", "powershell", "shell"} and "run" in parameters.get("_tool_name", ""):
            return [parameters.get("script_path", ""), parameters.get("cwd", "")]
        if tool_name == "server":
            return [parameters.get("project_dir", parameters.get("path", ""))]
        return []
