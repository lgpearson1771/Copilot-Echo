"""Build the session configuration and system prompt for the Copilot agent."""

from __future__ import annotations

import logging
import os

from copilot_echo.config import Config
from copilot_echo.mcp_config import build_project_mcp_server, load_global_mcp_servers
from copilot_echo.paths import project_root
from copilot_echo.projects import list_projects, load_active_projects


def build_session_config(config: Config) -> dict:
    """Build the SessionConfig dict with MCP servers and system message."""
    system_content = _build_system_prompt(config)

    mcp_servers = load_global_mcp_servers()
    mcp_servers.update(build_project_mcp_server(config))

    session_config: dict = {
        "system_message": {"mode": "append", "content": system_content},
        "on_permission_request": _approve_permission,
        "on_user_input_request": _handle_user_input,
    }

    if mcp_servers:
        session_config["mcp_servers"] = mcp_servers

    if config.repo.default_path:
        session_config["working_directory"] = config.repo.default_path

    return session_config


# ------------------------------------------------------------------
# System prompt assembly
# ------------------------------------------------------------------

_BASE_PROMPT = (
    "You are Copilot Echo, a voice-controlled assistant for software development. "
    "You help the user manage Azure DevOps work items, inspect and modify code in "
    "their repository, and answer development questions. Keep responses concise and "
    "conversational — they will be read aloud via text-to-speech. Avoid markdown "
    "formatting, code blocks, or bullet lists in your replies since the user is "
    "listening, not reading. When referencing work items, read out the ID, title, "
    "and key fields naturally. You HAVE Azure DevOps MCP tools available — use them "
    "when asked about work items, pull requests, or repos in Azure DevOps."
)


def _build_system_prompt(config: Config) -> str:
    """Assemble the full system prompt from base + knowledge + projects."""
    parts = [_BASE_PROMPT]

    # Persistent knowledge file
    knowledge = _load_knowledge(config.agent.knowledge_file)
    if knowledge:
        parts.append(
            "Below is persistent context the user has provided. "
            "Always keep these facts in mind:\n\n" + knowledge
        )

    # Active project knowledge bases
    projects_content = load_active_projects(
        config.agent.projects_dir,
        max_chars=config.agent.project_max_chars,
    )
    if projects_content:
        parts.append(
            "The following are ACTIVE PROJECT knowledge bases. "
            "Use them to understand ongoing work.\n\n"
            "You have project knowledge tools available "
            "(via the copilot_echo_projects MCP server):\n"
            "- append_project_entry(name, section, entry) — log work items, "
            "PRs, decisions, blockers, or lessons learned. Include a date "
            "prefix like '[2026-02-11]'. Do NOT ask before logging — just do it.\n"
            "- get_active_project(name) — read an active project in full.\n"
            "- compact_project_section(name, section, condensed_content) — "
            "replace a section with a shorter summary when warned about size.\n"
            "- list_all_projects() — discover active and archived projects.\n"
            "- get_archived_project(name) — load an archived project's content.\n\n"
            + projects_content
        )

    # Archived projects (names only — loaded on demand by the agent)
    _, archived_names = list_projects(config.agent.projects_dir)
    if archived_names:
        parts.append(
            "Archived projects available for on-demand loading: "
            + ", ".join(archived_names)
            + ". When the user asks about a past project, or when historical "
            "context would help answer a question, use get_archived_project "
            "to retrieve the full content. You do not need to ask the user — "
            "load it proactively when relevant."
        )

    return "\n\n".join(parts)


def _load_knowledge(knowledge_file: str | None) -> str:
    """Load persistent knowledge from the configured knowledge file."""
    if not knowledge_file:
        return ""
    root = project_root()
    path = os.path.join(root, knowledge_file)
    if not os.path.exists(path):
        logging.warning("Knowledge file not found: %s", path)
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            logging.info("Loaded knowledge file (%d chars): %s", len(content), path)
        return content
    except Exception:
        logging.exception("Failed to read knowledge file %s", path)
        return ""


# ------------------------------------------------------------------
# Permission / input request handlers
# ------------------------------------------------------------------


def _approve_permission(request, context=None):
    kind = request.get("kind", "unknown") if isinstance(request, dict) else "unknown"
    logging.info("Permission requested: %s — auto-approving", kind)
    return {"kind": "approved"}


def _handle_user_input(request, context=None):
    logging.info("User input requested by agent (auto-declining)")
    return {"text": ""}
