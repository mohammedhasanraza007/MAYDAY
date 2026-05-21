"""
Phase 6B — Goal-Oriented Automation Interceptor Tests
=====================================================
Validates intent classification and tool recovery for:
  1. Open WhatsApp (desktop or web fallback)
  2. Play song (YouTube search + click first video)
  3. Open/Read file (file_read routing)
  4. Create new file (file_write routing)
  5. Julia's AI search (web_search routing)
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

# Ensure MAYDAY root is on sys.path
MAYDAY_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MAYDAY_ROOT))

from core.intent_router import classify, is_executable_intent
from core.tool_recovery import recover_action_from_prompt


# ─── Helper ──────────────────────────────────────────────────────────────────

def _recover(prompt: str, family: str = ""):
    """Shortcut: call recover_action_from_prompt with a minimal intent/action."""
    intent = {"family": family or (classify(prompt) or "CHAT"), "executable": True}
    parsed_action = {"action": "respond", "text": "I am responding"}
    return recover_action_from_prompt(prompt, intent, parsed_action)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Intent Classification Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntentClassification:

    def test_open_whatsapp_is_automation(self):
        assert classify("open whatsapp") == "AUTOMATION"

    def test_whats_app_is_automation(self):
        assert classify("open whats app") == "AUTOMATION"

    def test_play_english_song_is_automation(self):
        assert classify("play english song") == "AUTOMATION"

    def test_play_tamil_song_is_automation(self):
        assert classify("play a tamil song") == "AUTOMATION"

    def test_julias_ai_is_web_access(self):
        assert classify("find julias ai by google") == "WEB_ACCESS"

    def test_julias_ai_apostrophe_is_web_access(self):
        assert classify("search for julia's ai") == "WEB_ACCESS"

    def test_read_file_is_file_ops(self):
        assert classify("open file main.py and read it") == "FILE_OPS"

    def test_make_new_file_is_file_ops(self):
        assert classify("make a new file named test.txt") == "FILE_OPS"

    def test_all_new_prompts_are_executable(self):
        prompts = [
            "open whatsapp",
            "play english song",
            "find julias ai by google",
            "open this file main.py read it",
            "make a new file name it test.txt",
        ]
        for p in prompts:
            assert is_executable_intent(p), f"Expected executable: {p!r}"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. WhatsApp Recovery Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestWhatsAppRecovery:

    def test_whatsapp_desktop_when_registry_exists(self):
        """If the registry key exists, should return shell_run to launch desktop app."""
        import unittest.mock as um

        fake_key = um.MagicMock()
        with patch("winreg.OpenKey", return_value=fake_key) as mock_open, \
             patch("winreg.CloseKey") as mock_close:
            result = _recover("open whatsapp")
            assert result is not None
            assert result["action"] == "tool_call"
            assert result["tool_name"] == "shell_run"
            assert "whatsapp:" in result["parameters"]["command"]
            mock_open.assert_called_once()
            mock_close.assert_called_once()

    def test_whatsapp_web_fallback_when_no_registry(self):
        """If the registry key doesn't exist, should return browser_open to WhatsApp Web."""
        with patch("winreg.OpenKey", side_effect=FileNotFoundError):
            result = _recover("open whatsapp")
            assert result is not None
            assert result["action"] == "tool_call"
            assert result["tool_name"] == "browser_open"
            assert result["parameters"]["url"] == "https://web.whatsapp.com"

    def test_whats_app_variant(self):
        """'whats app' (space-separated) should also trigger."""
        with patch("winreg.OpenKey", side_effect=OSError):
            result = _recover("open whats app")
            assert result is not None
            assert result["tool_name"] == "browser_open"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. YouTube Song Recovery Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestYouTubeSongRecovery:

    def test_play_english_song(self):
        result = _recover("play english song")
        assert result is not None
        assert result["action"] == "multi_tool_call"
        tools = result["tools"]
        assert len(tools) == 2
        assert tools[0]["tool_name"] == "browser_open"
        assert "youtube.com/results" in tools[0]["parameters"]["url"]
        assert "english" in tools[0]["parameters"]["url"]
        assert tools[1]["tool_name"] == "browser_click"
        assert "video-title" in tools[1]["parameters"]["selector"]

    def test_play_tamil_song(self):
        result = _recover("play a tamil song")
        assert result is not None
        assert "tamil" in result["tools"][0]["parameters"]["url"]

    def test_play_custom_song(self):
        result = _recover("play Shape of You by Ed Sheeran")
        assert result is not None
        url = result["tools"][0]["parameters"]["url"]
        assert "Shape" in url or "shape" in url.lower()

    def test_play_does_not_intercept_games(self):
        """'play flappy bird game' should NOT trigger song recovery."""
        result = _recover("play flappy bird game")
        # Should be None (NO_ACTION) from _recover_youtube_song_flow
        # because "game" and "flappy" keywords are excluded.
        # It will match other handlers instead.
        if result is not None:
            assert result.get("_recovery_source") != "prompt_youtube_song_play"

    def test_play_default_query(self):
        """'play' alone should default to 'english song' query."""
        result = _recover("play")
        assert result is not None
        assert "english" in result["tools"][0]["parameters"]["url"].lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Julia's AI Recovery Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestJuliasAIRecovery:

    def test_julias_ai_search(self):
        result = _recover("find julias ai by google")
        assert result is not None
        assert result["action"] == "tool_call"
        assert result["tool_name"] == "web_search"
        assert "Julias AI by Google" in result["parameters"]["query"]

    def test_julias_ai_apostrophe(self):
        result = _recover("what is julia's ai")
        assert result is not None
        assert result["tool_name"] == "web_search"

    def test_julia_ai_variant(self):
        result = _recover("search for julia ai made by google")
        assert result is not None
        assert result["tool_name"] == "web_search"

    def test_julia_without_ai_does_not_trigger(self):
        """Plain 'julia' without 'ai' context should NOT trigger this handler."""
        result = _recover("who is julia roberts")
        if result is not None:
            assert result.get("_recovery_source") != "prompt_julias_ai_search"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. File Read Recovery Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestFileReadRecovery:

    def test_read_file_with_path(self):
        result = _recover("open file E:\\MAYDAY\\main.py and read it")
        assert result is not None
        assert result["action"] == "tool_call"
        assert result["tool_name"] == "file_read"
        assert "main.py" in result["parameters"]["path"]

    def test_read_file_with_filename(self):
        result = _recover("read file config.json")
        assert result is not None
        assert result["tool_name"] == "file_read"
        assert result["parameters"]["path"] == "config.json"

    def test_open_this_file(self):
        result = _recover("open this file test.txt")
        assert result is not None
        assert result["tool_name"] == "file_read"

    def test_read_it_with_filename(self):
        result = _recover("open main.py read it")
        assert result is not None
        assert result["tool_name"] == "file_read"
        assert "main.py" in result["parameters"]["path"]


