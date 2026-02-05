from __future__ import annotations

import enum
from typing import Optional

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

    def pause(self) -> None:
        self.state = State.PAUSED

    def resume(self) -> None:
        self.state = State.IDLE

    def on_wake_word(self) -> None:
        if self.state != State.PAUSED:
            self.state = State.LISTENING

    def on_transcript(self, text: str) -> None:
        self.state = State.PROCESSING
        # TODO: Parse intent, call MCP via Copilot SDK, read back, request context.
        self.state = State.AWAITING_CONTEXT

    def on_additional_context(self, text: str) -> None:
        self.state = State.PROCESSING
        # TODO: Start agent session and prepare plan.
        self.state = State.AWAITING_CONFIRMATION

    def on_confirm(self, confirmed: bool) -> None:
        self.state = State.PROCESSING
        # TODO: Apply changes if confirmed.
        self.state = State.IDLE if confirmed else State.AWAITING_CONTEXT
