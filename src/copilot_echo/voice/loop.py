from __future__ import annotations

import logging
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
            status_callback("Listening")
            text = self.stt.transcribe_once(self.config.voice.command_listen_seconds)
            normalized = text.lower().strip() if text else ""
            if "stop listening" in normalized:
                logging.info("Stop listening command detected")
                self.tts.speak("Pausing listening.")
                self.orchestrator.pause()
                status_callback("Paused")
                continue
            if "resume listening" in normalized:
                logging.info("Resume listening command detected while active")
                self.tts.speak("Already listening.")
                self.orchestrator.resume()
                continue
            if text:
                logging.info("Transcript: %s", text)
                self.tts.speak(f"You said: {text}")
            else:
                logging.info("Transcript: <empty>")
                self.tts.speak("I did not catch that.")
            if self.config.voice.post_tts_cooldown_seconds > 0:
                time.sleep(self.config.voice.post_tts_cooldown_seconds)
            self.orchestrator.resume()