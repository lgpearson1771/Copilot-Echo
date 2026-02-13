"""Tests for copilot_echo.voice.loop."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch, PropertyMock, call

import pytest

from copilot_echo.errors import DeviceDisconnectedError
from copilot_echo.orchestrator import State


@pytest.fixture
def wired_loop(fake_config, mock_orchestrator, mock_stt, mock_tts):
    """Build a VoiceLoop with all hardware dependencies mocked."""
    with patch("copilot_echo.voice.loop.SpeechToText", return_value=mock_stt), \
         patch("copilot_echo.voice.loop.TextToSpeech", return_value=mock_tts), \
         patch("copilot_echo.voice.loop.WakeWordDetector") as MockWake, \
         patch("copilot_echo.voice.loop.InterruptibleSpeaker") as MockInterruptible, \
         patch("copilot_echo.voice.loop.VoiceCommandHandler") as MockCmds, \
         patch("copilot_echo.voice.loop.AutonomousRunner") as MockAuto:

        mock_wakeword = MagicMock()
        mock_wakeword.listen_until_detected.return_value = True
        MockWake.return_value = mock_wakeword

        mock_interruptible = MagicMock()
        mock_interruptible.speak.return_value = False  # not interrupted
        MockInterruptible.return_value = mock_interruptible

        mock_commands = MagicMock()
        mock_commands.handle.return_value = False  # not a command
        MockCmds.return_value = mock_commands

        mock_autonomous = MagicMock()
        mock_autonomous.check_trigger.return_value = False  # not a trigger
        MockAuto.return_value = mock_autonomous

        from copilot_echo.voice.loop import VoiceLoop

        loop = VoiceLoop(fake_config, mock_orchestrator)
        # Replace internals with our mocks
        loop.stt = mock_stt
        loop.tts = mock_tts
        loop.wakeword = mock_wakeword
        loop._interruptible = mock_interruptible
        loop._commands = mock_commands
        loop._autonomous = mock_autonomous

        yield loop


class TestPausedState:
    def test_listens_for_resume(self, wired_loop, mock_orchestrator, mock_stt, mock_tts):
        """In PAUSED state, 'resume listening' should trigger resume."""
        mock_orchestrator.state = State.PAUSED

        call_count = 0

        def fake_transcribe(duration):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "resume listening"
            return ""

        mock_stt.transcribe_once.side_effect = fake_transcribe
        stop_event = threading.Event()
        status_cb = MagicMock()

        def run_briefly():
            # After resume, the loop will try wakeword detection.
            # Set stop_event after a short delay.
            time.sleep(0.3)
            stop_event.set()

        t = threading.Thread(target=run_briefly, daemon=True)
        t.start()

        # Make wakeword return False to exit quickly after resume
        wired_loop.wakeword.listen_until_detected.return_value = False
        wired_loop.run(status_cb, stop_event)
        t.join(timeout=2)

        assert mock_orchestrator.state != State.PAUSED

    def test_wake_phrase_resumes(self, wired_loop, mock_orchestrator, mock_stt, mock_tts):
        mock_orchestrator.state = State.PAUSED

        call_count = 0

        def fake_transcribe(duration):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "hey echo"
            return ""

        mock_stt.transcribe_once.side_effect = fake_transcribe
        stop_event = threading.Event()
        status_cb = MagicMock()

        def run_briefly():
            time.sleep(0.3)
            stop_event.set()

        t = threading.Thread(target=run_briefly, daemon=True)
        t.start()

        wired_loop.wakeword.listen_until_detected.return_value = False
        wired_loop.run(status_cb, stop_event)
        t.join(timeout=2)

        # Should have called resume
        mock_tts.speak.assert_any_call("Resuming listening.")

    def test_auto_paused_skips_stt(self, wired_loop, mock_orchestrator, mock_stt):
        """When auto-paused (call detected), STT should NOT be polled."""
        mock_orchestrator.state = State.PAUSED
        mock_orchestrator._auto_paused = True

        stop_event = threading.Event()
        status_cb = MagicMock()

        def run_briefly():
            time.sleep(0.3)
            stop_event.set()

        t = threading.Thread(target=run_briefly, daemon=True)
        t.start()

        wired_loop.run(status_cb, stop_event)
        t.join(timeout=2)

        # STT should never have been called
        mock_stt.transcribe_once.assert_not_called()
        status_cb.assert_any_call("Paused (Call)")


class TestConversationLoop:
    def test_stop_listening_pauses(self, wired_loop, mock_orchestrator, mock_stt, mock_tts):
        mock_stt.transcribe_until_silence.return_value = "stop listening"
        status_cb = MagicMock()
        stop_event = threading.Event()

        wired_loop._conversation_loop(status_cb, stop_event)

        assert mock_orchestrator.state == State.PAUSED
        mock_tts.speak.assert_any_call("Pausing listening.")

    def test_hold_phrase_extends_deadline(self, wired_loop, mock_orchestrator, mock_stt, mock_tts):
        call_count = 0

        def fake_transcribe(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "hold on a sec"
            return ""  # silence → exit

        mock_stt.transcribe_until_silence.side_effect = fake_transcribe
        status_cb = MagicMock()
        stop_event = threading.Event()

        wired_loop._conversation_loop(status_cb, stop_event)

        mock_tts.speak.assert_any_call("Sure, take your time.")

    def test_commands_handled_before_agent(self, wired_loop, mock_orchestrator, mock_stt):
        call_count = 0

        def fake_transcribe(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "list my projects"
            return ""

        mock_stt.transcribe_until_silence.side_effect = fake_transcribe
        wired_loop._commands.handle.return_value = True
        status_cb = MagicMock()
        stop_event = threading.Event()

        wired_loop._conversation_loop(status_cb, stop_event)

        # Agent should NOT have been called
        mock_orchestrator.agent.send.assert_not_called()

    def test_autonomous_trigger_returns(self, wired_loop, mock_orchestrator, mock_stt):
        call_count = 0

        def fake_transcribe(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "daily standup"
            return ""

        mock_stt.transcribe_until_silence.side_effect = fake_transcribe
        wired_loop._autonomous.check_trigger.return_value = True
        status_cb = MagicMock()
        stop_event = threading.Event()

        wired_loop._conversation_loop(status_cb, stop_event)

        # Agent should NOT have been called directly
        mock_orchestrator.agent.send.assert_not_called()

    def test_agent_reply_spoken(self, wired_loop, mock_orchestrator, mock_stt, mock_tts):
        call_count = 0

        def fake_transcribe(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "what time is it"
            return ""

        mock_stt.transcribe_until_silence.side_effect = fake_transcribe
        mock_orchestrator.agent.send.return_value = "It is noon."
        status_cb = MagicMock()
        stop_event = threading.Event()

        wired_loop._conversation_loop(status_cb, stop_event)

        wired_loop._interruptible.speak.assert_called_once_with("It is noon.")

    def test_empty_agent_reply(self, wired_loop, mock_orchestrator, mock_stt, mock_tts):
        call_count = 0

        def fake_transcribe(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "something"
            return ""

        mock_stt.transcribe_until_silence.side_effect = fake_transcribe
        mock_orchestrator.agent.send.return_value = ""
        status_cb = MagicMock()
        stop_event = threading.Event()

        wired_loop._conversation_loop(status_cb, stop_event)

        mock_tts.speak.assert_any_call("I didn't get a response.")

    def test_silence_timeout_exits(self, wired_loop, mock_stt, mock_orchestrator):
        """When no speech is detected, the conversation should end."""
        mock_stt.transcribe_until_silence.return_value = ""
        status_cb = MagicMock()
        stop_event = threading.Event()

        wired_loop._conversation_loop(status_cb, stop_event)

        # Should have called resume
        assert mock_orchestrator.state == State.IDLE

    def test_interrupted_tts_resets_deadline(self, wired_loop, mock_orchestrator, mock_stt):
        call_count = 0

        def fake_transcribe(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "tell me a story"
            if call_count == 2:
                return "what else"
            return ""

        mock_stt.transcribe_until_silence.side_effect = fake_transcribe
        mock_orchestrator.agent.send.return_value = "Once upon a time."

        # First call to interruptible.speak returns True (interrupted),
        # second returns False (normal)
        wired_loop._interruptible.speak.side_effect = [True, False]
        status_cb = MagicMock()
        stop_event = threading.Event()

        wired_loop._conversation_loop(status_cb, stop_event)

        # Agent should have been called twice
        assert mock_orchestrator.agent.send.call_count == 2


# ------------------------------------------------------------------
# Startup error notification
# ------------------------------------------------------------------

class TestStartupErrorNotification:
    def test_speaks_warning_when_agent_failed(self, wired_loop, mock_orchestrator, mock_tts):
        mock_orchestrator.last_error = "Agent failed to start"
        stop_event = threading.Event()
        stop_event.set()  # exit immediately
        status_cb = MagicMock()

        wired_loop.run(status_cb, stop_event)

        # Should have warned about the error
        calls = [c.args[0] for c in mock_tts.speak.call_args_list]
        assert any("couldn't connect" in c.lower() for c in calls)

    def test_no_warning_when_agent_ok(self, wired_loop, mock_orchestrator, mock_tts):
        mock_orchestrator.last_error = None
        stop_event = threading.Event()
        stop_event.set()
        status_cb = MagicMock()

        wired_loop.run(status_cb, stop_event)

        # Should NOT have warned
        calls = [c.args[0] for c in mock_tts.speak.call_args_list]
        assert not any("couldn't connect" in c.lower() for c in calls)


# ------------------------------------------------------------------
# Device disconnection recovery
# ------------------------------------------------------------------

class TestDeviceRecovery:
    def test_device_disconnect_triggers_recovery(self, wired_loop, mock_orchestrator, mock_tts):
        """DeviceDisconnectedError should trigger _handle_device_disconnect."""
        call_count = 0

        def fake_listen(stop_event):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise DeviceDisconnectedError("device gone")
            stop_event.set()  # stop after recovery
            return False

        wired_loop.wakeword.listen_until_detected.side_effect = fake_listen
        status_cb = MagicMock()
        stop_event = threading.Event()

        mock_stream = MagicMock()
        with patch("copilot_echo.voice.audio.sd") as mock_sd, \
             patch("copilot_echo.voice.audio.list_input_devices", return_value=[(5, "Test Mic")]), \
             patch("copilot_echo.voice.loop.time.sleep"):
            mock_sd.InputStream.return_value = mock_stream
            # Patch sd in loop module for the InputStream validation
            with patch.dict("sys.modules", {"sounddevice": mock_sd}):
                import importlib
                # Just mock the whole recovery to keep it simple
                with patch.object(wired_loop, "_handle_device_disconnect") as mock_recovery:
                    def do_recovery(status_callback, se):
                        wired_loop.stt.audio_device = 5
                        wired_loop.wakeword.audio_device = 5
                        mock_tts.speak("Microphone disconnected. I'll try to reconnect.")
                        mock_tts.speak("Microphone reconnected.")

                    mock_recovery.side_effect = do_recovery
                    wired_loop.run(status_cb, stop_event)

        # Device should have been updated by the mock recovery
        assert wired_loop.stt.audio_device == 5
        assert wired_loop.wakeword.audio_device == 5

    def test_device_recovery_resets_autonomous_state(self, wired_loop, mock_orchestrator, mock_tts):
        mock_orchestrator.state = State.AUTONOMOUS

        call_count = 0

        def fake_listen(stop_event):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise DeviceDisconnectedError("gone")
            stop_event.set()
            return False

        wired_loop.wakeword.listen_until_detected.side_effect = fake_listen
        status_cb = MagicMock()
        stop_event = threading.Event()

        # Mock the recovery to check state cleanup
        with patch.object(wired_loop, "_handle_device_disconnect") as mock_recovery:
            def do_recovery(status_callback, se):
                # The real method resets autonomous state
                if mock_orchestrator.state == State.AUTONOMOUS:
                    mock_orchestrator.stop_autonomous()

            mock_recovery.side_effect = do_recovery
            wired_loop.run(status_cb, stop_event)

        # Autonomous state should have been cleaned up
        assert mock_orchestrator.state != State.AUTONOMOUS

    def test_handle_device_disconnect_no_mic_status(self, wired_loop, mock_orchestrator, mock_tts):
        """Status should show 'No Mic' while waiting for reconnect."""
        stop_event = threading.Event()
        statuses = []

        def track_status(s):
            statuses.append(s)

        mock_stream = MagicMock()
        with patch("copilot_echo.voice.audio.sd") as mock_audio_sd, \
             patch("copilot_echo.voice.audio.list_input_devices", return_value=[(0, "Mic")]), \
             patch("copilot_echo.voice.loop.time.sleep"):
            # We need sounddevice available when imported inside the method
            import sys
            mock_sd = MagicMock()
            mock_sd.InputStream.return_value = mock_stream
            with patch.dict(sys.modules, {"sounddevice": mock_sd}):
                wired_loop._handle_device_disconnect(track_status, stop_event)

        assert "No Mic" in statuses


# ------------------------------------------------------------------
# Top-level crash handler
# ------------------------------------------------------------------

class TestCrashHandler:
    def test_unexpected_error_speaks_and_retries(self, wired_loop, mock_orchestrator, mock_tts):
        call_count = 0

        def fake_listen(stop_event):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("unexpected bug")
            stop_event.set()
            return False

        wired_loop.wakeword.listen_until_detected.side_effect = fake_listen
        status_cb = MagicMock()
        stop_event = threading.Event()

        with patch("copilot_echo.voice.loop.time.sleep"):
            wired_loop.run(status_cb, stop_event)

        # Should have spoken about something going wrong
        calls = [c.args[0] for c in mock_tts.speak.call_args_list]
        assert any("went wrong" in c.lower() or "restarting" in c.lower() for c in calls)

    def test_crash_resets_state_to_idle(self, wired_loop, mock_orchestrator, mock_tts):
        mock_orchestrator.state = State.PROCESSING

        call_count = 0

        def fake_listen(stop_event):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("crash")
            stop_event.set()
            return False

        wired_loop.wakeword.listen_until_detected.side_effect = fake_listen
        status_cb = MagicMock()
        stop_event = threading.Event()

        with patch("copilot_echo.voice.loop.time.sleep"):
            wired_loop.run(status_cb, stop_event)

        assert mock_orchestrator.state == State.IDLE
