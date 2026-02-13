"""Shared test fixtures for the Copilot Echo test suite."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from copilot_echo.config import (
    AgentConfig,
    AppConfig,
    AutonomousRoutine,
    Config,
    RepoConfig,
    ToolsConfig,
    VoiceConfig,
)


# ------------------------------------------------------------------
# Config fixture
# ------------------------------------------------------------------

@pytest.fixture
def fake_config() -> Config:
    """Return a Config object with sensible test defaults."""
    return Config(
        app=AppConfig(name="Test Echo", log_level="DEBUG"),
        voice=VoiceConfig(
            wakeword_engine="stt",
            wake_word="hey echo",
            sample_rate=16000,
            wake_listen_seconds=1.0,
            command_listen_seconds=2.0,
            utterance_end_seconds=0.5,
            max_listen_seconds=10.0,
            stt_energy_threshold=0.01,
            post_tts_cooldown_seconds=0.0,
            conversation_window_seconds=5.0,
            stt_model="tiny",
            stt_device="cpu",
            stt_compute_type="int8",
        ),
        agent=AgentConfig(
            knowledge_file=None,
            projects_dir="config/projects",
            project_max_chars=4000,
            autonomous_routines=[
                AutonomousRoutine(
                    name="Daily Standup",
                    trigger_phrases=["daily standup", "standup prep"],
                    prompt="Prepare daily standup summary",
                    max_steps=5,
                ),
            ],
            autonomous_max_steps=10,
            autonomous_max_minutes=10,
        ),
        repo=RepoConfig(default_path=None, require_confirmation=True),
        tools=ToolsConfig(allowlist=["*"]),
    )


# ------------------------------------------------------------------
# Projects directory fixture
# ------------------------------------------------------------------

@pytest.fixture
def tmp_projects_dir(tmp_path):
    """Create active/ and archive/ subdirs in a temp directory."""
    active = tmp_path / "active"
    archive = tmp_path / "archive"
    active.mkdir()
    archive.mkdir()
    return str(tmp_path)


@pytest.fixture
def sample_project(tmp_projects_dir):
    """Create a sample active project file and return its name."""
    name = "Test Project"
    slug = "test-project"
    content = (
        "# Project: Test Project\n\n"
        "**Created:** 2026-02-11\n"
        "**Status:** Active\n"
        "**Goal:** Test goal\n\n"
        "## Repos & Work Items\n"
        "- Primary repo: test-repo\n\n"
        "## Key Decisions\n"
        "<!-- Agent appends decisions -->\n\n"
        "## Progress Log\n"
        "<!-- Agent appends progress -->\n\n"
        "## Blockers & Issues\n"
        "<!-- Agent notes blockers -->\n\n"
        "## Lessons Learned\n"
        "<!-- Insights -->\n"
    )
    path = os.path.join(tmp_projects_dir, "active", f"{slug}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return name


# ------------------------------------------------------------------
# Orchestrator fixture (with mocked Agent)
# ------------------------------------------------------------------

@pytest.fixture
def mock_orchestrator(fake_config):
    """Return an Orchestrator whose Agent is fully mocked."""
    with patch("copilot_echo.orchestrator.Agent") as MockAgent:
        mock_agent = MagicMock()
        mock_agent.send.return_value = "Mock agent reply"
        mock_agent.start.return_value = None
        mock_agent.stop.return_value = None
        mock_agent.cancel.return_value = None
        MockAgent.return_value = mock_agent

        from copilot_echo.orchestrator import Orchestrator

        orch = Orchestrator(fake_config)
        yield orch
