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

from copilot_echo.paths import project_root


def _resolve_root() -> str:
    """Return the repo root."""
    return project_root()


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


def list_projects(projects_dir: str) -> tuple[list[str], list[str]]:
    """Return ``(active_names, archived_names)`` based on files on disk."""
    active_dir, archive_dir = _ensure_dirs(projects_dir)
    active = _list_names(active_dir)
    archived = _list_names(archive_dir)
    return active, archived


def load_active_projects(projects_dir: str, max_chars: int = 0) -> str:
    """Read and concatenate all active project files into a single string
    suitable for injection into the system prompt.

    If *max_chars* is > 0, individual files that exceed the cap are
    truncated with a notice asking the agent to compact them.
    """
    active_dir, _ = _ensure_dirs(projects_dir)
    parts: list[str] = []
    try:
        for fname in sorted(os.listdir(active_dir)):
            if not fname.endswith(".md"):
                continue
            path = os.path.join(active_dir, fname)
            content = _read(path)
            if not content:
                continue
            if max_chars > 0 and len(content) > max_chars:
                original_len = len(content)
                content = (
                    content[:max_chars]
                    + "\n\n[TRUNCATED \u2014 file exceeds "
                    + f"{max_chars} char cap. Use compact_project_section "
                    + "to condense older entries.]"
                )
                logging.warning(
                    "Project file %s exceeds cap (%d/%d chars) \u2014 truncated",
                    fname, original_len, max_chars,
                )
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


def load_archived_project(name: str, projects_dir: str) -> str | None:
    """Load a single archived project by name.  Returns ``None`` if not found."""
    _, archive_dir = _ensure_dirs(projects_dir)
    slug = _slugify(name)
    path = os.path.join(archive_dir, f"{slug}.md")
    if not os.path.exists(path):
        return None
    return _read(path)


def get_project_path(name: str, projects_dir: str) -> str | None:
    """Return the absolute path to an active project file, or ``None``."""
    active_dir, _ = _ensure_dirs(projects_dir)
    slug = _slugify(name)
    path = os.path.join(active_dir, f"{slug}.md")
    return path if os.path.exists(path) else None


# ------------------------------------------------------------------
# Section editing (used by MCP server)
# ------------------------------------------------------------------

_VALID_SECTIONS = {
    "Repos & Work Items",
    "Key Decisions",
    "Progress Log",
    "Blockers & Issues",
    "Lessons Learned",
}


def append_entry(
    name: str, section: str, entry: str, projects_dir: str
) -> str:
    """Append a dated one-liner to *section* in an active project.

    Returns a status message.  Raises ``FileNotFoundError`` if the
    project doesn't exist, or ``ValueError`` for an invalid section.
    """
    if section not in _VALID_SECTIONS:
        raise ValueError(
            f"Invalid section '{section}'. "
            f"Valid sections: {', '.join(sorted(_VALID_SECTIONS))}"
        )
    path = get_project_path(name, projects_dir)
    if not path:
        raise FileNotFoundError(f"No active project '{name}'")

    text = _read(path)
    heading = f"## {section}"
    idx = text.find(heading)
    if idx == -1:
        raise ValueError(f"Section '{section}' heading not found in project file")

    # Find the end of the heading line
    eol = text.find("\n", idx)
    if eol == -1:
        eol = len(text)

    # Find the next section heading or end of file
    next_heading = re.search(r"\n## ", text[eol + 1:])
    if next_heading:
        insert_pos = eol + 1 + next_heading.start()
    else:
        insert_pos = len(text)

    # Strip trailing whitespace at insertion point and add entry
    before = text[:insert_pos].rstrip()
    after = text[insert_pos:]
    dated_entry = f"\n- {entry}"
    new_text = before + dated_entry + "\n" + after

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_text)

    char_count = len(new_text)
    msg = f"Entry added to {section} in project '{name}'."
    logging.info(msg)
    return f"{msg} File is now {char_count} chars."


def replace_section(
    name: str, section: str, new_content: str, projects_dir: str
) -> str:
    """Replace everything under *section* heading with *new_content*.

    Used for compacting / summarizing older entries.  Returns a status
    message.  Raises ``FileNotFoundError`` or ``ValueError`` on bad input.
    """
    if section not in _VALID_SECTIONS:
        raise ValueError(
            f"Invalid section '{section}'. "
            f"Valid sections: {', '.join(sorted(_VALID_SECTIONS))}"
        )
    path = get_project_path(name, projects_dir)
    if not path:
        raise FileNotFoundError(f"No active project '{name}'")

    text = _read(path)
    heading = f"## {section}"
    idx = text.find(heading)
    if idx == -1:
        raise ValueError(f"Section '{section}' heading not found in project file")

    # End of heading line
    eol = text.find("\n", idx)
    if eol == -1:
        eol = len(text)

    # Find next section heading or end of file
    next_heading = re.search(r"\n## ", text[eol + 1:])
    if next_heading:
        end_pos = eol + 1 + next_heading.start()
    else:
        end_pos = len(text)

    before = text[: eol + 1]
    after = text[end_pos:]
    new_text = before + new_content.strip() + "\n" + after

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_text)

    char_count = len(new_text)
    msg = f"Section '{section}' replaced in project '{name}'."
    logging.info(msg)
    return f"{msg} File is now {char_count} chars."


def read_active_project(name: str, projects_dir: str) -> str | None:
    """Read and return the full content of an active project.

    Returns ``None`` if the project doesn't exist.
    """
    path = get_project_path(name, projects_dir)
    if not path:
        return None
    return _read(path)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def _list_names(directory: str) -> list[str]:
    """Return human-readable project names from filenames in *directory*."""
    names: list[str] = []
    try:
        for fname in sorted(os.listdir(directory)):
            if fname.endswith(".md"):
                names.append(fname.removesuffix(".md").replace("-", " ").title())
    except FileNotFoundError:
        pass
    return names
