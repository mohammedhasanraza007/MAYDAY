from __future__ import annotations

import json

import pytest

from core.intent_router import classify
from core.json_parser import parse_model_output
from core.orchestrator import ChatOnlyOutputError, Orchestrator
from runtime.engine import ExecutionEngine
from tools.file_tools import FileTools


class RespondOnlyRouter:
    def route(self, _messages):
        return json.dumps({"action": "respond", "text": "cannot do that"}), "mock"


class ToolCallRouter:
    def route(self, _messages):
        return json.dumps(
            {
                "action": "tool_call",
                "tool_name": "scaffold_engine",
                "parameters": {
                    "project_name": "x",
                    "stack": "flask",
                    "files": [{"path": "app.py", "content": "print('x')"}],
                },
            }
        ), "mock"


def test_classify_make_app_returns_project_creation():
    assert classify("please make app for invoices") == "PROJECT_CREATION"


def test_classify_run_returns_execution():
    assert classify("run the server now") == "EXECUTION"


def test_classify_book_meeting_returns_automation():
    assert classify("book meeting for tomorrow") == "AUTOMATION"


def test_classify_refactor_returns_file_ops():
    assert classify("refactor this module") == "FILE_OPS"


def test_classify_create_file_returns_file_ops():
    assert classify("create file notes.txt with text hi") == "FILE_OPS"


def test_classify_search_returns_web_access():
    assert classify("Search for Python official website") == "WEB_ACCESS"


def test_classify_fetch_title_returns_web_access():
    assert classify("Fetch the title of https://www.python.org") == "WEB_ACCESS"


def test_classify_build_flask_app_semantic_fallback():
    assert classify("build flask app") == "PROJECT_CREATION"


def test_classify_fix_bug_semantic_fallback():
    assert classify("fix bug in code") == "FILE_OPS"


def test_classify_noun_only_input_returns_none():
    assert classify("{broken json") is None


def test_parser_wraps_plain_text_in_safe_response():
    parsed = parse_model_output("hello there")
    assert parsed["action"] == "respond"
    assert parsed["text"] == "hello there"


def test_parser_recovers_non_contract_json_without_crash():
    parsed = parse_model_output("{\"valid\": true}")
    assert parsed["action"] == "respond"
    assert "valid" in parsed["text"]


def test_parser_repairs_python_style_object():
    parsed = parse_model_output("{'action': 'respond', 'text': 'ok',}")
    assert parsed["action"] == "respond"
    assert parsed["text"] == "ok"


def test_parser_repairs_single_tool_disguised_as_multi_tool():
    parsed = parse_model_output(
        "```json\n"
        "{"
        "\"action\":\"multi_tool_call\","
        "\"tool_name\":\"file_system_tools\","
        "\"parameters\":{\"files\":[{\"path\":\"hello.txt\",\"content\":\"hi\"}]}"
        "}\n"
        "```"
    )
    assert parsed["action"] == "tool_call"
    assert parsed["tool_name"] == "file_write"
    assert parsed["parameters"] == {"path": "hello.txt", "content": "hi"}


def test_executable_intent_blocks_immediate_respond():
    orchestrator = Orchestrator(RespondOnlyRouter(), ExecutionEngine())
    with pytest.raises(ChatOnlyOutputError):
        orchestrator.run("build me a flask app")


def test_simple_file_prompt_recovers_to_real_tool_execution(tmp_path):
    target = tmp_path / "hello.txt"
    engine = ExecutionEngine()
    engine.register_tools({"file": FileTools()})
    engine.gateway.allowed_root = tmp_path.resolve()
    engine.gateway.hard_block_paths = []
    engine.gateway.session_allow_always = True
    orchestrator = Orchestrator(RespondOnlyRouter(), engine)

    response = orchestrator.run(f"Create file {target} with text hello")

    assert target.read_text(encoding="utf-8") == "hello"
    assert "file_write executed" in response


def test_chat_intent_blocks_tool_execution_path():
    orchestrator = Orchestrator(ToolCallRouter(), ExecutionEngine())
    response = orchestrator.run("hi")
    assert "blocked" in response.lower()
