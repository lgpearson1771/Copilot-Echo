from __future__ import annotations

import pyttsx3


class TextToSpeech:
    def __init__(self) -> None:
        self.engine = pyttsx3.init()

    def speak(self, text: str) -> None:
        self.engine.say(text)
        self.engine.runAndWait()
