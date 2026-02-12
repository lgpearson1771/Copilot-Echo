"""Tests for copilot_echo.voice.autonomous."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch, call

import pytest

from copilot_echo.errors import DeviceDisconnectedError
from copilot_echo.orchestrator import State
from copilot_echo.voice.autonomous import AutonomousRunner, _AD_HOC_PATTERN
from copilot_echo.voice.tts import INTERRUPT_PHRASES


# ------------------------------------------------------------------
# Static helpers
# ------------------------------------------------------------------

class TestStripMarker:
    def test_done_on_last_line(self):
        text, is_done = AutonomousRunner._strip_marker("Summary text\nDONE")
        assert "DONE" not in text
        assert is_done is True

    def test_next_on_last_line(self):
        text, is_done = AutonomousRunner._strip_marker("Step complete\nNEXT")
        assert "NEXT" not in text
        assert is_done is False

    def test_inline_done(self):
        text, is_done = AutonomousRunner._strip_marker("All finished DONE")
        assert "DONE" not in text
        assert is_done is True

    def test_inline_next(self):
        text, is_done = AutonomousRunner._strip_marker("Moving on NEXT")
        assert "NEXT" not in text
        assert is_done is False

    def test_no_marker(self):
        original = "Just a normal reply"
        text, is_done = AutonomousRunner._strip_marker(original)
        assert text == original
        assert is_done is False

    def test_done_mixed_case(self):
        text, is_done = AutonomousRunner._strip_marker("Text\ndone")
        # The method checks upper() so lowercase "done" should match
        assert is_done is True

    def test_next_mixed_case(self):
        text, is_done = AutonomousRunner._strip_marker("Text\nnext")
        assert is_done is False
        assert "next" not in text.lower() or text.strip() == "Text"

    def test_both_markers_done_wins(self):
        text, is_done = AutonomousRunner._strip_marker("Step\nNEXT\nDONE")
        # DONE on last line after stripping NEXT — DONE should be processed
        assert is_done is True


class TestIsInterruptPhrase:
    @pytest.mark.parametrize("phrase", INTERRUPT_PHRASES)
    def test_known_phrases(self, phrase):
        assert AutonomousRunner._is_interrupt_phrase(phrase) is True

    def test_case_insensitive(self):
        assert AutonomousRunner._is_interrupt_phrase("STOP") is True
        assert AutonomousRunner._is_interrupt_phrase("Listen Up") is True

    def test_substring_match(self):
        assert AutonomousRunner._is_interrupt_phrase("please stop talking") is True

    def test_negative(self):
        assert AutonomousRunner._is_interrupt_phrase("continue working") is False
        assert AutonomousRunner._is_interrupt_phrase("") is False


# ------------------------------------------------------------------
# Ad-hoc pattern
# ------------------------------------------------------------------

class TestAdHocPattern:
    def test_get_to_work_on(self):
        m = _AD_HOC_PATTERN.search("get to work on fixing the bug")
        assert m is not None
        assert m.group(1).strip() == "fixing the bug"

    def test_start_working_on(self):
        m = _AD_HOC_PATTERN.search("start working on PR reviews")
        assert m is not None
        assert m.group(1).strip() == "PR reviews"

    def test_work_on(self):
        m = _AD_HOC_PATTERN.search("work on the deployment pipeline")
        assert m is not None
        assert m.group(1).strip() == "the deployment pipeline"

    def test_no_match(self):
        m = _AD_HOC_PATTERN.search("what is the weather")
        assert m is None

    def test_case_insensitive(self):
        m = _AD_HOC_PATTERN.search("GET TO WORK ON big task")
        assert m is not None


# ------------------------------------------------------------------
# Trigger detection
# ------------------------------------------------------------------

class TestCheckTrigger:
    @pytest.fixture
    def runner(self, fake_config, mock_orchestrator, mock_stt, mock_tts):
        speak_fn = MagicMock(return_value=False)
        return AutonomousRunner(
            fake_config, mock_orchestrator, mock_stt, mock_tts, speak_fn
        )

    def test_routine_match(self, runner, mock_orchestrator):
        """Should match a configured routine trigger phrase."""
        status_cb = MagicMock()
        stop_event = threading.Event()

        # Mock the agent to return DONE immediately
        mock_orchestrator.agent.send.return_value = "Done\nDONE"

        result = runner.check_trigger(
            "daily standup", "daily standup", status_cb, stop_event
        )
        assert result is True

    def test_ad_hoc_match(self, runner, mock_orchestrator):
        status_cb = MagicMock()
        stop_event = threading.Event()
        mock_orchestrator.agent.send.return_value = "Finished\nDONE"

        result = runner.check_trigger(
            "get to work on fixing tests",
            "get to work on fixing tests",
            status_cb,
            stop_event,
        )
        assert result is True

    def test_no_match(self, runner):
        status_cb = MagicMock()
        stop_event = threading.Event()
        result = runner.check_trigger(
            "what time is it", "what time is it", status_cb, stop_event
        )
        assert result is False


# ------------------------------------------------------------------
# Run loop
# ------------------------------------------------------------------

class TestRun:
    @pytest.fixture
    def runner(self, fake_config, mock_orchestrator, mock_stt, mock_tts):
        speak_fn = MagicMock(return_value=False)
        return AutonomousRunner(
            fake_config, mock_orchestrator, mock_stt, mock_tts, speak_fn
        )

    def test_done_marker_exits(self, runner, mock_orchestrator, mock_stt):
        mock_orchestrator.agent.send.return_value = "All complete\nDONE"
        mock_stt.transcribe_once.return_value = ""
        status_cb = MagicMock()
        stop_event = threading.Event()

        runner._run("test task", 5, 10, status_cb, stop_event)

        # Should have called agent.send once (DONE on first step)
        assert mock_orchestrator.agent.send.call_count == 1

    def test_max_steps_reached(self, runner, mock_orchestrator, mock_stt):
        mock_orchestrator.agent.send.return_value = "Progress\nNEXT"
        mock_stt.transcribe_once.return_value = ""
        status_cb = MagicMock()
        stop_event = threading.Event()

        runner._run("test task", 3, 10, status_cb, stop_event)

        assert mock_orchestrator.agent.send.call_count == 3

    def test_stop_event_exits(self, runner, mock_orchestrator, mock_stt):
        mock_stt.transcribe_once.return_value = ""
        status_cb = MagicMock()
        stop_event = threading.Event()
        stop_event.set()  # Already stopped

        runner._run("test task", 5, 10, status_cb, stop_event)

        # Should not have called the agent at all
        mock_orchestrator.agent.send.assert_not_called()

    def test_hotkey_interrupt_before_step(self, runner, mock_orchestrator, mock_stt, mock_tts):
        # Set interrupt via status_cb side effect so it fires AFTER start_autonomous clears it
        def set_interrupt(msg):
            if msg == "Working":
                mock_orchestrator.interrupt_event.set()
        status_cb = MagicMock(side_effect=set_interrupt)
        mock_stt.transcribe_once.return_value = ""
        stop_event = threading.Event()

        runner._run("test task", 5, 10, status_cb, stop_event)

        # Should exit immediately and speak about stopping
        calls = [c.args[0] for c in mock_tts.speak.call_args_list]
        assert any("stopping" in c.lower() or "autonomous" in c.lower() for c in calls)

    def test_empty_reply_breaks(self, runner, mock_orchestrator, mock_stt, mock_tts):
        mock_orchestrator.agent.send.return_value = ""
        mock_stt.transcribe_once.return_value = ""
        status_cb = MagicMock()
        stop_event = threading.Event()

        runner._run("test task", 5, 10, status_cb, stop_event)

        # Should have spoken about not getting a response
        calls = [c.args[0] for c in mock_tts.speak.call_args_list]
        assert any("didn't get" in c.lower() or "response" in c.lower() for c in calls)

    def test_voice_interrupt_between_steps(self, runner, mock_orchestrator, mock_stt, mock_tts):
        call_count = 0

        def side_effect(text):
            nonlocal call_count
            call_count += 1
            return "Step done\nNEXT"

        mock_orchestrator.agent.send.side_effect = side_effect

        # First transcribe_once returns empty (pre-step), second returns interrupt
        transcribe_calls = iter(["", "", "stop", ""])
        mock_stt.transcribe_once.side_effect = lambda _: next(transcribe_calls, "")

        status_cb = MagicMock()
        stop_event = threading.Event()

        runner._run("test task", 5, 10, status_cb, stop_event)

        # Agent should have been called once then interrupted
        assert call_count == 1

    def test_time_limit(self, runner, mock_orchestrator, mock_stt, mock_tts):
        mock_orchestrator.agent.send.return_value = "Progress\nNEXT"
        mock_stt.transcribe_once.return_value = ""
        status_cb = MagicMock()
        stop_event = threading.Event()

        # Use 0 minutes to immediately hit deadline
        runner._run("test task", 10, 0, status_cb, stop_event)

        # Should speak about time limit
        calls = [c.args[0] for c in mock_tts.speak.call_args_list]
        assert any("time limit" in c.lower() for c in calls)


# ------------------------------------------------------------------
# Interrupt watcher
# ------------------------------------------------------------------

class TestInterruptWatcher:
    def test_watcher_cancels_agent(self, fake_config, mock_orchestrator, mock_stt, mock_tts):
        speak_fn = MagicMock(return_value=False)
        runner = AutonomousRunner(
            fake_config, mock_orchestrator, mock_stt, mock_tts, speak_fn
        )

        runner._interrupt_watcher_stop.clear()
        runner._agent_interrupted.clear()

        watcher = threading.Thread(target=runner._interrupt_watcher, daemon=True)
        watcher.start()

        # Fire interrupt
        mock_orchestrator.interrupt_event.set()
        watcher.join(timeout=2)

        assert runner._agent_interrupted.is_set()
        mock_orchestrator.agent.cancel.assert_called()

    def test_stop_interrupt_watcher(self, fake_config, mock_orchestrator, mock_stt, mock_tts):
        speak_fn = MagicMock(return_value=False)
        runner = AutonomousRunner(
            fake_config, mock_orchestrator, mock_stt, mock_tts, speak_fn
        )

        runner._interrupt_watcher_stop.clear()
        watcher = threading.Thread(target=runner._interrupt_watcher, daemon=True)
        watcher.start()

        runner._stop_interrupt_watcher()
        watcher.join(timeout=2)

        assert not watcher.is_alive()


# ------------------------------------------------------------------
# Exception cleanup safety net
# ------------------------------------------------------------------

class TestCleanupSafetyNet:
    def test_device_disconnect_during_run_cleans_up(
        self, fake_config, mock_orchestrator, mock_stt, mock_tts
    ):
        speak_fn = MagicMock(return_value=False)
        runner = AutonomousRunner(
            fake_config, mock_orchestrator, mock_stt, mock_tts, speak_fn
        )

        # transcribe_once raises DeviceDisconnectedError on pre-step check
        mock_stt.transcribe_once.side_effect = DeviceDisconnectedError("mic gone")
        status_cb = MagicMock()
        stop_event = threading.Event()

        with pytest.raises(DeviceDisconnectedError):
            runner._run("test task", 5, 10, status_cb, stop_event)

        # Cleanup should have happened
        assert mock_orchestrator.state != State.AUTONOMOUS

    def test_unexpected_error_cleans_up(
        self, fake_config, mock_orchestrator, mock_stt, mock_tts
    ):
        speak_fn = MagicMock(return_value=False)
        runner = AutonomousRunner(
            fake_config, mock_orchestrator, mock_stt, mock_tts, speak_fn
        )

        # Pre-step transcribe_once returns empty, agent send raises
        mock_stt.transcribe_once.return_value = ""
        mock_orchestrator.agent.send.side_effect = RuntimeError("unexpected")
        # send_to_agent catches the exception and returns error string,
        # so we need to make the interruptible speak raise instead
        speak_fn.side_effect = RuntimeError("speaker crash")
        status_cb = MagicMock()
        stop_event = threading.Event()

        with pytest.raises(RuntimeError, match="speaker crash"):
            runner._run("test task", 5, 10, status_cb, stop_event)

        assert mock_orchestrator.state != State.AUTONOMOUS
