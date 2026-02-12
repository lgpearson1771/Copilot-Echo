"""MCP server configuration loading and registration."""

from __future__ import annotations

import json
import logging
import os
import sys
import time

from copilot_echo.config import Config
from copilot_echo.paths import project_root


def load_global_mcp_servers() -> dict:
    """Load MCP server definitions from the global Copilot CLI config.

    Retries once on transient read errors (e.g. the file is locked by
    another process writing to it).
    """
    config_path = os.path.expanduser("~/.copilot/config.json")
    if not os.path.exists(config_path):
        logging.warning("Global Copilot CLI config not found at %s", config_path)
        return {}

    last_exc: Exception | None = None
    for attempt in range(1, 3):  # up to 2 attempts
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            servers = data.get("mcp_servers", {})
            if servers:
                servers = _sanitize_servers(servers)
                logging.info(
                    "Loaded %d MCP server(s) from global config: %s",
                    len(servers),
                    ", ".join(servers.keys()),
                )
            return servers
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                logging.warning(
                    "Failed to read global config (attempt %d/2), retrying: %s",
                    attempt,
                    exc,
                )
                time.sleep(1)

    logging.exception("Failed to read global Copilot CLI config", exc_info=last_exc)
    return {}


def build_project_mcp_server(config: Config) -> dict:
    """Return an MCP server entry for the local project knowledge server."""
    root = project_root()
    merged_env = dict(os.environ)
    merged_env["COPILOT_ECHO_PROJECTS_DIR"] = config.agent.projects_dir
    merged_env["COPILOT_ECHO_PROJECT_MAX_CHARS"] = str(
        config.agent.project_max_chars
    )
    server = {
        "copilot_echo_projects": {
            "type": "stdio",
            "command": sys.executable,
            "args": ["-m", "copilot_echo.project_mcp"],
            "cwd": root,
            "env": merged_env,
            "tools": ["*"],
            "timeout": 10_000,
        }
    }
    logging.info("Registered local project MCP server (cwd=%s)", root)
    return server


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _sanitize_servers(servers: dict) -> dict:
    """Sanitize server names and ensure required fields are present."""
    sanitized: dict = {}
    for name, srv in servers.items():
        safe_name = name.replace(" ", "_")
        if "tools" not in srv:
            srv["tools"] = ["*"]
        # Give servers enough time to start (60 s for slow starters)
        if "timeout" not in srv:
            srv["timeout"] = 60_000
        # For stdio servers, merge parent environment so child
        # processes can find binaries (node, npx, az CLI, etc.)
        if srv.get("type") in ("stdio", "local", None):
            _merge_stdio_env(srv, safe_name)
        sanitized[safe_name] = srv
    return sanitized


def _merge_stdio_env(srv: dict, name: str) -> None:
    """Merge parent environment into stdio server config and auto-detect cwd."""
    srv_env = srv.get("env", {})
    merged_env = dict(os.environ)
    merged_env.update(srv_env)
    srv["env"] = merged_env

    # If cwd is not set and command is "node" with an absolute path arg,
    # derive cwd from the script path so Node resolves local node_modules.
    if "cwd" not in srv and srv.get("command") == "node":
        args = srv.get("args", [])
        if args:
            script = args[0].replace("/", os.sep)
            script_dir = os.path.dirname(os.path.abspath(script))
            candidate = script_dir
            for _ in range(3):
                if os.path.isdir(os.path.join(candidate, "node_modules")):
                    srv["cwd"] = candidate
                    logging.info("Auto-set cwd for %s → %s", name, candidate)
                    break
                parent = os.path.dirname(candidate)
                if parent == candidate:
                    break
                candidate = parent
