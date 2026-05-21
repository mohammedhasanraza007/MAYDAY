from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from core.exceptions import ScaffoldError
from tools.base_tool import BaseTool


PROJECT_ROOT = Path(__file__).resolve().parent.parent / "projects"


class ScaffoldEngine(BaseTool):
    @property
    def name(self) -> str:
        return "scaffold"

    @property
    def description(self) -> str:
        return "Creates multi-file project scaffolds with atomic staging and verification."

    def get_capabilities(self) -> list[str]:
        return ["scaffold"]

    def execute(self, parameters: dict) -> dict:
        project_name = parameters.get("project_name")
        stack = parameters.get("stack")
        files = parameters.get("files")

        if not isinstance(project_name, str) or not project_name.strip():
            raise ScaffoldError("project_name is required")
        if not isinstance(stack, str) or not stack.strip():
            raise ScaffoldError("stack is required")
        if not isinstance(files, list) or not files:
            raise ScaffoldError("files must be a non-empty list")

        temp_root = Path(tempfile.mkdtemp(prefix="mayday_scaffold_"))
        try:
            normalized_name = project_name.strip()
            file_paths: list[str] = []
            sha_map: dict[str, str] = {}

            for index, file_spec in enumerate(files):
                if not isinstance(file_spec, dict):
                    raise ScaffoldError(f"files[{index}] must be an object")
                if "path" not in file_spec or "content" not in file_spec:
                    raise ScaffoldError(f"files[{index}] requires path and content")
                if not isinstance(file_spec["path"], str) or not file_spec["path"].strip():
                    raise ScaffoldError(f"files[{index}].path must be a non-empty string")
                if not isinstance(file_spec["content"], str):
                    raise ScaffoldError(f"files[{index}].content must be a string")

                relative_path = self._normalize_relative_path(file_spec["path"])
                target = self._safe_target(temp_root, relative_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                self._write_atomic(target, file_spec["content"])

                relative_key = relative_path.as_posix()
                file_paths.append(relative_key)
                sha_map[relative_key] = self._sha256_file(target)

            project_dir = PROJECT_ROOT / normalized_name
            project_dir.parent.mkdir(parents=True, exist_ok=True)
            if project_dir.exists():
                shutil.rmtree(project_dir)
            shutil.copytree(temp_root, project_dir)

            manifest = {
                "name": normalized_name,
                "stack": stack.strip(),
                "files": file_paths,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "sha256_per_file": sha_map,
            }

            manifest_path = project_dir / ".mayday_manifest.json"
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            self._verify_manifest(project_dir, manifest)

            return {
                "status": "success",
                "project_dir": str(project_dir),
                "files_written": file_paths,
            }
        except ScaffoldError:
            raise
        except Exception as exc:
            raise ScaffoldError(str(exc)) from exc
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

    def _normalize_relative_path(self, raw_path: str) -> Path:
        if raw_path.startswith("/") or raw_path.startswith("\\"):
            raise ScaffoldError(f"absolute paths are not allowed: {raw_path}")
        candidate = Path(raw_path)
        if candidate.is_absolute():
            raise ScaffoldError(f"absolute paths are not allowed: {raw_path}")
        if any(part == ".." for part in candidate.parts):
            raise ScaffoldError(f"path traversal is not allowed: {raw_path}")
        return candidate

    def _safe_target(self, root: Path, relative_path: Path) -> Path:
        root_resolved = root.resolve()
        target = (root / relative_path).resolve()
        if root_resolved != target and root_resolved not in target.parents:
            raise ScaffoldError(f"path escapes scaffold root: {relative_path.as_posix()}")
        return target

    def _write_atomic(self, path: Path, content: str) -> None:
        temp_file = path.with_suffix(f"{path.suffix}.tmp")
        temp_file.write_text(content, encoding="utf-8")
        temp_file.replace(path)

    def _verify_manifest(self, project_dir: Path, manifest: dict) -> None:
        for relative_path in manifest["files"]:
            expected = manifest["sha256_per_file"].get(relative_path)
            if not expected:
                raise ScaffoldError(f"manifest missing hash for {relative_path}")
            target = project_dir / relative_path
            if not target.exists():
                raise ScaffoldError(f"missing scaffold file after copy: {relative_path}")
            actual = self._sha256_file(target)
            if actual != expected:
                raise ScaffoldError(f"sha256 mismatch for {relative_path}")

    def _sha256_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8192), b""):
                digest.update(chunk)
        return digest.hexdigest()
