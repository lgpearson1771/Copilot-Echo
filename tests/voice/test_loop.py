"""Tests for copilot_echo.voice.loop."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch, PropertyMock, call

import pytest

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
                return "hey jarvis"
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
