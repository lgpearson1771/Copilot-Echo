"""Tests for copilot_echo.projects — the most testable module."""

from __future__ import annotations

import os
from datetime import date
from unittest.mock import patch

import pytest

# Patch project_root so _ensure_dirs works with tmp_path
# We do this at the module level for all tests in this file.


def _patch_root(tmp_path):
    """Helper — return a patcher that overrides _resolve_root."""
    return patch("copilot_echo.projects._resolve_root", return_value=str(tmp_path))


# ------------------------------------------------------------------
# _slugify
# ------------------------------------------------------------------

from copilot_echo.projects import _slugify


class TestSlugify:
    def test_basic(self):
        assert _slugify("Hello World") == "hello-world"

    def test_special_chars(self):
        assert _slugify("My Project! (v2)") == "my-project-v2"

    def test_empty_string(self):
        assert _slugify("") == "unnamed"

    def test_mixed_case(self):
        assert _slugify("CamelCaseProject") == "camelcaseproject"

    def test_leading_trailing_hyphens(self):
        assert _slugify("---test---") == "test"

    def test_only_special_chars(self):
        assert _slugify("!!!") == "unnamed"

    def test_numbers(self):
        assert _slugify("project 123") == "project-123"


# ------------------------------------------------------------------
# create_project / archive_project
# ------------------------------------------------------------------

from copilot_echo.projects import (
    archive_project,
    create_project,
    get_project_path,
    list_projects,
    load_active_projects,
    load_archived_project,
    read_active_project,
    append_entry,
    replace_section,
)


class TestCreateProject:
    def test_creates_file(self, tmp_path):
        with _patch_root(tmp_path):
            path = create_project("My App", "config/projects")
        assert os.path.isfile(path)
        content = open(path, encoding="utf-8").read()
        assert "# Project: My App" in content
        assert date.today().isoformat() in content

    def test_file_in_active_dir(self, tmp_path):
        with _patch_root(tmp_path):
            path = create_project("Test", "config/projects")
        assert os.sep + "active" + os.sep in path or "/active/" in path

    def test_duplicate_raises(self, tmp_path):
        with _patch_root(tmp_path):
            create_project("Dupe", "config/projects")
            with pytest.raises(FileExistsError):
                create_project("Dupe", "config/projects")

    def test_template_has_sections(self, tmp_path):
        with _patch_root(tmp_path):
            path = create_project("Sections", "config/projects")
        content = open(path, encoding="utf-8").read()
        for section in [
            "## Repos & Work Items",
            "## Key Decisions",
            "## Progress Log",
            "## Blockers & Issues",
            "## Lessons Learned",
        ]:
            assert section in content


class TestArchiveProject:
    def test_moves_file(self, tmp_path):
        with _patch_root(tmp_path):
            src = create_project("Movable", "config/projects")
            dst = archive_project("Movable", "config/projects")
        assert not os.path.exists(src)
        assert os.path.isfile(dst)

    def test_updates_status_line(self, tmp_path):
        with _patch_root(tmp_path):
            create_project("Status", "config/projects")
            dst = archive_project("Status", "config/projects")
        content = open(dst, encoding="utf-8").read()
        assert "Archived" in content
        assert "Active" not in content.split("Status:")[1].split("\n")[0]

    def test_not_found_raises(self, tmp_path):
        with _patch_root(tmp_path):
            with pytest.raises(FileNotFoundError):
                archive_project("Nonexistent", "config/projects")


# ------------------------------------------------------------------
# list_projects
# ------------------------------------------------------------------

class TestListProjects:
    def test_empty_dirs(self, tmp_path):
        with _patch_root(tmp_path):
            active, archived = list_projects("config/projects")
        assert active == []
        assert archived == []

    def test_active_only(self, tmp_path):
        with _patch_root(tmp_path):
            create_project("Alpha", "config/projects")
            active, archived = list_projects("config/projects")
        assert len(active) == 1
        assert archived == []

    def test_archived_only(self, tmp_path):
        with _patch_root(tmp_path):
            create_project("Beta", "config/projects")
            archive_project("Beta", "config/projects")
            active, archived = list_projects("config/projects")
        assert active == []
        assert len(archived) == 1

    def test_both(self, tmp_path):
        with _patch_root(tmp_path):
            create_project("One", "config/projects")
            create_project("Two", "config/projects")
            archive_project("Two", "config/projects")
            active, archived = list_projects("config/projects")
        assert len(active) == 1
        assert len(archived) == 1


# ------------------------------------------------------------------
# load_active_projects
# ------------------------------------------------------------------

class TestLoadActiveProjects:
    def test_empty_returns_empty_string(self, tmp_path):
        with _patch_root(tmp_path):
            result = load_active_projects("config/projects")
        assert result == ""

    def test_single_project(self, tmp_path):
        with _patch_root(tmp_path):
            create_project("Solo", "config/projects")
            result = load_active_projects("config/projects")
        assert "Solo" in result

    def test_max_chars_truncation(self, tmp_path):
        with _patch_root(tmp_path):
            create_project("Big", "config/projects")
            result = load_active_projects("config/projects", max_chars=50)
        assert "TRUNCATED" in result

    def test_multiple_projects_joined(self, tmp_path):
        with _patch_root(tmp_path):
            create_project("First", "config/projects")
            create_project("Second", "config/projects")
            result = load_active_projects("config/projects")
        assert "First" in result
        assert "Second" in result
        assert "---" in result  # separator


