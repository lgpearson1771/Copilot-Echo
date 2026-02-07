from __future__ import annotations

import logging
from typing import Callable

import pyttsx3


class TextToSpeech:
    def __init__(self) -> None:
        self._voice_id: str | None = None
        self._engine: pyttsx3.Engine | None = None

    def _build_engine(self) -> pyttsx3.Engine:
        engine = pyttsx3.init()
        if self._voice_id:
            engine.setProperty("voice", self._voice_id)
        return engine

    def speak(self, text: str, interrupt_check: Callable[[], bool] | None = None) -> bool:
        """Speak text with optional interrupt checking.
        
        Returns True if completed, False if interrupted.
        """
        logging.info("TTS speak: %s", text)
        self._engine = self._build_engine()
        try:
            self._engine.say(text)
            
            # If interrupt checking is enabled, poll during speech
            if interrupt_check:
                # Split into smaller chunks and check between them
                self._engine.startLoop(False)
                interrupted = False
                while self._engine.isBusy():
                    self._engine.iterate()
                    if interrupt_check():
                        logging.info("TTS interrupted")
                        self._engine.stop()
                        interrupted = True
                        break
                self._engine.endLoop()
                return not interrupted
            else:
                self._engine.runAndWait()
                return True
        except Exception:
            logging.exception("TTS failed during playback")
            return False
        finally:
            try:
                if self._engine:
                    self._engine.stop()
                    self._engine = None
            except Exception:
                logging.debug("TTS stop failed during cleanup")

    def stop(self) -> None:
        """Immediately stop any ongoing speech."""
        if self._engine:
            try:
                self._engine.stop()
            except Exception:
                logging.debug("TTS stop failed")
