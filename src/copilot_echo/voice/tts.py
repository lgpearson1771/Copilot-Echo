from __future__ import annotations

import logging
import re
import time

import pyttsx3


class TextToSpeech:
    def __init__(self) -> None:
        self._voice_id: str | None = None

    def _build_engine(self) -> pyttsx3.Engine:
        engine = pyttsx3.init()
        if self._voice_id:
            engine.setProperty("voice", self._voice_id)
        return engine

    def speak(self, text: str) -> None:
        logging.info("TTS speak: %s", text)
        engine = self._build_engine()
        try:
            engine.say(text)
            engine.runAndWait()
        except Exception:
            logging.exception("TTS failed during playback")
        finally:
            try:
                engine.stop()
            except Exception:
                logging.debug("TTS stop failed during cleanup")


# ------------------------------------------------------------------
# Interruptible speaker — speaks sentence-by-sentence, checking for
# user interrupts between each.
# ------------------------------------------------------------------

INTERRUPT_PHRASES = ["stop", "let me interrupt", "listen up"]
INTERRUPT_LISTEN_SEC = 1.0


class InterruptibleSpeaker:
    """Wraps TTS + STT to speak with per-sentence interrupt support."""

    def __init__(self, tts: TextToSpeech, stt, orchestrator, config) -> None:
        self.tts = tts
        self.stt = stt
        self.orchestrator = orchestrator
        self.config = config

    def speak(self, text: str) -> bool:
        """Speak *text* sentence-by-sentence with interrupt-phrase checks.

        Returns ``True`` if the user interrupted, ``False`` if finished
        speaking normally.
        """
        sentences = [s.strip() for s in re.split(r"(?<=[.!?;:])\s+", text) if s.strip()]
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
            snippet = self.stt.transcribe_once(INTERRUPT_LISTEN_SEC)
            if snippet:
                normalized = snippet.lower().strip()
                if any(phrase in normalized for phrase in INTERRUPT_PHRASES):
                    logging.info(
                        "Interrupt phrase detected ('%s'), stopping playback.",
                        snippet,
                    )
                    self.tts.speak("Go ahead.")
                    if self.config.voice.post_tts_cooldown_seconds > 0:
                        time.sleep(self.config.voice.post_tts_cooldown_seconds)
                    return True

        return False
