from __future__ import annotations

import enum
import logging
from typing import Optional

from copilot_echo.agent import Agent
from copilot_echo.config import Config


class State(enum.Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    AWAITING_CONTEXT = "awaiting_context"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    PAUSED = "paused"
    ERROR = "error"


class Orchestrator:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.state = State.IDLE
        self.last_error: Optional[str] = None
        self.agent = Agent(config)

    def start_agent(self) -> None:
        """Start the Copilot SDK agent."""
        try:
            self.agent.start()
        except Exception:
            logging.exception("Failed to start Copilot agent")
            self.last_error = "Agent failed to start"

    def stop_agent(self) -> None:
        """Shutdown the Copilot SDK agent."""
        self.agent.stop()

    def pause(self) -> None:
        self.state = State.PAUSED

    def resume(self) -> None:
        self.state = State.IDLE

    def on_wake_word(self) -> None:
        if self.state != State.PAUSED:
            self.state = State.LISTENING

    def send_to_agent(self, text: str) -> str:
        """Send a user transcript to the Copilot agent and return the reply."""
        self.state = State.PROCESSING
        try:
            reply = self.agent.send(text)
            return reply
        except Exception as exc:
            logging.exception("Agent error")
            self.last_error = str(exc)
            return "Sorry, I encountered an error."
        finally:
            self.state = State.IDLE

    def cancel_agent(self) -> None:
        """Cancel any pending agent request."""
        self.agent.cancel()
        self.state = State.IDLE