# ------------------------------------------------------------------
# append_entry / replace_section
# ------------------------------------------------------------------

class TestAppendEntry:
    def test_valid_section(self, tmp_path):
        with _patch_root(tmp_path):
            create_project("Append", "config/projects")
            result = append_entry(
                "Append", "Progress Log", "[2026-02-11] Did stuff", "config/projects"
            )
        assert "Entry added" in result
        assert "chars" in result

    def test_entry_appears_in_file(self, tmp_path):
        with _patch_root(tmp_path):
            create_project("Check", "config/projects")
            append_entry(
                "Check", "Key Decisions", "[2026-02-11] Pick Python", "config/projects"
            )
            content = read_active_project("Check", "config/projects")
        assert "Pick Python" in content

    def test_invalid_section_raises(self, tmp_path):
        with _patch_root(tmp_path):
            create_project("Bad", "config/projects")
            with pytest.raises(ValueError, match="Invalid section"):
                append_entry("Bad", "Nonexistent Section", "entry", "config/projects")

    def test_missing_project_raises(self, tmp_path):
        with _patch_root(tmp_path):
            with pytest.raises(FileNotFoundError):
                append_entry("Ghost", "Progress Log", "entry", "config/projects")


class TestReplaceSection:
    def test_replace_success(self, tmp_path):
        with _patch_root(tmp_path):
            create_project("Replace", "config/projects")
            append_entry(
                "Replace", "Progress Log", "[old] entry", "config/projects"
            )
            result = replace_section(
                "Replace", "Progress Log", "Condensed summary", "config/projects"
            )
        assert "replaced" in result.lower()

    def test_replace_invalid_section(self, tmp_path):
        with _patch_root(tmp_path):
            create_project("RBad", "config/projects")
            with pytest.raises(ValueError, match="Invalid section"):
                replace_section("RBad", "Fake", "content", "config/projects")

    def test_replace_preserves_other_sections(self, tmp_path):
        with _patch_root(tmp_path):
            create_project("Preserve", "config/projects")
            append_entry(
                "Preserve", "Key Decisions", "keep me", "config/projects"
            )
            replace_section(
                "Preserve", "Progress Log", "New progress", "config/projects"
            )
            content = read_active_project("Preserve", "config/projects")
        assert "keep me" in content
        assert "New progress" in content


# ------------------------------------------------------------------
# read_active_project / load_archived_project / get_project_path
# ------------------------------------------------------------------

class TestReadProject:
    def test_read_active_exists(self, tmp_path):
        with _patch_root(tmp_path):
            create_project("Readable", "config/projects")
            content = read_active_project("Readable", "config/projects")
        assert content is not None
        assert "Readable" in content

    def test_read_active_not_exists(self, tmp_path):
        with _patch_root(tmp_path):
            content = read_active_project("Nope", "config/projects")
        assert content is None

    def test_load_archived_not_found(self, tmp_path):
        with _patch_root(tmp_path):
            result = load_archived_project("Nope", "config/projects")
        assert result is None

    def test_load_archived_found(self, tmp_path):
        with _patch_root(tmp_path):
            create_project("Archived", "config/projects")
            archive_project("Archived", "config/projects")
            content = load_archived_project("Archived", "config/projects")
        assert content is not None
        assert "Archived" in content

    def test_get_project_path_exists(self, tmp_path):
        with _patch_root(tmp_path):
            create_project("Pathed", "config/projects")
            path = get_project_path("Pathed", "config/projects")
        assert path is not None
        assert os.path.isfile(path)

    def test_get_project_path_not_exists(self, tmp_path):
        with _patch_root(tmp_path):
            path = get_project_path("Missing", "config/projects")
        assert path is None


# ------------------------------------------------------------------
# _list_names
# ------------------------------------------------------------------

from copilot_echo.projects import _list_names


class TestListNames:
    def test_converts_slug_to_title(self, tmp_path):
        # Create a file with a slug name
        (tmp_path / "my-cool-project.md").write_text("content", encoding="utf-8")
        names = _list_names(str(tmp_path))
        assert names == ["My Cool Project"]

    def test_ignores_non_md_files(self, tmp_path):
        (tmp_path / "readme.txt").write_text("x", encoding="utf-8")
        (tmp_path / "project.md").write_text("x", encoding="utf-8")
        names = _list_names(str(tmp_path))
        assert len(names) == 1

    def test_empty_directory(self, tmp_path):
        names = _list_names(str(tmp_path))
        assert names == []

    def test_missing_directory(self, tmp_path):
        names = _list_names(str(tmp_path / "nonexistent"))
        assert names == []
