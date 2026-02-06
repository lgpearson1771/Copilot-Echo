from __future__ import annotations

import logging

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
