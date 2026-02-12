"""Tests for copilot_echo.paths."""

import os

from copilot_echo.paths import project_root


def test_project_root_returns_repo_root():
    """project_root() should return the repo root (two levels above paths.py)."""
    root = project_root()
    # The repo root contains pyproject.toml
    assert os.path.isfile(os.path.join(root, "pyproject.toml"))


def test_project_root_is_absolute():
    root = project_root()
    assert os.path.isabs(root)


def test_project_root_contains_src():
    root = project_root()
    assert os.path.isdir(os.path.join(root, "src"))
