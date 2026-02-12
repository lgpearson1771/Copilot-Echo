"""Tests for copilot_echo.orchestrator."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from copilot_echo.orchestrator import Orchestrator, State


class TestInitialState:
    def test_initial_state_is_idle(self, mock_orchestrator):
        assert mock_orchestrator.state == State.IDLE

    def test_initial_last_error_is_none(self, mock_orchestrator):
        assert mock_orchestrator.last_error is None

    def test_interrupt_event_is_clear(self, mock_orchestrator):
        assert not mock_orchestrator.interrupt_event.is_set()


class TestStateTransitions:
    def test_pause_sets_paused(self, mock_orchestrator):
        mock_orchestrator.pause()
        assert mock_orchestrator.state == State.PAUSED

    def test_resume_sets_idle(self, mock_orchestrator):
        mock_orchestrator.pause()
        mock_orchestrator.resume()
        assert mock_orchestrator.state == State.IDLE

    def test_on_wake_word_sets_listening(self, mock_orchestrator):
        mock_orchestrator.on_wake_word()
        assert mock_orchestrator.state == State.LISTENING

    def test_on_wake_word_ignored_when_paused(self, mock_orchestrator):
        mock_orchestrator.pause()
        mock_orchestrator.on_wake_word()
        assert mock_orchestrator.state == State.PAUSED


class TestAutoPause:
    def test_auto_pause_from_idle(self, mock_orchestrator):
        mock_orchestrator.auto_pause()
        assert mock_orchestrator.state == State.PAUSED
        assert mock_orchestrator.is_auto_paused is True

    def test_auto_pause_from_listening(self, mock_orchestrator):
        mock_orchestrator.state = State.LISTENING
        mock_orchestrator.auto_pause()
        assert mock_orchestrator.state == State.PAUSED
        assert mock_orchestrator.is_auto_paused is True

    def test_auto_pause_noop_during_processing(self, mock_orchestrator):
        mock_orchestrator.state = State.PROCESSING
        mock_orchestrator.auto_pause()
        assert mock_orchestrator.state == State.PROCESSING
        assert mock_orchestrator.is_auto_paused is False

    def test_auto_pause_noop_during_autonomous(self, mock_orchestrator):
        mock_orchestrator.state = State.AUTONOMOUS
        mock_orchestrator.auto_pause()
        assert mock_orchestrator.state == State.AUTONOMOUS
        assert mock_orchestrator.is_auto_paused is False

    def test_auto_resume_when_auto_paused(self, mock_orchestrator):
        mock_orchestrator.auto_pause()
        mock_orchestrator.auto_resume()
        assert mock_orchestrator.state == State.IDLE
        assert mock_orchestrator.is_auto_paused is False

    def test_auto_resume_noop_when_manually_paused(self, mock_orchestrator):
        mock_orchestrator.pause()
        mock_orchestrator.auto_resume()
        assert mock_orchestrator.state == State.PAUSED

    def test_resume_clears_auto_paused_flag(self, mock_orchestrator):
        mock_orchestrator.auto_pause()
        assert mock_orchestrator.is_auto_paused is True
        mock_orchestrator.resume()
        assert mock_orchestrator.is_auto_paused is False
        assert mock_orchestrator.state == State.IDLE

    def test_is_auto_paused_initially_false(self, mock_orchestrator):
        assert mock_orchestrator.is_auto_paused is False


class TestSendToAgent:
    def test_send_transitions_to_processing_then_idle(self, mock_orchestrator):
        """State should go through PROCESSING and end at IDLE."""
        states_seen = []
        original_send = mock_orchestrator.agent.send

        def tracking_send(text):
            states_seen.append(mock_orchestrator.state)
            return original_send(text)

        mock_orchestrator.agent.send = tracking_send
        reply = mock_orchestrator.send_to_agent("hello")
        assert State.PROCESSING in states_seen
        assert mock_orchestrator.state == State.IDLE
        assert reply == "Mock agent reply"

    def test_send_keep_state_restores_previous(self, mock_orchestrator):
        mock_orchestrator.state = State.AUTONOMOUS
        mock_orchestrator.send_to_agent("test", keep_state=True)
        assert mock_orchestrator.state == State.AUTONOMOUS

    def test_send_exception_returns_error_message(self, mock_orchestrator):
        mock_orchestrator.agent.send.side_effect = RuntimeError("boom")
        reply = mock_orchestrator.send_to_agent("fail")
        assert "error" in reply.lower()

    def test_send_sets_last_error_on_exception(self, mock_orchestrator):
        mock_orchestrator.agent.send.side_effect = RuntimeError("boom")
        mock_orchestrator.send_to_agent("fail")
        assert mock_orchestrator.last_error == "boom"

    def test_send_returns_to_idle_after_exception(self, mock_orchestrator):
        mock_orchestrator.agent.send.side_effect = RuntimeError("boom")
        mock_orchestrator.send_to_agent("fail")
        assert mock_orchestrator.state == State.IDLE


class TestCancelAgent:
    def test_cancel_resets_to_idle(self, mock_orchestrator):
        mock_orchestrator.state = State.PROCESSING
        mock_orchestrator.cancel_agent()
        assert mock_orchestrator.state == State.IDLE

    def test_cancel_calls_agent_cancel(self, mock_orchestrator):
        mock_orchestrator.cancel_agent()
        mock_orchestrator.agent.cancel.assert_called_once()


class TestAutonomousMode:
    def test_start_autonomous_sets_state(self, mock_orchestrator):
        mock_orchestrator.start_autonomous()
        assert mock_orchestrator.state == State.AUTONOMOUS

    def test_start_autonomous_clears_interrupt(self, mock_orchestrator):
        mock_orchestrator.interrupt_event.set()
        mock_orchestrator.start_autonomous()
        assert not mock_orchestrator.interrupt_event.is_set()

    def test_stop_autonomous_resets_idle(self, mock_orchestrator):
        mock_orchestrator.start_autonomous()
        mock_orchestrator.stop_autonomous()
        assert mock_orchestrator.state == State.IDLE

    def test_stop_autonomous_clears_interrupt(self, mock_orchestrator):
        mock_orchestrator.start_autonomous()
        mock_orchestrator.interrupt_event.set()
        mock_orchestrator.stop_autonomous()
        assert not mock_orchestrator.interrupt_event.is_set()


class TestRequestInterrupt:
    def test_request_interrupt_sets_event(self, mock_orchestrator):
        mock_orchestrator.request_interrupt()
        assert mock_orchestrator.interrupt_event.is_set()


class TestLifecycle:
    def test_start_agent_failure_sets_last_error(self, fake_config):
        with patch("copilot_echo.orchestrator.Agent") as MockAgent:
            mock_agent = MagicMock()
            mock_agent.start.side_effect = RuntimeError("Failed")
            MockAgent.return_value = mock_agent
            orch = Orchestrator(fake_config)
            orch.start_agent()
        assert orch.last_error == "Agent failed to start"

    def test_stop_agent_calls_agent_stop(self, mock_orchestrator):
        mock_orchestrator.stop_agent()
        mock_orchestrator.agent.stop.assert_called_once()
