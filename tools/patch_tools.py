"""
MAYDAY Patch Tools - surgical file editing without full overwrites.
Provides file_patch, file_replace_block, file_insert_after, file_delete_lines.
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path

from tools.base_tool import BaseTool

logger = logging.getLogger("mayday.tools.patch")


class PatchTools(BaseTool):
    @property
    def name(self) -> str:
        return "patch"

    @property
    def description(self) -> str:
        return "Surgical file editing: replace blocks, insert lines, apply diffs"

    def get_capabilities(self) -> list[str]:
        return ["file_patch", "file_replace_block", "file_insert_after", "file_delete_lines"]

    def execute(self, parameters: dict) -> dict:
        action = parameters.get("_tool_name", "")
        if action == "file_patch":
            return self._patch(parameters)
        if action == "file_replace_block":
            return self._replace_block(parameters)
        if action == "file_insert_after":
            return self._insert_after(parameters)
        if action == "file_delete_lines":
            return self._delete_lines(parameters)
        return {"status": "error", "error": f"Unknown patch action: {action}"}

    def _patch(self, parameters: dict) -> dict:
        path = Path(parameters.get("path", ""))
        old_text = parameters.get("old_text", "")
        new_text = parameters.get("new_text", "")
        if not path.exists():
            return {"status": "error", "error": f"File not found: {path}"}
        content = path.read_text(encoding="utf-8")
        if old_text not in content:
            return {"status": "error", "error": "old_text not found in file"}
        updated = content.replace(old_text, new_text, 1)
        path.write_text(updated, encoding="utf-8")
        return {
            "status": "ok",
            "path": str(path),
            "chars_changed": abs(len(new_text) - len(old_text)),
        }

    def _replace_block(self, parameters: dict) -> dict:
        path = Path(parameters.get("path", ""))
        block_name = parameters.get("block_name", "")
        new_content = parameters.get("new_content", "")
        if not path.exists():
            return {"status": "error", "error": f"File not found: {path}"}
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            return {"status": "error", "error": f"Syntax error in file: {exc}"}

        lines = source.splitlines(keepends=True)
        target = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == block_name:
                    target = node
                    break
        if target is None:
            return {"status": "error", "error": f"Block '{block_name}' not found"}

        start = target.lineno - 1
        end = target.end_lineno
        if getattr(target, "decorator_list", None):
            start = min(decorator.lineno for decorator in target.decorator_list) - 1

        replacement = new_content + ("\n" if not new_content.endswith("\n") else "")
        path.write_text("".join(lines[:start] + [replacement] + lines[end:]), encoding="utf-8")
        return {
            "status": "ok",
            "path": str(path),
            "block": block_name,
            "lines_replaced": end - start,
        }

    def _insert_after(self, parameters: dict) -> dict:
        path = Path(parameters.get("path", ""))
        after_pattern = parameters.get("after_pattern", "")
        insert_text = parameters.get("insert_text", "")
        if not path.exists():
            return {"status": "error", "error": f"File not found: {path}"}
        content = path.read_text(encoding="utf-8")
        index = content.find(after_pattern)
        if index == -1:
            return {"status": "error", "error": "after_pattern not found"}
        insert_at = index + len(after_pattern)
        path.write_text(content[:insert_at] + "\n" + insert_text + content[insert_at:], encoding="utf-8")
        return {"status": "ok", "path": str(path)}

    def _delete_lines(self, parameters: dict) -> dict:
        path = Path(parameters.get("path", ""))
        start_line = parameters.get("start_line", 1) - 1
        end_line = parameters.get("end_line", start_line + 1)
        if not path.exists():
            return {"status": "error", "error": f"File not found: {path}"}
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        del lines[start_line:end_line]
        path.write_text("".join(lines), encoding="utf-8")
        return {"status": "ok", "path": str(path), "lines_deleted": end_line - start_line}
