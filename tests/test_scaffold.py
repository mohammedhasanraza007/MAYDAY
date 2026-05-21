from __future__ import annotations

import json
from pathlib import Path

import pytest

import runtime.scaffold_engine as scaffold_module
from core.exceptions import ScaffoldError
from runtime.scaffold_engine import ScaffoldEngine


@pytest.fixture
def isolated_projects_root(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    monkeypatch.setattr(scaffold_module, "PROJECT_ROOT", root)
    return root


def _sample_files():
    return [
        {"path": "app.py", "content": "print('hello')\n"},
        {"path": "templates/index.html", "content": "<h1>ok</h1>\n"},
    ]


def test_writes_files_to_projects_dir(isolated_projects_root):
    engine = ScaffoldEngine()

    result = engine.execute(
        {"project_name": "demo", "stack": "flask", "files": _sample_files()}
    )

    project_dir = isolated_projects_root / "demo"
    assert result["status"] == "success"
    assert result["project_dir"] == str(project_dir)
    assert (project_dir / "app.py").exists()
    assert (project_dir / "templates/index.html").exists()


def test_atomic_rollback_on_error(isolated_projects_root, monkeypatch):
    engine = ScaffoldEngine()
    calls = {"count": 0}
    original = engine._write_atomic

    def fail_on_second_write(path: Path, content: str):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("simulated disk failure")
        original(path, content)

    monkeypatch.setattr(engine, "_write_atomic", fail_on_second_write)

    with pytest.raises(ScaffoldError):
        engine.execute(
            {"project_name": "rollback", "stack": "flask", "files": _sample_files()}
        )

    assert not (isolated_projects_root / "rollback").exists()


def test_path_traversal_rejected(isolated_projects_root):
    engine = ScaffoldEngine()

    with pytest.raises(ScaffoldError):
        engine.execute(
            {
                "project_name": "bad",
                "stack": "flask",
                "files": [{"path": "../etc/passwd", "content": "x"}],
            }
        )


def test_manifest_written(isolated_projects_root):
    engine = ScaffoldEngine()

    result = engine.execute(
        {"project_name": "manifest", "stack": "flask", "files": _sample_files()}
    )

    project_dir = Path(result["project_dir"])
    manifest_path = project_dir / ".mayday_manifest.json"
    assert manifest_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["name"] == "manifest"
    assert manifest["stack"] == "flask"
    assert sorted(manifest["files"]) == ["app.py", "templates/index.html"]
    assert set(manifest["sha256_per_file"]) == set(manifest["files"])


def test_overwrites_existing_project(isolated_projects_root):
    project_dir = isolated_projects_root / "demo"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "old.txt").write_text("old", encoding="utf-8")

    engine = ScaffoldEngine()
    engine.execute(
        {"project_name": "demo", "stack": "flask", "files": _sample_files()}
    )

    assert not (project_dir / "old.txt").exists()
    assert (project_dir / "app.py").exists()


def test_post_write_verification_catches_tamper(isolated_projects_root, monkeypatch):
    engine = ScaffoldEngine()
    original_verify = engine._verify_manifest

    def tampering_verify(project_dir: Path, manifest: dict):
        target = project_dir / manifest["files"][0]
        if target.exists():
            target.unlink()
        original_verify(project_dir, manifest)

    monkeypatch.setattr(engine, "_verify_manifest", tampering_verify)

    with pytest.raises(ScaffoldError):
        engine.execute(
            {"project_name": "tamper", "stack": "flask", "files": _sample_files()}
        )
