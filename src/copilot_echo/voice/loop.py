from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from copilot_echo.config import Config
from copilot_echo.orchestrator import Orchestrator, State
from copilot_echo.voice.stt import SpeechToText
from copilot_echo.voice.tts import TextToSpeech
from copilot_echo.voice.wakeword import WakeWordDetector


class VoiceLoop:
    def __init__(self, config: Config, orchestrator: Orchestrator) -> None:
        self.config = config
        self.orchestrator = orchestrator
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
            self.orchestrator.clear_interrupt()
            logging.info("Wake word detected")
            self._conversation_loop(status_callback, stop_event)

    def _conversation_loop(
        self, status_callback: Callable[[str], None], stop_event
    ) -> None:
        """Stay in conversation mode, listening without wake word, until
        timeout or 'stop listening' command.

        While the agent is processing or TTS is speaking, a background
        thread monitors for the wake word so the user can interrupt and
        redirect immediately by saying the wake phrase again.
        """
        window = self.config.voice.conversation_window_seconds
        deadline = time.time() + window
        logging.info("Entering conversation mode (%.0fs window)", window)
        status_callback("Conversation")

        while not stop_event.is_set() and time.time() < deadline:
            text = self.stt.transcribe_once(self.config.voice.command_listen_seconds)
            normalized = text.lower().strip() if text else ""

            # Check for interrupt command (spoken during STT recording)
            if any(phrase in normalized for phrase in ["stop", "cancel", "never mind"]):
                logging.info("Interrupt command detected")
                self.orchestrator.request_interrupt()
                self.tts.stop()
                self.tts.speak("Okay, stopped.")
                deadline = time.time() + window
                if self.config.voice.post_tts_cooldown_seconds > 0:
                    time.sleep(self.config.voice.post_tts_cooldown_seconds)
                continue

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
                logging.info("Transcript: <empty>")
                continue

            logging.info("Transcript: %s", text)
            status_callback("Processing")
            self.orchestrator.clear_interrupt()

            # ------ Interruptible agent call ------
            # Monitor for wake word in a background thread so the user
            # can say the wake phrase to interrupt while the agent thinks.
            interrupt_event = threading.Event()
            monitor_stop = threading.Event()

            monitor_thread = threading.Thread(
                target=self.wakeword.monitor_for_interrupt,
                args=(monitor_stop, interrupt_event),
                daemon=True,
            )
            monitor_thread.start()

            reply_box: list[str | None] = [None]

            def _agent_worker() -> None:
                reply_box[0] = self.orchestrator.send_to_agent(text)

            agent_thread = threading.Thread(target=_agent_worker, daemon=True)
            agent_thread.start()

            # Wait for agent to finish OR wake word interrupt
            while agent_thread.is_alive():
                if interrupt_event.is_set():
                    logging.info("User interrupted during agent processing")
                    self.orchestrator.cancel_agent()
                    break
                agent_thread.join(timeout=0.1)

            monitor_stop.set()
            monitor_thread.join(timeout=2)

            if interrupt_event.is_set():
                self.tts.speak("Go ahead.")
                if self.config.voice.post_tts_cooldown_seconds > 0:
                    time.sleep(self.config.voice.post_tts_cooldown_seconds)
                deadline = time.time() + window
                continue

            reply = reply_box[0]

            # ------ Interruptible TTS ------
            if reply:
                logging.info("Agent reply: %s", reply)

                # Fresh monitor for the TTS phase
                interrupt_event = threading.Event()
                monitor_stop = threading.Event()
                monitor_thread = threading.Thread(
                    target=self.wakeword.monitor_for_interrupt,
                    args=(monitor_stop, interrupt_event),
                    daemon=True,
                )
                monitor_thread.start()

                completed = self.tts.speak(
                    reply,
                    interrupt_check=lambda: interrupt_event.is_set(),
                )

                monitor_stop.set()
                monitor_thread.join(timeout=2)

                if not completed or interrupt_event.is_set():
                    logging.info("User interrupted during TTS")
                    self.tts.speak("Go ahead.")
                    if self.config.voice.post_tts_cooldown_seconds > 0:
                        time.sleep(self.config.voice.post_tts_cooldown_seconds)
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