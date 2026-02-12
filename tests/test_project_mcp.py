"""Tests for copilot_echo.project_mcp — MCP tool wrappers."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


def _patch_root(tmp_path):
    return patch("copilot_echo.projects._resolve_root", return_value=str(tmp_path))


class TestProjectMcpTools:
    """Test the MCP tool functions with filesystem fixtures."""

    @pytest.fixture(autouse=True)
    def _setup_env(self, tmp_path, monkeypatch):
        """Point the MCP module at a temp projects dir."""
        projects_dir = str(tmp_path / "config" / "projects")
        monkeypatch.setenv("COPILOT_ECHO_PROJECTS_DIR", projects_dir)
        monkeypatch.setenv("COPILOT_ECHO_PROJECT_MAX_CHARS", "4000")
        self.tmp_path = tmp_path
        self.projects_dir = projects_dir

        # Re-import to pick up env vars
        import copilot_echo.project_mcp as pm

        monkeypatch.setattr(pm, "_PROJECTS_DIR", projects_dir)
        monkeypatch.setattr(pm, "_MAX_CHARS", 4000)
        self.pm = pm

    def test_list_all_projects_empty(self):
        with _patch_root(self.tmp_path):
            result = self.pm.list_all_projects()
        assert "No active" in result
        assert "No archived" in result

    def test_list_all_projects_with_data(self):
        from copilot_echo.projects import create_project

        with _patch_root(self.tmp_path):
            create_project("Demo", self.projects_dir)
            result = self.pm.list_all_projects()
        assert "Demo" in result
        assert "Active" in result

    def test_get_archived_project_not_found(self):
        with _patch_root(self.tmp_path):
            result = self.pm.get_archived_project("Nothing")
        assert "not found" in result.lower() or "No archived" in result

    def test_get_active_project_not_found(self):
        with _patch_root(self.tmp_path):
            result = self.pm.get_active_project("Nothing")
        assert "not found" in result.lower() or "No active" in result

    def test_get_active_project_success(self):
        from copilot_echo.projects import create_project

        with _patch_root(self.tmp_path):
            create_project("Active", self.projects_dir)
            result = self.pm.get_active_project("Active")
        assert "Active" in result

    def test_append_project_entry_success(self):
        from copilot_echo.projects import create_project

        with _patch_root(self.tmp_path):
            create_project("Log", self.projects_dir)
            result = self.pm.append_project_entry(
                "Log", "Progress Log", "[2026-02-11] Did things"
            )
        assert "Entry added" in result

    def test_append_project_entry_size_warning(self):
        from copilot_echo.projects import create_project

        with _patch_root(self.tmp_path):
            # Set a very low cap so we trigger the warning
            self.pm._MAX_CHARS = 100
            create_project("Warn", self.projects_dir)
            # The template itself is already >100 chars
            result = self.pm.append_project_entry(
                "Warn", "Progress Log", "[2026-02-11] Large entry"
            )
        assert "WARNING" in result

    def test_compact_project_section_success(self):
        from copilot_echo.projects import create_project

        with _patch_root(self.tmp_path):
            create_project("Compact", self.projects_dir)
            result = self.pm.compact_project_section(
                "Compact", "Progress Log", "Condensed summary"
            )
        assert "replaced" in result.lower()

    def test_compact_project_section_error(self):
        with _patch_root(self.tmp_path):
            result = self.pm.compact_project_section(
                "Ghost", "Progress Log", "content"
            )
        assert "No active" in result or "not found" in result.lower()

    def test_get_file_chars_existing(self):
        from copilot_echo.projects import create_project

        with _patch_root(self.tmp_path):
            create_project("Chars", self.projects_dir)
            count = self.pm._get_file_chars("Chars")
        assert isinstance(count, int)
        assert count > 0

    def test_get_file_chars_missing(self):
        with _patch_root(self.tmp_path):
            count = self.pm._get_file_chars("Missing")
        assert count is None
