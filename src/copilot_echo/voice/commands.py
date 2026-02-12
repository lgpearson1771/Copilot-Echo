"""Voice command handler for project knowledge base commands."""

from __future__ import annotations

import logging
import re

from copilot_echo import projects
from copilot_echo.config import Config
from copilot_echo.orchestrator import Orchestrator
from copilot_echo.voice.tts import TextToSpeech


_START_PATTERNS = [
    re.compile(r"start a project (?:called |named )?(.+)", re.IGNORECASE),
    re.compile(r"create a project (?:called |named )?(.+)", re.IGNORECASE),
    re.compile(r"new project (?:called |named )?(.+)", re.IGNORECASE),
]
_FINISH_PATTERNS = [
    re.compile(
        r"(?:finish|close|complete|end) (?:the )?project (?:called |named )?(.+)",
        re.IGNORECASE,
    ),
    re.compile(r"archive (?:the )?project (?:called |named )?(.+)", re.IGNORECASE),
]
_LIST_PHRASES = [
    "list my projects",
    "list projects",
    "show my projects",
    "what projects do i have",
]


class VoiceCommandHandler:
    """Handles project-related voice commands."""

    def __init__(
        self,
        config: Config,
        orchestrator: Orchestrator,
        tts: TextToSpeech,
    ) -> None:
        self.config = config
        self.orchestrator = orchestrator
        self.tts = tts

    def handle(self, normalized: str, original: str) -> bool:
        """Check for project-related voice commands.

        Returns ``True`` if a command was handled.
        """
        # List projects
        if any(phrase in normalized for phrase in _LIST_PHRASES):
            return self._cmd_list_projects()

        # Start a project — match against original to preserve casing
        for pat in _START_PATTERNS:
            m = pat.search(original)
            if m:
                name = self._extract_project_name(m.group(1).strip())
                return self._cmd_start_project(name)

        # Finish / archive a project
        for pat in _FINISH_PATTERNS:
            m = pat.search(original)
            if m:
                name = self._extract_project_name(m.group(1).strip())
                return self._cmd_finish_project(name)

        return False

    # ------------------------------------------------------------------
    # Individual commands
    # ------------------------------------------------------------------

    def _cmd_start_project(self, name: str) -> bool:
        try:
            projects.create_project(name, self.config.agent.projects_dir)
            self.tts.speak(f"Project {name} created. I'll start tracking it.")
            logging.info("Project created: %s", name)
        except FileExistsError:
            self.tts.speak(f"A project called {name} already exists.")
        except Exception:
            logging.exception("Failed to create project")
            self.tts.speak("Sorry, I couldn't create that project.")
        return True

    def _cmd_finish_project(self, name: str) -> bool:
        try:
            projects.archive_project(name, self.config.agent.projects_dir)
            self.tts.speak(f"Project {name} has been archived.")
            logging.info("Project archived: %s", name)
        except FileNotFoundError:
            self.tts.speak(f"I couldn't find an active project called {name}.")
        except Exception:
            logging.exception("Failed to archive project")
            self.tts.speak("Sorry, I couldn't archive that project.")
        return True

    def _cmd_list_projects(self) -> bool:
        try:
            active, archived = projects.list_projects(self.config.agent.projects_dir)
            if not active and not archived:
                self.tts.speak("You don't have any projects yet.")
            else:
                parts: list[str] = []
                if active:
                    names = ", ".join(active)
                    parts.append(f"Active projects: {names}.")
                if archived:
                    names = ", ".join(archived)
                    parts.append(f"Archived projects: {names}.")
                self.tts.speak(" ".join(parts))
        except Exception:
            logging.exception("Failed to list projects")
            self.tts.speak("Sorry, I couldn't list your projects.")
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_project_name(self, raw_name: str) -> str:
        """Use the agent to extract a clean project name from raw speech."""
        prompt = (
            "The user said the following when creating or referencing a project. "
            "Extract ONLY the short project name — remove any conversational "
            "filler like 'for me about the', 'about', 'the one for', etc. "
            "Return ONLY the project name, nothing else. No quotes, no "
            "explanation.\n\n"
            f'User said: "{raw_name}"'
        )
        try:
            reply = self.orchestrator.send_to_agent(prompt)
            cleaned = reply.strip().strip('"').strip("'").strip() if reply else ""
            if cleaned and len(cleaned) < len(raw_name) * 2:
                logging.info(
                    "Agent extracted project name: '%s' (from '%s')",
                    cleaned,
                    raw_name,
                )
                return cleaned
        except Exception:
            logging.debug("Agent name extraction failed, using raw name", exc_info=True)
        return raw_name
