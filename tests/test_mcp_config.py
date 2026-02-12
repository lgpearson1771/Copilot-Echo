"""Tests for copilot_echo.mcp_config."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

import pytest

from copilot_echo.mcp_config import (
    _merge_stdio_env,
    _sanitize_servers,
    build_project_mcp_server,
    load_global_mcp_servers,
)


# ------------------------------------------------------------------
# load_global_mcp_servers
# ------------------------------------------------------------------

class TestLoadGlobalMcpServers:
    def test_missing_config_file(self, tmp_path):
        fake_path = str(tmp_path / "nonexistent" / "config.json")
        with patch("copilot_echo.mcp_config.os.path.expanduser", return_value=fake_path):
            result = load_global_mcp_servers()
        assert result == {}

    def test_invalid_json(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("NOT VALID JSON {{{", encoding="utf-8")
        with patch(
            "copilot_echo.mcp_config.os.path.expanduser",
            return_value=str(config_file),
        ):
            result = load_global_mcp_servers()
        assert result == {}

    def test_empty_servers(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"mcp_servers": {}}), encoding="utf-8")
        with patch(
            "copilot_echo.mcp_config.os.path.expanduser",
            return_value=str(config_file),
        ):
            result = load_global_mcp_servers()
        assert result == {}

    def test_valid_servers(self, tmp_path):
        servers = {
            "test_server": {
                "type": "stdio",
                "command": "node",
                "args": ["server.js"],
            }
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"mcp_servers": servers}), encoding="utf-8"
        )
        with patch(
            "copilot_echo.mcp_config.os.path.expanduser",
            return_value=str(config_file),
        ):
            result = load_global_mcp_servers()
        assert "test_server" in result
        assert result["test_server"]["tools"] == ["*"]


# ------------------------------------------------------------------
# _sanitize_servers
# ------------------------------------------------------------------

class TestSanitizeServers:
    def test_spaces_in_name(self):
        servers = {"My Server": {"type": "stdio", "command": "node"}}
        result = _sanitize_servers(servers)
        assert "My_Server" in result
        assert "My Server" not in result

    def test_adds_default_tools(self):
        servers = {"s": {"type": "stdio", "command": "node"}}
        result = _sanitize_servers(servers)
        assert result["s"]["tools"] == ["*"]

    def test_preserves_existing_tools(self):
        servers = {"s": {"type": "stdio", "command": "node", "tools": ["tool_a"]}}
        result = _sanitize_servers(servers)
        assert result["s"]["tools"] == ["tool_a"]

    def test_adds_default_timeout(self):
        servers = {"s": {"type": "stdio", "command": "node"}}
        result = _sanitize_servers(servers)
        assert result["s"]["timeout"] == 60_000

    def test_preserves_existing_timeout(self):
        servers = {"s": {"type": "stdio", "command": "node", "timeout": 5000}}
        result = _sanitize_servers(servers)
        assert result["s"]["timeout"] == 5000


# ------------------------------------------------------------------
# _merge_stdio_env
# ------------------------------------------------------------------

class TestMergeStdioEnv:
    def test_merges_parent_env(self):
        srv = {"command": "node", "args": []}
        with patch.dict(os.environ, {"TEST_VAR": "hello"}, clear=False):
            _merge_stdio_env(srv, "test")
        assert srv["env"]["TEST_VAR"] == "hello"

    def test_server_env_overrides_parent(self):
        srv = {"command": "node", "args": [], "env": {"PATH": "/custom"}}
        _merge_stdio_env(srv, "test")
        assert srv["env"]["PATH"] == "/custom"

    def test_node_cwd_auto_detection(self, tmp_path):
        # Create a node_modules dir to trigger cwd detection
        node_modules = tmp_path / "node_modules"
        node_modules.mkdir()
        script = str(tmp_path / "index.js")
        srv = {"command": "node", "args": [script]}
        _merge_stdio_env(srv, "test")
        assert "cwd" in srv
        assert srv["cwd"] == str(tmp_path)


# ------------------------------------------------------------------
# build_project_mcp_server
# ------------------------------------------------------------------

class TestBuildProjectMcpServer:
    def test_returns_server_entry(self, fake_config):
        result = build_project_mcp_server(fake_config)
        assert "copilot_echo_projects" in result
        srv = result["copilot_echo_projects"]
        assert srv["type"] == "stdio"
        assert srv["command"] == sys.executable
        assert "-m" in srv["args"]
        assert "copilot_echo.project_mcp" in srv["args"]

    def test_env_includes_projects_dir(self, fake_config):
        result = build_project_mcp_server(fake_config)
        srv = result["copilot_echo_projects"]
        assert srv["env"]["COPILOT_ECHO_PROJECTS_DIR"] == fake_config.agent.projects_dir
        assert srv["env"]["COPILOT_ECHO_PROJECT_MAX_CHARS"] == str(
            fake_config.agent.project_max_chars
        )
