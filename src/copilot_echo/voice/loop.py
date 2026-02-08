from __future__ import annotations

import logging
import re
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