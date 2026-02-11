from __future__ import annotations

import logging
import re
import threading
import time
from typing import Callable

from copilot_echo.config import Config
from copilot_echo.orchestrator import Orchestrator, State
from copilot_echo.voice.stt import SpeechToText
from copilot_echo.voice.tts import TextToSpeech
from copilot_echo.voice.wakeword import WakeWordDetector
from copilot_echo import projects


class VoiceLoop:
    def __init__(self, config: Config, orchestrator: Orchestrator) -> None:
        self.config = config
        self.orchestrator = orchestrator
        self._interrupt_watcher_stop = threading.Event()
        self._agent_interrupted = threading.Event()
        self.stt = SpeechToText(
            model_name=config.voice.stt_model,
            device=config.voice.stt_device,
            compute_type=config.voice.stt_compute_type,
            sample_rate=config.voice.sample_rate,
            audio_device=config.voice.audio_device,
        )
        if config.voice.audio_device_name:
            from copilot_echo.voice.audio import resolve_input_device

            resolved = resolve_input_device(
                config.voice.audio_device, config.voice.audio_device_name
            )
            self.stt.audio_device = resolved
        self.tts = TextToSpeech()
        self.wakeword = WakeWordDetector(
            engine=config.voice.wakeword_engine,
            phrase=config.voice.wake_word,
            stt=self.stt,
            listen_seconds=config.voice.wake_listen_seconds,
            sample_rate=config.voice.sample_rate,
            audio_device=config.voice.audio_device,
            audio_device_name=config.voice.audio_device_name,
            inference_framework=config.voice.wakeword_inference_framework,
            wakeword_models=config.voice.wakeword_models,
            threshold=config.voice.wakeword_threshold,
            chunk_size=config.voice.wakeword_chunk_size,
            holdoff_seconds=config.voice.wakeword_holdoff_seconds,
            vad_threshold=config.voice.wakeword_vad_threshold,
            speex_noise_suppression=config.voice.wakeword_speex_noise_suppression,
        )

    def run(self, status_callback: Callable[[str], None], stop_event) -> None:
        while not stop_event.is_set():
            if self.orchestrator.state == State.PAUSED:
                status_callback("Paused")
                text = self.stt.transcribe_once(self.config.voice.wake_listen_seconds)
                normalized = text.lower().strip() if text else ""
                logging.info("Paused transcript: %s", text if text else "<empty>")
                wake_phrase = self.config.voice.wake_word.lower().strip()
                if "resume listening" in normalized or (wake_phrase and wake_phrase in normalized):
                    logging.info("Resume listening command detected")
                    self.tts.speak("Resuming listening.")
                    self.orchestrator.resume()
                else:
                    time.sleep(0.5)
                continue

            status_callback("Idle")
            if not self.wakeword.listen_until_detected(stop_event):
                continue

            self.orchestrator.on_wake_word()
            logging.info("Wake word detected")
            self._conversation_loop(status_callback, stop_event)

    def _conversation_loop(
        self, status_callback: Callable[[str], None], stop_event
    ) -> None:
        """Stay in conversation mode, listening without wake word, until
        silence timeout or 'stop listening' command."""
        window = self.config.voice.conversation_window_seconds
        deadline = time.time() + window
        logging.info("Entering conversation mode (%.0fs window)", window)
        status_callback("Conversation")

        while not stop_event.is_set():
            # Use remaining time until deadline as the silence timeout
            # so the conversation exits only after continuous silence.
            remaining = deadline - time.time()
            if remaining <= 0:
                break

            text = self.stt.transcribe_until_silence(
                silence_timeout=remaining,
                utterance_end_seconds=self.config.voice.utterance_end_seconds,
                max_duration=self.config.voice.max_listen_seconds,
                energy_threshold=self.config.voice.stt_energy_threshold,
            )
            normalized = text.lower().strip() if text else ""

            if "stop listening" in normalized:
                logging.info("Stop listening command detected")
                self.tts.speak("Pausing listening.")
                self.orchestrator.pause()
                status_callback("Paused")
                return

            hold_phrases = ["hold on a sec", "hold on a second", "give me more time"]
            if any(phrase in normalized for phrase in hold_phrases):
                extension = 30.0
                deadline = time.time() + extension
                logging.info("Hold phrase detected, extending conversation by %.0fs", extension)
                self.tts.speak("Sure, take your time.")
                if self.config.voice.post_tts_cooldown_seconds > 0:
                    time.sleep(self.config.voice.post_tts_cooldown_seconds)
                continue

            if not text:
                # No speech detected — silence_timeout elapsed inside
                # transcribe_until_silence, so we exit conversation mode.
                logging.info("Silence timeout reached")
                break

            # -- Project knowledge base commands --
            project_handled = self._handle_project_command(normalized, text)
            if project_handled:
                deadline = time.time() + window
                if self.config.voice.post_tts_cooldown_seconds > 0:
                    time.sleep(self.config.voice.post_tts_cooldown_seconds)
                continue

            # -- Autonomous mode triggers --
            autonomous_handled = self._check_autonomous_trigger(
                normalized, text, status_callback, stop_event,
            )
            if autonomous_handled:
                # After autonomous mode ends we return to wake word mode.
                return

            logging.info("Transcript: %s", text)
            status_callback("Processing")

            reply = self.orchestrator.send_to_agent(text)

            if reply:
                logging.info("Agent reply: %s", reply)
                interrupted = self._speak_interruptible(reply)
                if interrupted:
                    deadline = time.time() + window
                    continue
            else:
                logging.info("Agent reply: <empty>")
                self.tts.speak("I didn't get a response.")

            if self.config.voice.post_tts_cooldown_seconds > 0:
                time.sleep(self.config.voice.post_tts_cooldown_seconds)

            # Reset the conversation window after each interaction
            deadline = time.time() + window

        logging.info("Conversation window expired, returning to wake word mode")
        self.orchestrator.resume()

    # ------------------------------------------------------------------
    # Project knowledge base voice commands
    # ------------------------------------------------------------------

    _START_PATTERNS = [
        re.compile(r"start a project (?:called |named )?(.+)", re.IGNORECASE),
        re.compile(r"create a project (?:called |named )?(.+)", re.IGNORECASE),
        re.compile(r"new project (?:called |named )?(.+)", re.IGNORECASE),
    ]
    _FINISH_PATTERNS = [
        re.compile(r"(?:finish|close|complete|end) (?:the )?project (?:called |named )?(.+)", re.IGNORECASE),
        re.compile(r"archive (?:the )?project (?:called |named )?(.+)", re.IGNORECASE),
    ]
    _LIST_PHRASES = ["list my projects", "list projects", "show my projects", "what projects do i have"]

    def _handle_project_command(self, normalized: str, original: str) -> bool:
        """Check for project-related voice commands.  Returns True if handled."""
        # List projects
        if any(phrase in normalized for phrase in self._LIST_PHRASES):
            return self._cmd_list_projects()

        # Start a project — match against original text to preserve casing
        for pat in self._START_PATTERNS:
            m = pat.search(original)
            if m:
                name = self._extract_project_name(m.group(1).strip())
                return self._cmd_start_project(name)

        # Finish / archive a project
        for pat in self._FINISH_PATTERNS:
            m = pat.search(original)
            if m:
                name = self._extract_project_name(m.group(1).strip())
                return self._cmd_finish_project(name)

        return False

    def _extract_project_name(self, raw_name: str) -> str:
        """Use the agent to extract a clean project name from raw speech.

        Sends a short prompt asking the LLM to strip conversational filler
        and return just the project name.  Falls back to *raw_name* if the
        agent is unavailable or returns something unusable.
        """
        prompt = (
            "The user said the following when creating or referencing a project. "
            "Extract ONLY the short project name — remove any conversational "
            "filler like 'for me about the', 'about', 'the one for', etc. "
            "Return ONLY the project name, nothing else. No quotes, no "
            "explanation.\n\n"
            f"User said: \"{raw_name}\""
        )
        try:
            reply = self.orchestrator.send_to_agent(prompt)
            cleaned = reply.strip().strip('"').strip("'").strip() if reply else ""
            if cleaned and len(cleaned) < len(raw_name) * 2:
                logging.info(
                    "Agent extracted project name: '%s' (from '%s')",
                    cleaned, raw_name,
                )
                return cleaned
        except Exception:
            logging.debug("Agent name extraction failed, using raw name", exc_info=True)
        return raw_name

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
                parts = []
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
    # Autonomous "Get to Work" mode
    # ------------------------------------------------------------------

    _AD_HOC_PATTERN = re.compile(
        r"(?:get to work|start working|work) on (.+)", re.IGNORECASE
    )

    def _check_autonomous_trigger(
        self,
        normalized: str,
        original: str,
        status_callback: Callable[[str], None],
        stop_event,
    ) -> bool:
        """Return True and run autonomous loop if *text* matches a trigger."""
        routines = self.config.agent.autonomous_routines

        # 1. Check pre-configured routine trigger phrases
        for routine in routines:
            for phrase in routine.trigger_phrases:
                if phrase.lower() in normalized:
                    logging.info(
                        "Autonomous routine triggered: %s (phrase='%s')",
                        routine.name, phrase,
                    )
                    max_steps = (
                        routine.max_steps
                        if routine.max_steps is not None
                        else self.config.agent.autonomous_max_steps
                    )
                    self.tts.speak(f"Starting routine: {routine.name}.")
                    self._autonomous_loop(
                        routine.prompt,
                        max_steps,
                        self.config.agent.autonomous_max_minutes,
                        status_callback,
                        stop_event,
                    )
                    return True

        # 2. Ad-hoc "get to work on {task}" support
        m = self._AD_HOC_PATTERN.search(original)
        if m:
            task = m.group(1).strip()
            logging.info("Ad-hoc autonomous task: %s", task)
            self.tts.speak(f"Got it, working on: {task}.")
            self._autonomous_loop(
                task,
                self.config.agent.autonomous_max_steps,
                self.config.agent.autonomous_max_minutes,
                status_callback,
                stop_event,
            )
            return True

        return False

    def _autonomous_loop(
        self,
        prompt: str,
        max_steps: int,
        max_minutes: int,
        status_callback: Callable[[str], None],
        stop_event,
    ) -> None:
        """Execute an autonomous multi-step routine.

        The agent is given a system-level instruction to work step by step
        and signal progress with ``NEXT`` (more to do) or ``DONE`` (finished)
        at the end of each reply.  The loop continues until DONE, a hard
        limit is hit, or the user interrupts.
        """
        self.orchestrator.start_autonomous()
        status_callback("Working")

        # Start a background watcher that cancels the agent mid-flight
        # when the interrupt event is set (hotkey / tray Stop).
        self._interrupt_watcher_stop.clear()
        self._agent_interrupted.clear()
        watcher = threading.Thread(
            target=self._interrupt_watcher,
            daemon=True,
        )
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
                self.tts.speak(
                    "I've hit the time limit. Here's where I got to."
                )
                break

            logging.info("Autonomous step %d/%d", step, max_steps)
            status_callback(f"Working ({step}/{max_steps})")

            # Pre-step interrupt check — the agent call can take 10-30s
            # so give the user a chance to bail out before we send.
            if self.orchestrator.interrupt_event.is_set():
                logging.info("Autonomous mode: hotkey interrupt before step %d", step)
                self.orchestrator.interrupt_event.clear()
                self.tts.speak(
                    "Stopping autonomous mode. We can keep chatting."
                )
                self.orchestrator.stop_autonomous()
                self._stop_interrupt_watcher()
                status_callback("Conversation")
                return
            pre_snippet = self.stt.transcribe_once(self._INTERRUPT_LISTEN_SEC)
            if pre_snippet:
                pre_norm = pre_snippet.lower().strip()
                if any(p in pre_norm for p in self._INTERRUPT_PHRASES):
                    logging.info("Autonomous mode: interrupt before step %d", step)
                    self.tts.speak(
                        "Stopping autonomous mode. We can keep chatting."
                    )
                    self.orchestrator.stop_autonomous()
                    status_callback("Conversation")
                    return

            reply = self.orchestrator.send_to_agent(
                current_prompt, keep_state=True,
            )

            # Check if the agent was cancelled mid-flight by the watcher
            if self._agent_interrupted.is_set():
                logging.info("Autonomous mode: agent cancelled mid-flight at step %d", step)
                self.orchestrator.interrupt_event.clear()
                self._agent_interrupted.clear()
                self.tts.speak(
                    "Stopping autonomous mode. We can keep chatting."
                )
                self.orchestrator.stop_autonomous()
                self._stop_interrupt_watcher()
                status_callback("Conversation")
                return

            if not reply:
                logging.info("Autonomous mode: empty reply at step %d", step)
                self.tts.speak("I didn't get a response. Stopping.")
                break

            # Strip the DONE / NEXT marker before speaking
            is_done = False
            spoken_text = reply
            for marker in ("DONE", "NEXT"):
                # Check last line for marker
                lines = spoken_text.rstrip().rsplit("\n", 1)
                if len(lines) > 1 and lines[-1].strip().upper() == marker:
                    spoken_text = lines[0].rstrip()
                    if marker == "DONE":
                        is_done = True
                elif spoken_text.rstrip().upper().endswith(marker):
                    spoken_text = spoken_text.rstrip()[: -len(marker)].rstrip()
                    if marker == "DONE":
                        is_done = True

            logging.info("Autonomous reply (step %d): %s", step, reply)

            interrupted = self._speak_interruptible(spoken_text)
            if interrupted:
                logging.info("Autonomous mode: user interrupted at step %d", step)
                self.tts.speak(
                    "Stopping autonomous mode. We can keep chatting."
                )
                self.orchestrator.stop_autonomous()
                self._stop_interrupt_watcher()
                status_callback("Conversation")
                return  # fall back to conversation loop caller

            if is_done:
                logging.info("Autonomous mode: agent signalled DONE at step %d", step)
                self.tts.speak("All done with that routine.")
                break

            # Inter-step listen for user interruption
            if self.orchestrator.interrupt_event.is_set():
                logging.info("Autonomous mode: hotkey interrupt between steps")
                self.orchestrator.interrupt_event.clear()
                self.tts.speak(
                    "Stopping autonomous mode. We can keep chatting."
                )
                self.orchestrator.stop_autonomous()
                self._stop_interrupt_watcher()
                status_callback("Conversation")
                return
            snippet = self.stt.transcribe_once(self._INTERRUPT_LISTEN_SEC)
            if snippet:
                snippet_norm = snippet.lower().strip()
                if any(p in snippet_norm for p in self._INTERRUPT_PHRASES):
                    logging.info("Autonomous mode: interrupt phrase between steps")
                    self.tts.speak(
                        "Stopping autonomous mode. We can keep chatting."
                    )
                    self.orchestrator.stop_autonomous()
                    self._stop_interrupt_watcher()
                    status_callback("Conversation")
                    return

            current_prompt = "Continue with the next step. Report your progress."
        else:
            # max_steps reached without DONE
            logging.info("Autonomous mode: max steps reached")
            self.tts.speak("I've completed the maximum number of steps.")

        self.orchestrator.stop_autonomous()
        self._stop_interrupt_watcher()
        self._stop_interrupt_watcher()
        status_callback("Idle")

    def _interrupt_watcher(self) -> None:
        """Poll interrupt_event at high frequency and cancel the agent.

        Runs on a daemon thread while autonomous mode is active.
        When the interrupt fires, it cancels any in-flight agent request
        and sets ``_agent_interrupted`` so the autonomous loop can break
        at the next check.
        """
        while not self._interrupt_watcher_stop.is_set():
            if self.orchestrator.interrupt_event.is_set():
                logging.info("Interrupt watcher: firing agent cancel")
                self._agent_interrupted.set()
                self.orchestrator.cancel_agent()
                # Don't clear interrupt_event here — let the loop do it
                # so it can speak the exit message.
                return
            self._interrupt_watcher_stop.wait(timeout=0.15)

    def _stop_interrupt_watcher(self) -> None:
        self._interrupt_watcher_stop.set()
        self._agent_interrupted.clear()

    # ------------------------------------------------------------------
    # Interruptible TTS — speak sentence-by-sentence, listening briefly
    # between each for interrupt phrases via STT.
    # ------------------------------------------------------------------

    _INTERRUPT_PHRASES = ["stop", "let me interrupt", "listen up"]
    _INTERRUPT_LISTEN_SEC = 1.0  # seconds to record between sentences

    def _speak_interruptible(self, text: str) -> bool:
        """Speak *text* sentence-by-sentence with interrupt-phrase checks.

        Returns ``True`` if the user interrupted, ``False`` if finished
        speaking normally.
        """
        sentences = [s.strip() for s in re.split(r'(?<=[.!?;:])\s+', text) if s.strip()]
        if not sentences:
            return False

        for i, sentence in enumerate(sentences):
            self.tts.speak(sentence)

            # After the last sentence there's nothing left to interrupt.
            if i >= len(sentences) - 1:
                break

            # Check for hotkey interrupt (instant, no mic needed)
            if self.orchestrator.interrupt_event.is_set():
                logging.info("Hotkey interrupt detected during TTS playback.")
                self.orchestrator.interrupt_event.clear()
                self.tts.speak("Go ahead.")
                if self.config.voice.post_tts_cooldown_seconds > 0:
                    time.sleep(self.config.voice.post_tts_cooldown_seconds)
                return True

            # Brief listen for an interrupt command between sentences.
            snippet = self.stt.transcribe_once(self._INTERRUPT_LISTEN_SEC)
            if snippet:
                normalized = snippet.lower().strip()
                if any(phrase in normalized for phrase in self._INTERRUPT_PHRASES):
                    logging.info(
                        "Interrupt phrase detected ('%s'), stopping playback.",
                        snippet,
                    )
                    self.tts.speak("Go ahead.")
                    if self.config.voice.post_tts_cooldown_seconds > 0:
                        time.sleep(self.config.voice.post_tts_cooldown_seconds)
                    return True

        return False