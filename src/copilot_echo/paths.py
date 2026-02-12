"""Shared path utilities for Copilot Echo."""

from __future__ import annotations

import os


def project_root() -> str:
    """Return the absolute path to the repository root.

    The repo root is two directory levels above this source file
    (``src/copilot_echo/paths.py`` → repo root).
    """
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
