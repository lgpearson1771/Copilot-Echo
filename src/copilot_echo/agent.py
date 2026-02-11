"""Bridge between the voice loop and the Copilot SDK agent."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
import sys
import threading
from typing import Optional

from copilot_echo.config import Config

# Lazily import copilot SDK so the module can be loaded even if the SDK
# has import-time side effects.
_copilot = None


def _ensure_copilot():
    global _copilot
    if _copilot is None:
        import copilot as _cp

        _copilot = _cp
    return _copilot


class Agent:
    """Manages a Copilot SDK client + session on a background asyncio loop.

    All public methods are **sync** and safe to call from the voice-loop thread.
    Internally they schedule coroutines on the private event loop.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self._client = None
        self._session = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._started = False
        self._current_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Spin up the background event loop, the Copilot CLI process, and
        create an initial session."""
        if self._started:
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=60)
        if not self._started:
            raise RuntimeError("Agent failed to start within 60 seconds")
        logging.info("Copilot agent ready")

    def stop(self) -> None:
        if self._loop and self._started:
            future = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
            try:
                future.result(timeout=10)
            except Exception:
                logging.exception("Error during agent shutdown")
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread:
                self._thread.join(timeout=5)
            self._started = False
            logging.info("Copilot agent stopped")

    # ------------------------------------------------------------------
    # Public API (sync, called from voice-loop thread)
    # ------------------------------------------------------------------

    def send(self, prompt: str, timeout: float = 120.0) -> str:
        """Send a user message and wait for the assistant's response.

        Returns the assistant reply text, or an error string on failure.
        """
        if not self._started or not self._loop:
            return "Agent is not running."
        future = asyncio.run_coroutine_threadsafe(
            self._send(prompt, timeout), self._loop
        )
        try:
            return future.result(timeout=timeout + 5)
        except concurrent.futures.CancelledError:
            logging.info("Agent request was cancelled")
            return ""
        except Exception as exc:
            logging.exception("Agent send failed")
            return f"Sorry, something went wrong: {exc}"

    def cancel(self) -> None:
        """Cancel any pending agent request."""
        task = self._current_task
        if task and self._loop:
            self._loop.call_soon_threadsafe(task.cancel)
            logging.info("Agent request cancelled")

    # ------------------------------------------------------------------
    # Internal async helpers
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        """Entry point for the background thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._startup())
        self._ready.set()
        self._loop.run_forever()

    async def _startup(self) -> None:
        cp = _ensure_copilot()
        try:
            self._client = cp.CopilotClient(
                options={
                    "use_logged_in_user": True,
                    "log_level": self.config.app.log_level.lower(),
                }
            )
            await self._client.start()
            self._session = await self._client.create_session(
                self._build_session_config()
            )
            self._started = True
            await self._log_available_tools()
        except Exception:
            logging.exception("Failed to start Copilot agent")
            self._started = False

    async def _log_available_tools(self) -> None:
        """Log the tools that the session actually has access to."""
        try:
            if not self._session:
                return
            # Ask the agent what tools it has by sending a diagnostic query
            # (the session object may expose tools directly on some SDK versions)
            session = self._session
            if hasattr(session, "available_tools"):
                tools = session.available_tools
                if tools:
                    names = [t.get("name", "?") if isinstance(t, dict) else str(t) for t in tools]
                    logging.info("Session tools (%d): %s", len(names), ", ".join(names))
                else:
                    logging.info("Session reports no available tools")
            elif hasattr(session, "tools"):
                tools = session.tools
                if tools:
                    names = [t.get("name", "?") if isinstance(t, dict) else str(t) for t in tools]
                    logging.info("Session tools (%d): %s", len(names), ", ".join(names))
            else:
                logging.info("Session object has no tools attribute — tool list unavailable for diagnostics")
        except Exception:
            logging.debug("Could not retrieve session tools", exc_info=True)

    async def _shutdown(self) -> None:
        if self._session:
            try:
                await self._session.destroy()
            except Exception:
                logging.debug("Session destroy failed", exc_info=True)
            self._session = None
        if self._client:
            try:
                await self._client.stop()
            except Exception:
                logging.debug("Client stop failed", exc_info=True)
            self._client = None

    async def _send(self, prompt: str, timeout: float) -> str:
        self._current_task = asyncio.current_task()
        try:
            if not self._session:
                return "No active session."
            response = await self._session.send_and_wait(
                {"prompt": prompt}, timeout=timeout
            )
            if response and hasattr(response, "data") and hasattr(response.data, "content"):
                return response.data.content or ""
            return ""
        except asyncio.CancelledError:
            logging.info("Agent send coroutine cancelled")
            raise
        except Exception as exc:
            logging.exception("send_and_wait failed")
            return f"Sorry, something went wrong: {exc}"
        finally:
            self._current_task = None

    def _build_session_config(self) -> dict:
        """Build the SessionConfig dict with MCP servers and system message."""
        system_content = (
            "You are Copilot Echo, a voice-controlled assistant for software development. "
            "You help the user manage Azure DevOps work items, inspect and modify code in "
            "their repository, and answer development questions. Keep responses concise and "
            "conversational — they will be read aloud via text-to-speech. Avoid markdown "
            "formatting, code blocks, or bullet lists in your replies since the user is "
            "listening, not reading. When referencing work items, read out the ID, title, "
            "and key fields naturally. You HAVE Azure DevOps MCP tools available — use them "
            "when asked about work items, pull requests, or repos in Azure DevOps."
        )

        # Append persistent knowledge from the knowledge file.
        knowledge = self._load_knowledge()
        if knowledge:
            system_content += (
                "\n\nBelow is persistent context the user has provided. "
                "Always keep these facts in mind:\n\n" + knowledge
            )

        # Append active project knowledge bases.
        from copilot_echo.projects import list_projects, load_active_projects

        projects_content = load_active_projects(
            self.config.agent.projects_dir,
            max_chars=self.config.agent.project_max_chars,
        )
        if projects_content:
            system_content += (
                "\n\nThe following are ACTIVE PROJECT knowledge bases. "
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

        # Tell the agent about archived projects so it can load them on demand.
        _, archived_names = list_projects(self.config.agent.projects_dir)
        if archived_names:
            system_content += (
                "\n\nArchived projects available for on-demand loading: "
                + ", ".join(archived_names)
                + ". When the user asks about a past project, or when historical "
                "context would help answer a question, use get_archived_project "
                "to retrieve the full content. You do not need to ask the user — "
                "load it proactively when relevant."
            )

        # Read MCP servers from the global Copilot CLI config so all
        # servers configured there are available to the agent.
        mcp_servers = self._load_global_mcp_servers()

        # Register the local project knowledge MCP server.
        mcp_servers.update(self._build_project_mcp_server())

        def approve_permission(request, context=None):
            kind = request.get("kind", "unknown") if isinstance(request, dict) else "unknown"
            logging.info("Permission requested: %s — auto-approving", kind)
            return {"kind": "approved"}

        def handle_user_input(request, context=None):
            logging.info("User input requested by agent (auto-declining)")
            return {"text": ""}

        config: dict = {
            "system_message": {"mode": "append", "content": system_content},
            "on_permission_request": approve_permission,
            "on_user_input_request": handle_user_input,
        }

        if mcp_servers:
            config["mcp_servers"] = mcp_servers

        if self.config.repo.default_path:
            config["working_directory"] = self.config.repo.default_path

        return config

    def _load_knowledge(self) -> str:
        """Load persistent knowledge from the configured knowledge file."""
        rel = self.config.agent.knowledge_file
        if not rel:
            return ""
        # Resolve relative to project root (two levels up from this file)
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.join(root, rel)
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

    def _build_project_mcp_server(self) -> dict:
        """Return an MCP server entry for the local project knowledge server."""
        root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        merged_env = dict(os.environ)
        merged_env["COPILOT_ECHO_PROJECTS_DIR"] = self.config.agent.projects_dir
        merged_env["COPILOT_ECHO_PROJECT_MAX_CHARS"] = str(
            self.config.agent.project_max_chars
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

    @staticmethod
    def _load_global_mcp_servers() -> dict:
        """Load MCP server definitions from the global Copilot CLI config."""
        config_path = os.path.expanduser("~/.copilot/config.json")
        if not os.path.exists(config_path):
            logging.warning("Global Copilot CLI config not found at %s", config_path)
            return {}

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            servers = data.get("mcp_servers", {})
            if servers:
                # Sanitize server names: replace spaces/invalid chars with underscores
                sanitized = {}
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
                        srv_env = srv.get("env", {})
                        merged_env = dict(os.environ)
                        merged_env.update(srv_env)
                        srv["env"] = merged_env
                        # If cwd is not set and command is "node" with an
                        # absolute path arg, derive cwd from the script path
                        # so Node resolves local node_modules correctly.
                        # Use the project root (two levels up from dist/x.js
                        # or one level up from x.js).
                        if "cwd" not in srv and srv.get("command") == "node":
                            args = srv.get("args", [])
                            if args:
                                script = args[0].replace("/", os.sep)
                                script_dir = os.path.dirname(os.path.abspath(script))
                                # Walk up to find node_modules
                                candidate = script_dir
                                for _ in range(3):
                                    if os.path.isdir(os.path.join(candidate, "node_modules")):
                                        srv["cwd"] = candidate
                                        logging.info(
                                            "Auto-set cwd for %s → %s",
                                            safe_name,
                                            candidate,
                                        )
                                        break
                                    parent = os.path.dirname(candidate)
                                    if parent == candidate:
                                        break
                                    candidate = parent
                    sanitized[safe_name] = srv
                servers = sanitized
                logging.info(
                    "Loaded %d MCP server(s) from global config: %s",
                    len(servers),
                    ", ".join(servers.keys()),
                )
            return servers
        except Exception:
            logging.exception("Failed to read global Copilot CLI config")
            return {}
