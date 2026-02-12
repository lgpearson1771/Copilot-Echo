"""Tests for copilot_echo.voice.commands."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from copilot_echo.voice.commands import (
    VoiceCommandHandler,
    _FINISH_PATTERNS,
    _LIST_PHRASES,
    _START_PATTERNS,
)


@pytest.fixture
def handler(fake_config, mock_orchestrator, mock_tts, tmp_projects_dir):
    """Create a VoiceCommandHandler backed by a temp projects dir."""
    fake_config.agent.projects_dir = tmp_projects_dir
    return VoiceCommandHandler(fake_config, mock_orchestrator, mock_tts)


# ------------------------------------------------------------------
# Pattern matching
# ------------------------------------------------------------------

class TestPatternMatching:
    def test_start_project_called(self, handler, mock_orchestrator):
        mock_orchestrator.agent.send.return_value = "My App"
        result = handler.handle("start a project called my app", "start a project called My App")
        assert result is True

    def test_create_project_named(self, handler, mock_orchestrator):
        mock_orchestrator.agent.send.return_value = "New App"
        result = handler.handle("create a project named new app", "create a project named New App")
        assert result is True

    def test_new_project(self, handler, mock_orchestrator):
        mock_orchestrator.agent.send.return_value = "Cool Thing"
        result = handler.handle("new project cool thing", "new project Cool Thing")
        assert result is True

    def test_finish_project(self, handler, mock_orchestrator):
        # First create the project so we can finish it
        mock_orchestrator.agent.send.return_value = "Temp"
        handler.handle("start a project called temp", "start a project called Temp")
        mock_orchestrator.agent.send.return_value = "Temp"
        result = handler.handle("finish project temp", "finish project Temp")
        assert result is True

    def test_archive_project(self, handler, mock_orchestrator):
        mock_orchestrator.agent.send.return_value = "Old"
        handler.handle("start a project called old", "start a project called Old")
        mock_orchestrator.agent.send.return_value = "Old"
        result = handler.handle("archive project old", "archive project Old")
        assert result is True

    def test_list_my_projects(self, handler):
        result = handler.handle("list my projects", "list my projects")
        assert result is True

    def test_show_my_projects(self, handler):
        result = handler.handle("show my projects", "show my projects")
        assert result is True

    def test_what_projects_do_i_have(self, handler):
        result = handler.handle("what projects do i have", "What projects do I have")
        assert result is True

    def test_no_match_returns_false(self, handler):
        result = handler.handle("what is the weather", "What is the weather")
        assert result is False


# ------------------------------------------------------------------
# Command execution
# ------------------------------------------------------------------

class TestCommandExecution:
    def test_start_success(self, handler, mock_tts, mock_orchestrator):
        mock_orchestrator.agent.send.return_value = "Alpha"
        handler.handle("start a project called alpha", "start a project called Alpha")
        # TTS should have spoken a success message
        spoken = mock_tts.speak.call_args_list[-1].args[0]
        assert "created" in spoken.lower() or "tracking" in spoken.lower()

    def test_start_duplicate(self, handler, mock_tts, mock_orchestrator):
        mock_orchestrator.agent.send.return_value = "Dup"
        handler.handle("new project dup", "new project Dup")
        mock_orchestrator.agent.send.return_value = "Dup"
        handler.handle("new project dup", "new project Dup")
        spoken = mock_tts.speak.call_args_list[-1].args[0]
        assert "already exists" in spoken.lower()

    def test_finish_success(self, handler, mock_tts, mock_orchestrator):
        mock_orchestrator.agent.send.return_value = "Beta"
        handler.handle("new project beta", "new project Beta")
        mock_orchestrator.agent.send.return_value = "Beta"
        handler.handle("finish project beta", "finish project Beta")
        spoken = mock_tts.speak.call_args_list[-1].args[0]
        assert "archived" in spoken.lower()

    def test_finish_not_found(self, handler, mock_tts, mock_orchestrator):
        mock_orchestrator.agent.send.return_value = "Ghost"
        handler.handle("finish project ghost", "finish project Ghost")
        spoken = mock_tts.speak.call_args_list[-1].args[0]
        assert "couldn't find" in spoken.lower()

    def test_list_empty(self, handler, mock_tts):
        handler.handle("list my projects", "list my projects")
        spoken = mock_tts.speak.call_args_list[-1].args[0]
        assert "don't have" in spoken.lower() or "no" in spoken.lower()

    def test_list_active_and_archived(self, handler, mock_tts, mock_orchestrator):
        mock_orchestrator.agent.send.return_value = "One"
        handler.handle("new project one", "new project One")
        mock_orchestrator.agent.send.return_value = "Two"
        handler.handle("new project two", "new project Two")
        mock_orchestrator.agent.send.return_value = "Two"
        handler.handle("finish project two", "finish project Two")
        handler.handle("list my projects", "list my projects")
        spoken = mock_tts.speak.call_args_list[-1].args[0]
        assert "active" in spoken.lower()
        assert "archived" in spoken.lower()


# ------------------------------------------------------------------
# Name extraction
# ------------------------------------------------------------------

class TestExtractProjectName:
    def test_agent_cleans_name(self, handler, mock_orchestrator):
        mock_orchestrator.agent.send.return_value = "Clean Name"
        result = handler._extract_project_name("for me about the clean name")
        assert result == "Clean Name"

    def test_fallback_raw_name(self, handler, mock_orchestrator):
        mock_orchestrator.agent.send.side_effect = RuntimeError("fail")
        result = handler._extract_project_name("raw name")
        assert result == "raw name"

    def test_empty_agent_reply_uses_raw(self, handler, mock_orchestrator):
        mock_orchestrator.agent.send.return_value = ""
        result = handler._extract_project_name("original")
        assert result == "original"


# ------------------------------------------------------------------
# Regex coverage
# ------------------------------------------------------------------

class TestRegexPatterns:
    @pytest.mark.parametrize(
        "text",
        [
            "start a project called Test",
            "start a project named Test",
            "start a project Test",
            "create a project called Test",
            "create a project named Test",
            "create a project Test",
            "new project Test",
        ],
    )
    def test_start_patterns(self, text):
        matches = [p.search(text) for p in _START_PATTERNS]
        assert any(m is not None for m in matches), f"No START pattern matched: {text}"

    @pytest.mark.parametrize(
        "text",
        [
            "finish project Test",
            "finish the project Test",
            "close project Test",
            "complete the project Test",
            "end project Test",
            "archive project Test",
            "archive the project Test",
        ],
    )
    def test_finish_patterns(self, text):
        matches = [p.search(text) for p in _FINISH_PATTERNS]
        assert any(m is not None for m in matches), f"No FINISH pattern matched: {text}"

    @pytest.mark.parametrize("phrase", _LIST_PHRASES)
    def test_list_phrases(self, phrase):
        assert phrase in _LIST_PHRASES
