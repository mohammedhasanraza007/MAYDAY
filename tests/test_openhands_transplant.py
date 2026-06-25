from __future__ import annotations

import importlib
import os
import sys
import threading
from pathlib import Path

import pytest


def test_permission_gate_cancel_state_is_threading_event():
    from runtime.permission_gate import permission_gate

    assert isinstance(permission_gate._cancelled, threading.Event)
    permission_gate._cancelled.set()
    permission_gate.reset()
    assert not permission_gate._cancelled.is_set()


def test_memory_context_compressor_pins_entries_at_front():
    from memory.context_compressor import ContextCompressor

    compressor = ContextCompressor(max_tokens=5)
    long_pinned = "PINNED " + "important " * 40
    output = compressor.compress(
        [
            {"role": "user", "content": "older unpinned text"},
            {"role": "tool", "content": long_pinned, "pinned": True},
            {"role": "assistant", "content": "recent"},
        ]
    )

    assert output.startswith(long_pinned)
    assert "[...]" not in output.splitlines()[0]


def test_scaffold_temp_staging_uses_projects_parent(monkeypatch, tmp_path):
    import runtime.scaffold_engine as scaffold_module
    from runtime.scaffold_engine import ScaffoldEngine

    monkeypatch.setattr(scaffold_module, "PROJECT_ROOT", tmp_path / "projects")
    observed: dict[str, str | None] = {}

    def fake_mkdtemp(prefix: str, dir: str | Path | None = None) -> str:
        observed["prefix"] = prefix
        observed["dir"] = str(dir) if dir is not None else None
        target = tmp_path / "staging"
        target.mkdir()
        return str(target)

    monkeypatch.setattr(scaffold_module.tempfile, "mkdtemp", fake_mkdtemp)
    ScaffoldEngine().execute(
        {
            "project_name": "demo_api",
            "stack": "flask",
            "files": [{"path": "app.py", "content": "print('hello')\n"}],
        }
    )

    assert observed == {"prefix": "mayday_scaffold_", "dir": str(tmp_path)}


def test_new_transplant_modules_import_and_basic_behaviors(tmp_path):
    from core.event_stream import AgentAction, AgentObservation, EventStream
    from core.skill_loader import skill_loader
    from memory.condenser import FailureMemory, HierarchicalCondenser
    from tools.patch_tools import PatchTools
    from tools.test_runner import TestRunnerTool

    seen = []
    stream = EventStream()
    stream.subscribe(seen.append)
    stream.emit(AgentAction(type="tool_call", tool="file_write", parameters={"path": "x"}))
    stream.emit(AgentObservation(action_id="abc123", status="success", result={"status": "success"}, pinned=True))
    assert len(stream.get_history()) == 2
    assert len(seen) == 2

    condenser = HierarchicalCondenser(max_tokens=10)
    compressed = condenser.compress([{"role": "tool", "content": "keep", "pinned": True}] * 30)
    assert compressed
    assert all(entry.get("pinned") for entry in compressed if entry.get("role") == "tool")

    failures = FailureMemory()
    assert not failures.should_skip("file_write", {"path": "missing"})
    failures.record("file_write", {"path": "missing"})
    failures.record("file_write", {"path": "missing"})
    assert failures.should_skip("file_write", {"path": "missing"})

    n = skill_loader.load()
    assert n >= 4

    source = tmp_path / "sample.py"
    source.write_text("def target():\n    return 'old'\n\ndef keep():\n    return 'same'\n", encoding="utf-8")
    result = PatchTools().execute(
        {
            "_tool_name": "file_replace_block",
            "path": str(source),
            "block_name": "target",
            "new_content": "def target():\n    return 'new'",
        }
    )
    assert result["status"] == "ok"
    text = source.read_text(encoding="utf-8")
    assert "return 'new'" in text
    assert "def keep" in text

    assert "run_tests" in TestRunnerTool().get_capabilities()


def test_gpu_offload_config_always_returns_backend_key():
    from core.gpu_detector import get_ml_offload_config

    config = get_ml_offload_config()
    assert "backend" in config
    assert "n_gpu_layers" in config


def test_mcp_server_exports_registration_api():
    server = importlib.import_module("mcp.server")

    assert hasattr(server, "start_mcp_server")
    assert hasattr(server, "register_tool")


def test_validation_prompt_recovery_for_write_to_file_and_scaffold():
    from core.tool_recovery import recover_action_from_prompt

    file_action = recover_action_from_prompt(
        "write hello to test_output.txt",
        {"family": "FILE_OPS"},
        {},
    )
    assert file_action["tool_name"] == "file_write"
    assert file_action["parameters"]["path"] == "test_output.txt"
    assert file_action["parameters"]["content"] == "hello"
    assert file_action["parameters"]["minimum_chars"] == 1

    scaffold_action = recover_action_from_prompt(
        "scaffold a flask app called demo_api",
        {"family": "PROJECT_CREATION"},
        {},
    )
    assert scaffold_action["tool_name"] == "scaffold"
    assert scaffold_action["parameters"]["project_name"] == "demo_api"
    paths = {item["path"] for item in scaffold_action["parameters"]["files"]}
    assert {"app.py", "requirements.txt", "README.md"} <= paths


def test_loop_guard_signature_uses_full_parameters_json():
    from core.orchestrator import Orchestrator

    orchestrator = Orchestrator(router=None, engine=None)
    prefix = "x" * 120
    first = orchestrator._tool_call_signature(
        "browser_type",
        {"selector": "search", "text": prefix + "first"},
    )
    second = orchestrator._tool_call_signature(
        "browser_type",
        {"selector": "search", "text": prefix + "second"},
    )

    assert first != second


def test_process_sandbox_run_isolated_returns_stdout():
    from runtime.sandbox import ProcessSandbox

    sandbox = ProcessSandbox(enabled=True)

    assert sandbox.run_isolated("print(42)") == "42\n"


def test_repo_indexer_extracts_symbols_imports_summary_and_cache(tmp_path):
    from coding.repo_indexer import RepoIndexer

    sample = tmp_path / "pkg" / "sample.py"
    sample.parent.mkdir()
    sample.write_text(
        "import os\nfrom pathlib import Path\n\nclass Demo:\n    pass\n\ndef run():\n    return Path(os.getcwd())\n",
        encoding="utf-8",
    )

    indexer = RepoIndexer(tmp_path)
    first = indexer.build_index()
    second = indexer.build_index()

    assert "pkg/sample.py" in first["file_tree"]
    assert first["symbols"]["pkg/sample.py"] == ["Demo", "run"]
    assert first["imports"]["pkg/sample.py"] == ["os", "pathlib.Path"]
    assert "1 python files" in first["summary"]
    assert second == first


def test_voice_input_imports_without_optional_audio_dependencies():
    from audio.voice_input import VoiceInput

    voice = VoiceInput()

    assert hasattr(voice, "listen")
    assert hasattr(voice, "is_available")
    assert isinstance(voice.is_available(), bool)


def test_main_window_renders_requested_tabs_without_lora():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication, QTabWidget, QTreeView
    from ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()

    tabs = window.findChild(QTabWidget)
    tree = window.findChild(QTreeView)
    tab_names = [tabs.tabText(index) for index in range(tabs.count())]

    assert tree is not None
    assert tabs is not None
    assert tab_names == [
        "Chat",
        "AgentStream",
        "Terminal",
        "Files",
        "Models",
        "API",
        "Skills",
        "Logs",
        "Dashboard",
    ]
    assert not any("lora" in name.lower() for name in tab_names)
    window.close()
    app.processEvents()
