"""
M.A.Y.D.A.Y Physical Tool Execution
===================================
Real OS-level actions for file management, browser, and terminal.
"""
import os
import webbrowser
import subprocess
import shutil
import logging
from pathlib import Path

logger = logging.getLogger("mayday.tools")

class FileTools:
    def execute(self, params):
        action = params.get("_tool_name", params.get("action"))
        path = params.get("path")
        
        if action == "read":
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        elif action == "write":
            content = params.get("content", "")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"File written: {path}"
        elif action == "list":
            return os.listdir(path or ".")
        return f"Unknown file action: {action}"

class BrowserTools:
    def execute(self, params):
        url = params.get("url")
        if url:
            webbrowser.open(url)
            return f"Opened browser: {url}"
        return "No URL provided"

class SystemTools:
    def execute(self, params):
        cmd = params.get("command")
        if cmd:
            try:
                result = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True)
                return result
            except subprocess.CalledProcessError as e:
                return f"Command failed: {e.output}"
        return "No command provided"
