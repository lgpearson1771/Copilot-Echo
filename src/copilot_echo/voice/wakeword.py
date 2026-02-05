from __future__ import annotations

import logging
import time
from typing import Iterable

import numpy as np
import sounddevice as sd

from copilot_echo.voice.audio import resolve_input_device
from copilot_echo.voice.stt import SpeechToText


class WakeWordDetector:
    def __init__(
        self,
        engine: str,
        phrase: str,
        stt: SpeechToText,
        listen_seconds: float,
        sample_rate: int,
        audio_device: int | None,
        audio_device_name: str | None,
        model_paths: Iterable[str] | None,
        threshold: float,
        chunk_size: int,
        holdoff_seconds: float,
    ) -> None:
        self.engine = engine
        self.phrase = phrase.lower().strip()
        self.stt = stt
        self.listen_seconds = listen_seconds
        self.sample_rate = sample_rate
        self.audio_device = resolve_input_device(audio_device, audio_device_name)
        self.model_paths = list(model_paths or [])
        self.threshold = threshold
        self.chunk_size = chunk_size
        self.holdoff_seconds = holdoff_seconds
        self._last_trigger = 0.0
        self._model = None

        if self.engine == "openwakeword":
            from openwakeword.model import Model

            if self.model_paths:
                self._model = Model(wakeword_models=self.model_paths)
            else:
                self._model = Model()

    def listen_until_detected(self, stop_event) -> bool:
        if self.engine == "openwakeword":
            return self._listen_openwakeword(stop_event)
        return self._listen_stt(stop_event)

    def _listen_stt(self, stop_event) -> bool:
        if stop_event.is_set():
            return False
        text = self.stt.transcribe_once(self.listen_seconds)
        logging.info("Wake check transcript: %s", text if text else "<empty>")
        return self.phrase in text.lower()

    def _listen_openwakeword(self, stop_event) -> bool:
        if not self._model:
            logging.error("Openwakeword model not initialized")
            return False

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=self.chunk_size,
            device=self.audio_device,
        ) as stream:
            while not stop_event.is_set():
                audio, _ = stream.read(self.chunk_size)
                samples = np.squeeze(audio)
                if samples.size == 0:
                    continue

                predictions = self._model.predict(samples)
                if self._is_triggered(predictions):
                    logging.info("Wake word detected (openwakeword)")
                    return True

        return False

    def _is_triggered(self, predictions) -> bool:
        now = time.time()
        if now - self._last_trigger < self.holdoff_seconds:
            return False

        if isinstance(predictions, dict):
            for score in predictions.values():
                if score >= self.threshold:
                    self._last_trigger = now
                    return True
        return False
