"""Autonomous 'Get to Work' mode for the voice loop."""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable

from copilot_echo.config import Config
from copilot_echo.orchestrator import Orchestrator
from copilot_echo.voice.stt import SpeechToText
from copilot_echo.voice.tts import INTERRUPT_LISTEN_SEC, INTERRUPT_PHRASES, TextToSpeech


_AD_HOC_PATTERN = re.compile(
    r"(?:get to work|start working|work) on (.+)", re.IGNORECASE
)


class AutonomousRunner:
    """Manages autonomous multi-step routines with interrupt support."""

    def __init__(
        self,
        config: Config,
        orchestrator: Orchestrator,
        stt: SpeechToText,
        tts: TextToSpeech,
        speak_interruptible: Callable[[str], bool],
    ) -> None:
        self.config = config
        self.orchestrator = orchestrator
        self.stt = stt
        self.tts = tts
        self._speak_interruptible = speak_interruptible
        self._interrupt_watcher_stop = threading.Event()
        self._agent_interrupted = threading.Event()

    # ------------------------------------------------------------------
    # Trigger detection
    # ------------------------------------------------------------------

    def check_trigger(
        self,
        normalized: str,
        original: str,
        status_callback: Callable[[str], None],
        stop_event: threading.Event,
    ) -> bool:
        """Return ``True`` and run the autonomous loop if *text* matches a trigger."""
        routines = self.config.agent.autonomous_routines

        # 1. Check pre-configured routine trigger phrases
        for routine in routines:
            for phrase in routine.trigger_phrases:
                if phrase.lower() in normalized:
                    logging.info(
                        "Autonomous routine triggered: %s (phrase='%s')",
                        routine.name,
                        phrase,
                    )
                    max_steps = (
                        routine.max_steps
                        if routine.max_steps is not None
                        else self.config.agent.autonomous_max_steps
                    )
                    self.tts.speak(f"Starting routine: {routine.name}.")
                    self._run(
                        routine.prompt,
                        max_steps,
                        self.config.agent.autonomous_max_minutes,
                        status_callback,
                        stop_event,
                    )
                    return True

        # 2. Ad-hoc "get to work on {task}" support
        m = _AD_HOC_PATTERN.search(original)
        if m:
            task = m.group(1).strip()
            logging.info("Ad-hoc autonomous task: %s", task)
            self.tts.speak(f"Got it, working on: {task}.")
            self._run(
                task,
                self.config.agent.autonomous_max_steps,
                self.config.agent.autonomous_max_minutes,
                status_callback,
                stop_event,
            )
            return True

        return False

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _run(
        self,
        prompt: str,
        max_steps: int,
        max_minutes: int,
        status_callback: Callable[[str], None],
        stop_event: threading.Event,
    ) -> None:
        """Execute an autonomous multi-step routine."""
        self.orchestrator.start_autonomous()
        status_callback("Working")

        # Start interrupt watcher thread
        self._interrupt_watcher_stop.clear()
        self._agent_interrupted.clear()
        watcher = threading.Thread(target=self._interrupt_watcher, daemon=True)
        watcher.start()

        initial_prompt = (
            "You are now in autonomous work mode. Execute the following "
            "routine step by step.\n\n"
            f"ROUTINE: {prompt}\n\n"
            "RULES:\n"
            "1. Work through the routine one step at a time.\n"
            "2. After each step give a concise spoken summary of what you "
            "did and what you found.\n"
            "3. End your reply with the word NEXT if there are more steps, "
            "or DONE if the routine is complete.\n"
            "4. Do NOT include NEXT or DONE in the spoken summary — put it "
            "on its own final line.\n"
        )

        deadline = time.time() + max_minutes * 60
        current_prompt = initial_prompt

        for step in range(1, max_steps + 1):
            if stop_event.is_set():
                break

            if time.time() >= deadline:
                logging.info("Autonomous mode: time limit reached")
                self.tts.speak("I've hit the time limit. Here's where I got to.")
                break

            logging.info("Autonomous step %d/%d", step, max_steps)
            status_callback(f"Working ({step}/{max_steps})")

            # Pre-step interrupt check
            if self._check_hotkey_interrupt(f"before step {step}"):
                self._exit_autonomous(status_callback)
                return
            pre_snippet = self.stt.transcribe_once(INTERRUPT_LISTEN_SEC)
            if pre_snippet and self._is_interrupt_phrase(pre_snippet):
                logging.info("Autonomous mode: interrupt before step %d", step)
                self._exit_autonomous(status_callback)
                return

            reply = self.orchestrator.send_to_agent(current_prompt, keep_state=True)

            # Check if agent was cancelled mid-flight by the watcher
            if self._agent_interrupted.is_set():
                logging.info("Autonomous mode: agent cancelled mid-flight at step %d", step)
                self.orchestrator.interrupt_event.clear()
                self._agent_interrupted.clear()
                self._exit_autonomous(status_callback)
                return

            if not reply:
                logging.info("Autonomous mode: empty reply at step %d", step)
                self.tts.speak("I didn't get a response. Stopping.")
                break

            # Strip the DONE / NEXT marker before speaking
            spoken_text, is_done = self._strip_marker(reply)
            logging.info("Autonomous reply (step %d): %s", step, reply)

            interrupted = self._speak_interruptible(spoken_text)
            if interrupted:
                logging.info("Autonomous mode: user interrupted at step %d", step)
                self._exit_autonomous(status_callback)
                return

            if is_done:
                logging.info("Autonomous mode: agent signalled DONE at step %d", step)
                self.tts.speak("All done with that routine.")
                break

            # Inter-step interrupt check
            if self._check_hotkey_interrupt("between steps"):
                self._exit_autonomous(status_callback)
                return
            snippet = self.stt.transcribe_once(INTERRUPT_LISTEN_SEC)
            if snippet and self._is_interrupt_phrase(snippet):
                logging.info("Autonomous mode: interrupt phrase between steps")
                self._exit_autonomous(status_callback)
                return

            current_prompt = "Continue with the next step. Report your progress."
        else:
            # max_steps reached without DONE
            logging.info("Autonomous mode: max steps reached")
            self.tts.speak("I've completed the maximum number of steps.")

        self.orchestrator.stop_autonomous()
        self._stop_interrupt_watcher()
        status_callback("Idle")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _exit_autonomous(self, status_callback: Callable[[str], None]) -> None:
        """Common cleanup when exiting autonomous mode early."""
        self.tts.speak("Stopping autonomous mode. We can keep chatting.")
        self.orchestrator.stop_autonomous()
        self._stop_interrupt_watcher()
        status_callback("Conversation")

    def _check_hotkey_interrupt(self, context: str) -> bool:
        """Return ``True`` and clear the event if the hotkey interrupt fired."""
        if self.orchestrator.interrupt_event.is_set():
            logging.info("Autonomous mode: hotkey interrupt %s", context)
            self.orchestrator.interrupt_event.clear()
            return True
        return False

    @staticmethod
    def _is_interrupt_phrase(snippet: str) -> bool:
        normalized = snippet.lower().strip()
        return any(p in normalized for p in INTERRUPT_PHRASES)

    @staticmethod
    def _strip_marker(reply: str) -> tuple[str, bool]:
        """Strip DONE / NEXT marker from the agent's reply.

        Returns ``(spoken_text, is_done)``.
        """
        is_done = False
        spoken_text = reply
        for marker in ("DONE", "NEXT"):
            lines = spoken_text.rstrip().rsplit("\n", 1)
            if len(lines) > 1 and lines[-1].strip().upper() == marker:
                spoken_text = lines[0].rstrip()
                if marker == "DONE":
                    is_done = True
            elif spoken_text.rstrip().upper().endswith(marker):
                spoken_text = spoken_text.rstrip()[: -len(marker)].rstrip()
                if marker == "DONE":
                    is_done = True
        return spoken_text, is_done

    def _interrupt_watcher(self) -> None:
        """Poll interrupt_event at high frequency and cancel the agent."""
        while not self._interrupt_watcher_stop.is_set():
            if self.orchestrator.interrupt_event.is_set():
                logging.info("Interrupt watcher: firing agent cancel")
                self._agent_interrupted.set()
                self.orchestrator.cancel_agent()
                return
            self._interrupt_watcher_stop.wait(timeout=0.15)

    def _stop_interrupt_watcher(self) -> None:
        self._interrupt_watcher_stop.set()
        self._agent_interrupted.clear()
