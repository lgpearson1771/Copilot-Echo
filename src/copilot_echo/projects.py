"""Project knowledge base management.

Handles creating, listing, archiving, and loading per-project knowledge
files under ``config/projects/{active,archive}/``.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
from datetime import date
from typing import List, Optional


def _resolve_root() -> str:
    """Return the repo root (two levels up from this source file)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _slugify(name: str) -> str:
    """Turn a human project name into a safe filename slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-") or "unnamed"


# ------------------------------------------------------------------
# Directory helpers
# ------------------------------------------------------------------

def _ensure_dirs(projects_dir: str) -> tuple[str, str]:
    """Ensure active/ and archive/ subdirectories exist.  Returns
    ``(active_dir, archive_dir)`` as absolute paths."""
    root = _resolve_root()
    base = os.path.join(root, projects_dir)
    active = os.path.join(base, "active")
    archive = os.path.join(base, "archive")
    os.makedirs(active, exist_ok=True)
    os.makedirs(archive, exist_ok=True)
    return active, archive


# ------------------------------------------------------------------
# CRUD
# ------------------------------------------------------------------

_TEMPLATE = """\
# Project: {name}

**Created:** {date}
**Status:** Active
**Goal:** (to be filled in by user or agent)

## Repos & Work Items
- Primary repo: (inherited from knowledge.md or specified)
- Work items: (agent appends as they're discussed)

## Key Decisions
<!-- Agent appends decisions as they're made during conversations -->

## Progress Log
<!-- Agent appends one-liner summaries of completed work items, PRs, etc. -->

## Blockers & Issues
<!-- Agent notes blockers encountered and how they were resolved -->

## Lessons Learned
<!-- Insights that might be useful for future projects -->
"""


def create_project(name: str, projects_dir: str) -> str:
    """Create a new active project file from template.

    Returns the absolute path to the created file, or raises
    ``FileExistsError`` if a project with that slug already exists.
    """
    active, _ = _ensure_dirs(projects_dir)
    slug = _slugify(name)
    path = os.path.join(active, f"{slug}.md")
    if os.path.exists(path):
        raise FileExistsError(f"Project '{name}' already exists at {path}")

    content = _TEMPLATE.format(name=name, date=date.today().isoformat())
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    logging.info("Created project '%s' → %s", name, path)
    return path


def archive_project(name: str, projects_dir: str) -> str:
    """Move an active project to the archive folder.

    Returns the new path in ``archive/``, or raises ``FileNotFoundError``.
    """
    active, archive = _ensure_dirs(projects_dir)
    slug = _slugify(name)
    src = os.path.join(active, f"{slug}.md")
    if not os.path.exists(src):
        raise FileNotFoundError(f"No active project '{name}' found at {src}")

    # Mark status as Archived in the file content
    try:
        text = _read(src)
        text = text.replace("**Status:** Active", f"**Status:** Archived ({date.today().isoformat()})")
        with open(src, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        logging.debug("Could not update status line in project file", exc_info=True)

    dst = os.path.join(archive, f"{slug}.md")
    shutil.move(src, dst)
    logging.info("Archived project '%s' → %s", name, dst)
    return dst


def list_projects(projects_dir: str) -> tuple[List[str], List[str]]:
    """Return ``(active_names, archived_names)`` based on files on disk."""
    active_dir, archive_dir = _ensure_dirs(projects_dir)
    active = _list_names(active_dir)
    archived = _list_names(archive_dir)
    return active, archived


def load_active_projects(projects_dir: str) -> str:
    """Read and concatenate all active project files into a single string
    suitable for injection into the system prompt."""
    active_dir, _ = _ensure_dirs(projects_dir)
    parts: list[str] = []
    try:
        for fname in sorted(os.listdir(active_dir)):
            if not fname.endswith(".md"):
                continue
            path = os.path.join(active_dir, fname)
            content = _read(path)
            if content:
                parts.append(content)
    except Exception:
        logging.exception("Failed to read active project files")
    if parts:
        combined = "\n\n---\n\n".join(parts)
        logging.info(
            "Loaded %d active project(s) (%d chars total)",
            len(parts),
            len(combined),
        )
        return combined
    return ""


def load_archived_project(name: str, projects_dir: str) -> Optional[str]:
    """Load a single archived project by name.  Returns ``None`` if not found."""
    _, archive_dir = _ensure_dirs(projects_dir)
    slug = _slugify(name)
    path = os.path.join(archive_dir, f"{slug}.md")
    if not os.path.exists(path):
        return None
    return _read(path)


def get_project_path(name: str, projects_dir: str) -> Optional[str]:
    """Return the absolute path to an active project file, or ``None``."""
    active_dir, _ = _ensure_dirs(projects_dir)
    slug = _slugify(name)
    path = os.path.join(active_dir, f"{slug}.md")
    return path if os.path.exists(path) else None


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def _list_names(directory: str) -> List[str]:
    """Return human-readable project names from filenames in *directory*."""
    names: list[str] = []
    try:
        for fname in sorted(os.listdir(directory)):
            if fname.endswith(".md"):
                names.append(fname.removesuffix(".md").replace("-", " ").title())
    except FileNotFoundError:
        pass
    return names
