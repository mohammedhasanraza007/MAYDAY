"""
M.A.Y.D.A.Y Integration Test — Smoke Test
"""
import unittest
from core.exceptions import *
from ui.theme import THEME
from mayday_runtime.engine import ExecutionEngine
from core.session import SessionManager
from core.json_parser import parse_model_output

class TestMaydayFoundation(unittest.TestCase):
    def test_exceptions(self):
        with self.assertRaises(HardRuleViolationError):
            raise HardRuleViolationError("Test")
            
    def test_theme(self):
        self.assertEqual(THEME.BG, "#000000")
        
    def test_engine_registration(self):
        engine = ExecutionEngine()
        class MockTool:
            def execute(self, params): return {"ok": True}
        engine.register_tool("mock", MockTool())
        self.assertIn("mock", engine.get_registered_tools())
        
    def test_json_parsing(self):
        raw = '```json\n{"action": "respond", "response": "hello"}\n```'
        parsed = parse_model_output(raw)
        self.assertEqual(parsed['action'], 'respond')
        self.assertEqual(parsed['response'], 'hello')

    def test_session_limit(self):
        session = SessionManager()
        for _ in range(session.max_steps): session.increment_step()
        with self.assertRaises(SessionLimitError):
            session.increment_step()

if __name__ == '__main__':
    unittest.main()