# ═══════════════════════════════════════════════════════════════════════════════
# 6. New File Creation Recovery Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestNewFileCreationRecovery:

    def test_make_new_file_name_it(self):
        result = _recover("make a new file name it test.txt")
        assert result is not None
        assert result["action"] == "tool_call"
        assert result["tool_name"] == "file_write"
        assert "test.txt" in result["parameters"]["path"]

    def test_create_file_called(self):
        result = _recover("create a file called notes.md")
        assert result is not None
        assert result["tool_name"] == "file_write"
        assert "notes.md" in result["parameters"]["path"]

    def test_make_file_with_content(self):
        result = _recover("make a new file name it hello.txt with content Hello World")
        assert result is not None
        assert result["tool_name"] == "file_write"
        assert "hello.txt" in result["parameters"]["path"]
        assert "Hello World" in result["parameters"]["content"]

    def test_existing_file_write_pattern_not_intercepted(self):
        """Prompts matching the existing FILE_WRITE_PATTERN should NOT be
        intercepted by _recover_new_file_creation (let _recover_file_write handle it)."""
        result = _recover("create file output.txt with text some data")
        # This should be handled by the existing _recover_file_write, not our new handler
        if result is not None:
            assert result.get("_recovery_source") != "prompt_new_file_creation"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Finalization Flag Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestFinalizationFlags:
    """All recovery actions must set _finalize_after_tool=True so the
    orchestrator returns tool evidence instead of looping."""

    def test_whatsapp_finalize(self):
        with patch("winreg.OpenKey", side_effect=OSError):
            result = _recover("open whatsapp")
        assert result is not None
        assert result.get("_finalize_after_tool") is True

    def test_youtube_finalize(self):
        result = _recover("play english song")
        assert result is not None
        assert result.get("_finalize_after_tool") is True

    def test_julias_ai_finalize(self):
        result = _recover("find julias ai")
        assert result is not None
        assert result.get("_finalize_after_tool") is True

    def test_file_read_finalize(self):
        result = _recover("read file main.py")
        assert result is not None
        assert result.get("_finalize_after_tool") is True

    def test_new_file_finalize(self):
        result = _recover("make a new file name it test.txt")
        assert result is not None
        assert result.get("_finalize_after_tool") is True
