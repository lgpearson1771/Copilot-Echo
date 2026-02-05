from __future__ import annotations

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

from copilot_echo.voice.audio import resolve_input_device


class SpeechToText:
    def __init__(
        self,
        model_name: str,
        device: str,
        compute_type: str,
        sample_rate: int,
        audio_device: int | None,
    ) -> None:
        self.model = WhisperModel(model_name, device=device, compute_type=compute_type)
        self.sample_rate = sample_rate
        self.audio_device = resolve_input_device(audio_device, None)

    def transcribe_once(self, duration_sec: float) -> str:
        audio = sd.rec(
            int(duration_sec * self.sample_rate),
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            device=self.audio_device,
        )
        sd.wait()

        samples = np.squeeze(audio)
        segments, _ = self.model.transcribe(samples, language="en", vad_filter=True)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return text
