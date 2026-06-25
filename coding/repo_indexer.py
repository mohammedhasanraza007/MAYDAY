from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path
from typing import Any


LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".md": "markdown",
    ".json": "json",
    ".html": "html",
    ".css": "css",
}


class RepoIndexer:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or ".").resolve()
        self._last_index: dict[str, Any] | None = None

    def scan(self, path: Path | str) -> dict[str, Any]:
        root = Path(path).resolve()
        file_tree: list[dict[str, Any]] = []
        symbols: list[dict[str, Any]] = []
        imports: dict[str, list[str]] = {}

        for file_path in self._iter_supported_files(root):
            relative = file_path.relative_to(root).as_posix()
            language = LANGUAGE_BY_SUFFIX.get(file_path.suffix.lower(), "text")
            try:
                size = file_path.stat().st_size
            except OSError:
                size = 0
            file_tree.append({"path": relative, "language": language, "size": size})

            text = self._read_text(file_path)
            if language == "python":
                py_symbols, py_imports = self._python_index(relative, text)
                symbols.extend(py_symbols)
                imports[relative] = py_imports
            elif language in {"javascript", "typescript"}:
                js_symbols, js_imports = self._script_index(relative, text)
                symbols.extend(js_symbols)
                imports[relative] = js_imports
            else:
                imports[relative] = []

        index = {
            "file_tree": sorted(file_tree, key=lambda item: item["path"]),
            "symbols": sorted(symbols, key=lambda item: (item["file"], item["line"], item["name"])),
            "imports": imports,
            "summary": self._summary(file_tree, symbols),
        }
        self.root = root
        self._last_index = index
        return index

    def build_index(self) -> dict[str, Any]:
        """Compatibility wrapper for older MAYDAY callers."""
        index = self.scan(self.root)
        symbols_by_file: dict[str, list[str]] = {}
        for symbol in index["symbols"]:
            symbols_by_file.setdefault(symbol["file"], []).append(symbol["name"])
        return {
            "file_tree": [entry["path"] for entry in index["file_tree"]],
            "symbols": symbols_by_file,
            "imports": index["imports"],
            "summary": index["summary"],
        }

    def get_context_prompt(self, path: Path | str) -> str:
        index = self.scan(path)
        top_files = ", ".join(entry["path"] for entry in index["file_tree"][:20])
        top_symbols = ", ".join(
            f"{item['name']}({item['type']}) in {item['file']}:{item['line']}"
            for item in index["symbols"][:30]
        )
        return (
            "Repository context:\n"
            f"{index['summary']}\n"
            f"Files: {top_files}\n"
            f"Symbols: {top_symbols}"
        )

    def cache_to_disk(self, path: Path | str) -> None:
        cache_path = Path(path)
        index = self._last_index or self.scan(self.root)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")

    def load_from_cache(self, path: Path | str) -> dict[str, Any] | None:
        cache_path = Path(path)
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        self._last_index = data
        return data

    def _iter_supported_files(self, root: Path) -> list[Path]:
        if not root.exists():
            return []
        ignored_dirs = {".git", ".venv", "__pycache__", "node_modules"}
        files: list[Path] = []
        for current_root, dirnames, filenames in os.walk(root):
            current_path = Path(current_root)
            relative_dir = current_path.relative_to(root).as_posix()
            dirnames[:] = [
                name
                for name in dirnames
                if name not in ignored_dirs
                and f"{relative_dir}/{name}".strip("./") != "runtime/python"
                and not f"{relative_dir}/{name}".strip("./").startswith("runtime/python/")
            ]
            for filename in filenames:
                file_path = current_path / filename
                if file_path.suffix.lower() in LANGUAGE_BY_SUFFIX:
                    files.append(file_path)
        return sorted(files)

    def _python_index(self, relative: str, text: str) -> tuple[list[dict[str, Any]], list[str]]:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return [], []

        symbols: list[dict[str, Any]] = []
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                symbols.append(
                    {"file": relative, "name": node.name, "type": kind, "line": node.lineno}
                )
            elif isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.extend(f"{module}.{alias.name}".strip(".") for alias in node.names)
        return symbols, sorted(dict.fromkeys(imports))

    def _script_index(self, relative: str, text: str) -> tuple[list[dict[str, Any]], list[str]]:
        symbols: list[dict[str, Any]] = []
        imports: list[str] = []
        for match in re.finditer(r"\b(?:class|function)\s+([A-Za-z_$][\w$]*)", text):
            kind = "class" if match.group(0).startswith("class") else "function"
            symbols.append(
                {
                    "file": relative,
                    "name": match.group(1),
                    "type": kind,
                    "line": text.count("\n", 0, match.start()) + 1,
                }
            )
        for match in re.finditer(r"\bimport\s+(?:.+?\s+from\s+)?['\"]([^'\"]+)['\"]", text):
            imports.append(match.group(1))
        for match in re.finditer(r"\brequire\(['\"]([^'\"]+)['\"]\)", text):
            imports.append(match.group(1))
        return symbols, sorted(dict.fromkeys(imports))

    def _read_text(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""

    def _summary(self, file_tree: list[dict[str, Any]], symbols: list[dict[str, Any]]) -> str:
        by_language: dict[str, int] = {}
        for entry in file_tree:
            by_language[entry["language"]] = by_language.get(entry["language"], 0) + 1
        language_summary = ", ".join(f"{count} {language}" for language, count in sorted(by_language.items()))
        return f"{len(file_tree)} files indexed ({language_summary}); {len(symbols)} symbols found."
