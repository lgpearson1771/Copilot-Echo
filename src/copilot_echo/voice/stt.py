from __future__ import annotations

import logging
import time

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
        """Record for a fixed duration and transcribe.  Used for simple
        wake-word / resume-listening checks where VAD isn't needed."""
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

    def transcribe_until_silence(
        self,
        silence_timeout: float = 5.0,
        utterance_end_seconds: float = 1.5,
        max_duration: float = 60.0,
        energy_threshold: float = 0.01,
    ) -> str:
        """Stream audio and record until the user finishes speaking.

        *   If no speech is detected for *silence_timeout* seconds the
            method returns ``""`` immediately (no transcription run).
        *   Once speech is detected, recording continues until
            *utterance_end_seconds* of silence after the last speech chunk,
            then the full recording is transcribed.
        *   *max_duration* is a hard cap to prevent infinite recording.
        *   *energy_threshold* is the RMS level (on float32 [-1, 1] audio)
            above which a chunk counts as speech.
        """
        chunk_duration = 0.1  # 100 ms per chunk
        chunk_samples = int(chunk_duration * self.sample_rate)
        chunks: list[np.ndarray] = []
        speech_detected = False
        last_speech_time = time.time()
        start_time = last_speech_time

        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=chunk_samples,
                device=self.audio_device,
            ) as stream:
                while True:
                    now = time.time()

                    # Hard time limit
                    if now - start_time >= max_duration:
                        logging.info("Reached max recording duration (%.0fs)", max_duration)
                        break

                    audio, _ = stream.read(chunk_samples)
                    chunks.append(audio.copy())

                    rms = float(np.sqrt(np.mean(audio ** 2)))

                    if rms > energy_threshold:
                        speech_detected = True
                        last_speech_time = now

                    silence_duration = now - last_speech_time

                    if speech_detected:
                        # Speech started — stop after utterance_end gap
                        if silence_duration >= utterance_end_seconds:
                            logging.debug(
                                "End-of-utterance silence (%.1fs)", silence_duration
                            )
                            break
                    else:
                        # No speech yet — honour silence_timeout
                        if silence_duration >= silence_timeout:
                            logging.debug(
                                "No speech detected for %.1fs", silence_duration
                            )
                            return ""
        except Exception:
            logging.exception("Error during VAD recording")
            return ""

        if not chunks:
            return ""

        samples = np.concatenate(chunks)
        samples = np.squeeze(samples)
        segments, _ = self.model.transcribe(samples, language="en", vad_filter=True)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return text
