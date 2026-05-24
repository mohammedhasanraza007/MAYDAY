from __future__ import annotations

import pytest

from runtime.action_schema import validate_action


def test_file_write_accepts_blank_xlsx_template():
    valid, reason = validate_action("file_write", {"path": "EmployeeAttendanceTest.xlsx", "template": "blank_xlsx"})
    assert valid, reason


def test_file_write_rejects_missing_content_without_template():
    valid, reason = validate_action("file_write", {"path": "notes.txt"})
    assert not valid
    assert "content" in reason


def test_file_write_rejects_unknown_template():
    valid, reason = validate_action("file_write", {"path": "notes.txt", "template": "made_up"})
    assert not valid
    assert "template" in reason


def test_action_grammar_loads():
    pytest.importorskip("llama_cpp")
    from model.loader import ModelLoader

    loader = ModelLoader()
    assert loader._grammar is not None


def test_tier_gpu_layer_policy():
    from model.loader import gpu_layers_for_tier

    assert gpu_layers_for_tier({"tier": 1}, "tier1.gguf", "DIRECTML") == 0
    assert gpu_layers_for_tier({"tier": 2}, "tier2.gguf", "DIRECTML") == 36
    assert gpu_layers_for_tier({"tier": 3}, "tier3.gguf", "DIRECTML") == 36
