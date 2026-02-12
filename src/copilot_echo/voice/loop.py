from __future__ import annotations

import logging
import time
from collections.abc import Callable

from copilot_echo.config import Config
from copilot_echo.errors import DeviceDisconnectedError
from copilot_echo.orchestrator import Orchestrator, State
from copilot_echo.voice.autonomous import AutonomousRunner
from copilot_echo.voice.commands import VoiceCommandHandler
from copilot_echo.voice.stt import SpeechToText
from copilot_echo.voice.tts import InterruptibleSpeaker, TextToSpeech, speak_error
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
        self.tts = TextToSpeech(
            voice=config.voice.tts_voice,
            rate=config.voice.tts_rate,
            volume=config.voice.tts_volume,
        )
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

        # Composed helpers
        self._interruptible = InterruptibleSpeaker(
            self.tts, self.stt, self.orchestrator, self.config
        )
        self._commands = VoiceCommandHandler(
            self.config, self.orchestrator, self.tts
        )
        self._autonomous = AutonomousRunner(
            self.config,
            self.orchestrator,
            self.stt,
            self.tts,
            self._interruptible.speak,
        )

    def run(self, status_callback: Callable[[str], None], stop_event) -> None:
        # Notify user if the agent failed during startup
        if self.orchestrator.last_error:
            speak_error(
                self.tts,
                "Warning: I couldn't connect to the Copilot agent. "
                "Some features may not work.",
            )

        while not stop_event.is_set():
            try:
                self._run_iteration(status_callback, stop_event)
            except DeviceDisconnectedError:
                self._handle_device_disconnect(status_callback, stop_event)
            except Exception:
                logging.exception("Voice loop encountered an unexpected error")
                speak_error(
                    self.tts,
                    "Something went wrong with the voice system. Restarting.",
                )
                # Reset orchestrator to a safe state before retrying
                if self.orchestrator.state not in (State.PAUSED, State.IDLE):
                    self.orchestrator.state = State.IDLE
                time.sleep(2)

    # ------------------------------------------------------------------
    # Single iteration of the main loop (extracted for error handling)
    # ------------------------------------------------------------------

    def _run_iteration(
        self, status_callback: Callable[[str], None], stop_event
    ) -> None:
        if self.orchestrator.state == State.PAUSED:
            # Auto-paused by call detector: silence the mic completely.
            if self.orchestrator.is_auto_paused:
                status_callback("Paused (Call)")
                time.sleep(0.5)
                return

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
            return

        status_callback("Idle")
        if not self.wakeword.listen_until_detected(stop_event):
            return

        self.orchestrator.on_wake_word()
        logging.info("Wake word detected")
        self._conversation_loop(status_callback, stop_event)

    # ------------------------------------------------------------------
    # Device recovery
    # ------------------------------------------------------------------

    def _handle_device_disconnect(
        self, status_callback: Callable[[str], None], stop_event
    ) -> None:
        """Poll until the audio device is available again, then resume."""
        logging.warning("Audio device disconnected")
        speak_error(
            self.tts, "Microphone disconnected. I'll try to reconnect."
        )
        status_callback("No Mic")

        # Make sure we're in a clean state
        if self.orchestrator.state == State.AUTONOMOUS:
            self.orchestrator.stop_autonomous()
        elif self.orchestrator.state not in (State.PAUSED, State.IDLE):
            self.orchestrator.state = State.IDLE

        import sounddevice as sd

        from copilot_echo.voice.audio import resolve_input_device

        while not stop_event.is_set():
            time.sleep(3)
            try:
                new_device = resolve_input_device(
                    self.config.voice.audio_device,
                    self.config.voice.audio_device_name,
                )
                # Validate the device by briefly opening a stream
                test = sd.InputStream(
                    device=new_device,
                    samplerate=self.config.voice.sample_rate,
                    channels=1,
                    dtype="float32",
                )
                test.start()
                test.stop()
                test.close()

                # Success — update both consumers
                self.stt.audio_device = new_device
                self.wakeword.audio_device = new_device
                logging.info("Audio device reconnected (index=%s)", new_device)
                speak_error(self.tts, "Microphone reconnected.")
                return
            except Exception:
                logging.debug("Device still unavailable, retrying…")

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
                logging.info("Silence timeout reached")
                break

            # -- Project knowledge base commands --
            if self._commands.handle(normalized, text):
                deadline = time.time() + window
                if self.config.voice.post_tts_cooldown_seconds > 0:
                    time.sleep(self.config.voice.post_tts_cooldown_seconds)
                continue

            # -- Autonomous mode triggers --
            if self._autonomous.check_trigger(
                normalized, text, status_callback, stop_event
            ):
                return

            logging.info("Transcript: %s", text)
            status_callback("Processing")

            reply = self.orchestrator.send_to_agent(text)

            if reply:
                logging.info("Agent reply: %s", reply)
                interrupted = self._interruptible.speak(reply)
                if interrupted:
                    deadline = time.time() + window
                    continue
            else:
                logging.info("Agent reply: <empty>")
                self.tts.speak("I didn't get a response.")

            if self.config.voice.post_tts_cooldown_seconds > 0:
                time.sleep(self.config.voice.post_tts_cooldown_seconds)

            deadline = time.time() + window

        logging.info("Conversation window expired, returning to wake word mode")
        self.orchestrator.resume()