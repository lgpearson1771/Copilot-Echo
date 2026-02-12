"""Tests for copilot_echo.config."""

from __future__ import annotations

import os
import textwrap
from unittest.mock import patch

import pytest
import yaml

from copilot_echo.config import (
    AgentConfig,
    AppConfig,
    AutonomousRoutine,
    Config,
    RepoConfig,
    ToolsConfig,
    VoiceConfig,
    _load_agent_config,
    load_config,
)


# ------------------------------------------------------------------
# Dataclass defaults
# ------------------------------------------------------------------

class TestDataclassDefaults:
    def test_app_config_defaults(self):
        cfg = AppConfig()
        assert cfg.name == "Copilot Echo"
        assert cfg.log_level == "INFO"

    def test_voice_config_defaults(self):
        cfg = VoiceConfig()
        assert cfg.sample_rate == 16000
        assert cfg.stt_model == "base"
        assert cfg.stt_device == "cpu"
        assert cfg.stt_compute_type == "int8"
        assert cfg.wakeword_engine == "stt"
        assert cfg.wake_word == "hey jarvis"
        assert cfg.wakeword_models == []
        assert cfg.conversation_window_seconds == 30.0

    def test_agent_config_defaults(self):
        cfg = AgentConfig()
        assert cfg.knowledge_file is None
        assert cfg.projects_dir == "config/projects"
        assert cfg.project_max_chars == 4000
        assert cfg.autonomous_routines == []
        assert cfg.autonomous_max_steps == 10
        assert cfg.autonomous_max_minutes == 10

    def test_autonomous_routine_defaults(self):
        r = AutonomousRoutine()
        assert r.name == ""
        assert r.trigger_phrases == []
        assert r.prompt == ""
        assert r.max_steps is None

    def test_repo_config_defaults(self):
        cfg = RepoConfig()
        assert cfg.default_path is None
        assert cfg.require_confirmation is True

    def test_tools_config_requires_allowlist(self):
        with pytest.raises(TypeError):
            ToolsConfig()  # type: ignore[call-arg]

    def test_tools_config_with_allowlist(self):
        cfg = ToolsConfig(allowlist=["*"])
        assert cfg.allowlist == ["*"]


# ------------------------------------------------------------------
# _load_agent_config
# ------------------------------------------------------------------

class TestLoadAgentConfig:
    def test_with_routines(self):
        data = {
            "autonomous_routines": [
                {
                    "name": "standup",
                    "trigger_phrases": ["daily standup"],
                    "prompt": "Do standup",
                    "max_steps": 3,
                }
            ]
        }
        cfg = _load_agent_config(data)
        assert len(cfg.autonomous_routines) == 1
        assert cfg.autonomous_routines[0].name == "standup"
        assert cfg.autonomous_routines[0].max_steps == 3

    def test_empty_routines(self):
        data = {"autonomous_routines": []}
        cfg = _load_agent_config(data)
        assert cfg.autonomous_routines == []

    def test_no_routines_key(self):
        cfg = _load_agent_config({})
        assert cfg.autonomous_routines == []

    def test_routine_max_steps_none(self):
        data = {
            "autonomous_routines": [
                {"name": "r", "trigger_phrases": [], "prompt": "p"}
            ]
        }
        cfg = _load_agent_config(data)
        assert cfg.autonomous_routines[0].max_steps is None


# ------------------------------------------------------------------
# load_config
# ------------------------------------------------------------------

class TestLoadConfig:
    def test_load_config_from_yaml_data(self):
        """Test that a well-formed YAML dict produces a correct Config."""
        yaml_data = {
            "app": {"name": "TestApp", "log_level": "DEBUG"},
            "voice": {},
            "agent": {},
            "repo": {},
            "tools": {"allowlist": ["*"]},
        }
        cfg = Config(
            app=AppConfig(**yaml_data.get("app", {})),
            voice=VoiceConfig(**yaml_data.get("voice", {})),
            agent=_load_agent_config(yaml_data.get("agent", {})),
            repo=RepoConfig(**yaml_data.get("repo", {})),
            tools=ToolsConfig(**yaml_data.get("tools", {})),
        )
        assert cfg.app.name == "TestApp"
        assert cfg.app.log_level == "DEBUG"
        assert isinstance(cfg.voice, VoiceConfig)
        assert isinstance(cfg.agent, AgentConfig)

    def test_load_config_real_example_yaml(self):
        """Verify the actual example.yaml parses without error."""
        from copilot_echo.paths import project_root
        from pathlib import Path

        root = Path(project_root())
        path = root / "config" / "example.yaml"
        if not path.exists():
            pytest.skip("example.yaml not found")

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        cfg = Config(
            app=AppConfig(**data.get("app", {})),
            voice=VoiceConfig(**data.get("voice", {})),
            agent=_load_agent_config(data.get("agent", {})),
            repo=RepoConfig(**data.get("repo", {})),
            tools=ToolsConfig(**data.get("tools", {})),
        )
        assert isinstance(cfg, Config)
        assert cfg.app.name  # non-empty name
