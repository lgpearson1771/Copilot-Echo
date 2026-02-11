"""Local MCP server exposing project knowledge base tools.

Started as a stdio subprocess by the Copilot SDK agent so the agent can
autonomously read, write, and manage project knowledge files.

Run standalone for testing::

    python -m copilot_echo.project_mcp
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from copilot_echo.projects import (
    append_entry,
    list_projects,
    load_archived_project,
    read_active_project,
    replace_section,
)

# Configuration passed via environment variables from the parent process.
_PROJECTS_DIR = os.environ.get("COPILOT_ECHO_PROJECTS_DIR", "config/projects")
_MAX_CHARS = int(os.environ.get("COPILOT_ECHO_PROJECT_MAX_CHARS", "4000"))

mcp_server = FastMCP("Copilot Echo Projects")


# ------------------------------------------------------------------
# Tools
# ------------------------------------------------------------------


@mcp_server.tool()
def list_all_projects() -> str:
    """List all active and archived project names.

    Use this to discover what projects exist before loading or editing them.
    """
    active, archived = list_projects(_PROJECTS_DIR)
    lines: list[str] = []
    if active:
        lines.append("Active projects: " + ", ".join(active))
    else:
        lines.append("No active projects.")
    if archived:
        lines.append("Archived projects: " + ", ".join(archived))
    else:
        lines.append("No archived projects.")
    return "\n".join(lines)


@mcp_server.tool()
def get_archived_project(name: str) -> str:
    """Load the full content of an archived project by name.

    Use this when the user asks about a past/completed project or when
    historical context would help answer a question.
    """
    content = load_archived_project(name, _PROJECTS_DIR)
    if content is None:
        return f"No archived project named '{name}' found."
    return content


@mcp_server.tool()
def get_active_project(name: str) -> str:
    """Read the full content of an active project.

    Use this to review the current state of a project, e.g. before
    deciding whether to compact older entries.
    """
    content = read_active_project(name, _PROJECTS_DIR)
    if content is None:
        return f"No active project named '{name}' found."
    return content


@mcp_server.tool()
def append_project_entry(name: str, section: str, entry: str) -> str:
    """Append a one-line entry to a section in an active project.

    Use this to log work items resolved, PRs merged, key decisions,
    blockers encountered, or lessons learned.

    Args:
        name: The project name (e.g. "Query Migration").
        section: One of: "Repos & Work Items", "Key Decisions",
                 "Progress Log", "Blockers & Issues", "Lessons Learned".
        entry: The entry text. Include a date prefix, e.g.
               "[2026-02-11] WI#12345: Fixed query timeout (resolved)".

    Returns a status message including the current file size. If the file
    is approaching the character cap, a warning will be included — use
    ``compact_project_section`` to condense older entries.
    """
    try:
        result = append_entry(name, section, entry, _PROJECTS_DIR)
    except (FileNotFoundError, ValueError) as exc:
        return str(exc)

    # Warn if approaching the cap
    char_count = _get_file_chars(name)
    if char_count and _MAX_CHARS > 0 and char_count > int(_MAX_CHARS * 0.85):
        result += (
            f" WARNING: File is at {char_count}/{_MAX_CHARS} chars — "
            "consider using compact_project_section to condense older entries."
        )
    return result


@mcp_server.tool()
def compact_project_section(name: str, section: str, condensed_content: str) -> str:
    """Replace a section's content with a condensed/summarized version.

    Use this when a project file is approaching its character cap. Read
    the project first with ``get_active_project``, write a compact
    summary of the older entries, then call this tool to replace the
    section content.

    Args:
        name: The project name.
        section: One of: "Repos & Work Items", "Key Decisions",
                 "Progress Log", "Blockers & Issues", "Lessons Learned".
        condensed_content: The new, shorter content for the section.
    """
    try:
        return replace_section(name, section, condensed_content, _PROJECTS_DIR)
    except (FileNotFoundError, ValueError) as exc:
        return str(exc)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _get_file_chars(name: str) -> int | None:
    """Return the character count of an active project file, or None."""
    content = read_active_project(name, _PROJECTS_DIR)
    return len(content) if content else None


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    mcp_server.run()
