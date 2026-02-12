from __future__ import annotations

import enum
import logging
import threading

from copilot_echo.agent import Agent
from copilot_echo.config import Config


class State(enum.Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    AUTONOMOUS = "autonomous"
    AWAITING_CONTEXT = "awaiting_context"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    PAUSED = "paused"
    ERROR = "error"


class Orchestrator:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.state = State.IDLE
        self.last_error: str | None = None
        self.agent = Agent(config)
        self.interrupt_event = threading.Event()
        self._auto_paused: bool = False

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
        self._auto_paused = False
        self.state = State.IDLE

    def auto_pause(self) -> None:
        """Pause due to an active call.  Only takes effect from IDLE or LISTENING."""
        if self.state in (State.IDLE, State.LISTENING):
            self._auto_paused = True
            self.state = State.PAUSED

    def auto_resume(self) -> None:
        """Resume after an auto-pause.  No-op if the pause was manual."""
        if self._auto_paused:
            self._auto_paused = False
            self.state = State.IDLE

    @property
    def is_auto_paused(self) -> bool:
        return self._auto_paused

    def on_wake_word(self) -> None:
        if self.state != State.PAUSED:
            self.state = State.LISTENING

    def send_to_agent(self, text: str, keep_state: bool = False) -> str:
        """Send a user transcript to the Copilot agent and return the reply.

        If *keep_state* is True the state is NOT reset to IDLE after the
        call (used during autonomous mode).
        """
        prev_state = self.state
        self.state = State.PROCESSING
        try:
            reply = self.agent.send(text)
            return reply
        except Exception as exc:
            logging.exception("Agent error")
            self.last_error = str(exc)
            return "Sorry, I encountered an error."
        finally:
            if keep_state:
                self.state = prev_state
            else:
                self.state = State.IDLE

    def cancel_agent(self) -> None:
        """Cancel any pending agent request."""
        self.agent.cancel()
        self.state = State.IDLE

    def start_autonomous(self) -> None:
        """Enter autonomous working mode."""
        self.interrupt_event.clear()
        self.state = State.AUTONOMOUS
        logging.info("Entering autonomous mode")

    def stop_autonomous(self) -> None:
        """Leave autonomous working mode."""
        self.interrupt_event.clear()
        self.state = State.IDLE
        logging.info("Exiting autonomous mode")

    def request_interrupt(self) -> None:
        """Signal an interrupt from the hotkey or tray button."""
        self.interrupt_event.set()
        logging.info("Interrupt requested via hotkey/tray")
