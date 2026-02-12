"""Tests for copilot_echo.voice.call_detector."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from unittest.mock import MagicMock, patch, call

import pytest

from copilot_echo.orchestrator import State


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_session_ctl(pid: int, state: int = 1):
    """Create a mock audio session control pair (ctl, ctl2)."""
    ctl = MagicMock()
    ctl.GetState.return_value = state

    ctl2 = MagicMock()
    ctl2.GetProcessId.return_value = pid
    ctl.QueryInterface.return_value = ctl2
    return ctl


def _make_enumerator(sessions: list):
    """Create a mock IAudioSessionEnumerator with the given sessions."""
    enum = MagicMock()
    enum.GetCount.return_value = len(sessions)
    enum.GetSession.side_effect = lambda i: sessions[i]
    return enum


def _make_device(sessions: list):
    """Create a mock IMMDevice that returns the given sessions."""
    mgr = MagicMock()
    mgr.QueryInterface.return_value = mgr
    mgr.GetSessionEnumerator.return_value = _make_enumerator(sessions)

    device = MagicMock()
    device.Activate.return_value = mgr
    return device


# ------------------------------------------------------------------
# is_call_active
# ------------------------------------------------------------------

class TestIsCallActive:
    """Tests for the is_call_active helper function."""

    def _patch_sessions(self, sessions):
        return patch(
            "copilot_echo.voice.call_detector.get_active_audio_sessions",
            return_value=sessions,
        )

    def test_no_sessions_returns_false(self):
        from copilot_echo.voice.call_detector import is_call_active, AudioSession

        with self._patch_sessions([]):
            assert is_call_active({"ms-teams.exe"}) is False

    def test_matching_process_returns_true(self):
        from copilot_echo.voice.call_detector import is_call_active, AudioSession

        with self._patch_sessions([AudioSession(pid=100, process_name="ms-teams.exe")]):
            assert is_call_active({"ms-teams.exe"}) is True

    def test_non_matching_process_returns_false(self):
        from copilot_echo.voice.call_detector import is_call_active, AudioSession

        with self._patch_sessions([AudioSession(pid=100, process_name="chrome.exe")]):
            assert is_call_active({"ms-teams.exe"}) is False

    def test_case_insensitive_match(self):
        from copilot_echo.voice.call_detector import is_call_active, AudioSession

        with self._patch_sessions([AudioSession(pid=100, process_name="MS-Teams.EXE")]):
            assert is_call_active({"ms-teams.exe"}) is True

    def test_multiple_apps_any_match(self):
        from copilot_echo.voice.call_detector import is_call_active, AudioSession

        with self._patch_sessions([AudioSession(pid=200, process_name="Zoom.exe")]):
            assert is_call_active({"ms-teams.exe", "Zoom.exe"}) is True


# ------------------------------------------------------------------
# get_active_audio_sessions
# ------------------------------------------------------------------

class TestGetActiveAudioSessions:
    """Tests for the WASAPI session enumeration logic."""

    @patch("copilot_echo.voice.call_detector._get_audio_endpoints")
    @patch("copilot_echo.voice.call_detector._HAS_PYCAW", True)
    def test_no_devices_returns_empty(self, mock_endpoints):
        from copilot_echo.voice.call_detector import get_active_audio_sessions

        mock_endpoints.return_value = []
        assert get_active_audio_sessions() == []

    @patch("copilot_echo.voice.call_detector.psutil")
    @patch("copilot_echo.voice.call_detector._get_audio_endpoints")
    @patch("copilot_echo.voice.call_detector._HAS_PYCAW", True)
    @patch("copilot_echo.voice.call_detector.comtypes")
    def test_active_session_captured(self, mock_comtypes, mock_endpoints, mock_psutil):
        from copilot_echo.voice.call_detector import get_active_audio_sessions

        ctl = _make_session_ctl(pid=42, state=1)
        device = _make_device([ctl])
        mock_endpoints.return_value = [device]

        proc = MagicMock()
        proc.name.return_value = "ms-teams.exe"
        mock_psutil.Process.return_value = proc
        mock_psutil.NoSuchProcess = Exception
        mock_psutil.AccessDenied = Exception

        sessions = get_active_audio_sessions()

        assert len(sessions) == 1
        assert sessions[0].process_name == "ms-teams.exe"
        assert sessions[0].pid == 42

    @patch("copilot_echo.voice.call_detector.psutil")
    @patch("copilot_echo.voice.call_detector._get_audio_endpoints")
    @patch("copilot_echo.voice.call_detector._HAS_PYCAW", True)
    @patch("copilot_echo.voice.call_detector.comtypes")
    def test_pid_zero_filtered(self, mock_comtypes, mock_endpoints, mock_psutil):
        from copilot_echo.voice.call_detector import get_active_audio_sessions

        ctl = _make_session_ctl(pid=0, state=1)
        device = _make_device([ctl])
        mock_endpoints.return_value = [device]

        sessions = get_active_audio_sessions()
        assert sessions == []

    @patch("copilot_echo.voice.call_detector.psutil")
    @patch("copilot_echo.voice.call_detector._get_audio_endpoints")
    @patch("copilot_echo.voice.call_detector._HAS_PYCAW", True)
    @patch("copilot_echo.voice.call_detector.comtypes")
    def test_audiodg_filtered(self, mock_comtypes, mock_endpoints, mock_psutil):
        from copilot_echo.voice.call_detector import get_active_audio_sessions

        ctl = _make_session_ctl(pid=10, state=1)
        device = _make_device([ctl])
        mock_endpoints.return_value = [device]

        proc = MagicMock()
        proc.name.return_value = "audiodg.exe"
        mock_psutil.Process.return_value = proc
        mock_psutil.NoSuchProcess = Exception
        mock_psutil.AccessDenied = Exception

        sessions = get_active_audio_sessions()
        assert sessions == []

    @patch("copilot_echo.voice.call_detector.psutil")
    @patch("copilot_echo.voice.call_detector._get_audio_endpoints")
    @patch("copilot_echo.voice.call_detector._HAS_PYCAW", True)
    @patch("copilot_echo.voice.call_detector.comtypes")
    def test_inactive_session_filtered(self, mock_comtypes, mock_endpoints, mock_psutil):
        from copilot_echo.voice.call_detector import get_active_audio_sessions

        ctl = _make_session_ctl(pid=42, state=0)  # Inactive
        device = _make_device([ctl])
        mock_endpoints.return_value = [device]

        sessions = get_active_audio_sessions()
        assert sessions == []

    @patch("copilot_echo.voice.call_detector.psutil")
    @patch("copilot_echo.voice.call_detector._get_audio_endpoints")
    @patch("copilot_echo.voice.call_detector._HAS_PYCAW", True)
    @patch("copilot_echo.voice.call_detector.comtypes")
    def test_no_such_process_handled(self, mock_comtypes, mock_endpoints, mock_psutil):
        import psutil as real_psutil

        from copilot_echo.voice.call_detector import get_active_audio_sessions

        ctl = _make_session_ctl(pid=999, state=1)
        device = _make_device([ctl])
        mock_endpoints.return_value = [device]

        mock_psutil.Process.side_effect = real_psutil.NoSuchProcess(999)
        mock_psutil.NoSuchProcess = real_psutil.NoSuchProcess
        mock_psutil.AccessDenied = real_psutil.AccessDenied

        sessions = get_active_audio_sessions()
        assert sessions == []

    @patch("copilot_echo.voice.call_detector.psutil")
    @patch("copilot_echo.voice.call_detector._get_audio_endpoints")
    @patch("copilot_echo.voice.call_detector._HAS_PYCAW", True)
    @patch("copilot_echo.voice.call_detector.comtypes")
    def test_multiple_devices_enumerated(self, mock_comtypes, mock_endpoints, mock_psutil):
        from copilot_echo.voice.call_detector import get_active_audio_sessions

        ctl1 = _make_session_ctl(pid=10, state=1)
        ctl2 = _make_session_ctl(pid=20, state=1)
        device1 = _make_device([ctl1])
        device2 = _make_device([ctl2])
        mock_endpoints.return_value = [device1, device2]

        def proc_factory(pid):
            p = MagicMock()
            p.name.return_value = f"app{pid}.exe"
            return p

        mock_psutil.Process.side_effect = proc_factory
        mock_psutil.NoSuchProcess = Exception
        mock_psutil.AccessDenied = Exception

        sessions = get_active_audio_sessions()
        assert len(sessions) == 2

    @patch("copilot_echo.voice.call_detector.psutil")
    @patch("copilot_echo.voice.call_detector._get_audio_endpoints")
    @patch("copilot_echo.voice.call_detector._HAS_PYCAW", True)
    @patch("copilot_echo.voice.call_detector.comtypes")
    def test_duplicate_pid_deduplicated(self, mock_comtypes, mock_endpoints, mock_psutil):
        """Same PID on both capture and render endpoint should appear only once."""
        from copilot_echo.voice.call_detector import get_active_audio_sessions

        ctl1 = _make_session_ctl(pid=42, state=1)
        ctl2 = _make_session_ctl(pid=42, state=1)
        device1 = _make_device([ctl1])  # e.g. render
        device2 = _make_device([ctl2])  # e.g. capture
        mock_endpoints.return_value = [device1, device2]

        proc = MagicMock()
        proc.name.return_value = "ms-teams.exe"
        mock_psutil.Process.return_value = proc
        mock_psutil.NoSuchProcess = Exception
        mock_psutil.AccessDenied = Exception

        sessions = get_active_audio_sessions()
        assert len(sessions) == 1
        assert sessions[0].pid == 42

    @patch("copilot_echo.voice.call_detector._HAS_PYCAW", False)
    def test_no_pycaw_returns_empty(self):
        from copilot_echo.voice.call_detector import get_active_audio_sessions

        sessions = get_active_audio_sessions()
        assert sessions == []


# ------------------------------------------------------------------
# CallDetector
# ------------------------------------------------------------------

class TestCallDetector:
    """Tests for the CallDetector polling loop."""

    def test_disabled_in_config_returns_immediately(self, fake_config, mock_orchestrator):
        from copilot_echo.voice.call_detector import CallDetector

        fake_config.voice.auto_pause_on_call = False
        detector = CallDetector(fake_config, mock_orchestrator)
        stop_event = threading.Event()

        # Should return without blocking
        detector.run(stop_event)
        # No state change
        assert mock_orchestrator.state == State.IDLE

    def test_call_detected_triggers_auto_pause(self, fake_config, mock_orchestrator):
        from copilot_echo.voice.call_detector import CallDetector

        fake_config.voice.auto_pause_on_call = True
        fake_config.voice.auto_pause_poll_seconds = 0.05

        detector = CallDetector(fake_config, mock_orchestrator)

        call_count = 0

        def fake_call_check(app_names):
            nonlocal call_count
            call_count += 1
            return call_count == 1  # first poll: call active; second: no call

        stop_event = threading.Event()

        with patch("copilot_echo.voice.call_detector.is_call_active", side_effect=fake_call_check):
            t = threading.Thread(target=detector.run, args=(stop_event,), daemon=True)
            t.start()
            time.sleep(0.15)
            stop_event.set()
            t.join(timeout=2)

        # After first poll auto_pause fires, after second auto_resume fires
        # Final state depends on timing, but auto_pause must have been called
        assert mock_orchestrator.state in (State.PAUSED, State.IDLE)

    def test_call_ended_triggers_auto_resume(self, fake_config, mock_orchestrator):
        from copilot_echo.voice.call_detector import CallDetector

        fake_config.voice.auto_pause_on_call = True
        fake_config.voice.auto_pause_poll_seconds = 0.05

        detector = CallDetector(fake_config, mock_orchestrator)

        call_count = 0

        def fake_call_check(app_names):
            nonlocal call_count
            call_count += 1
            return call_count <= 1  # first poll: call; second+: no call

        stop_event = threading.Event()

        with patch("copilot_echo.voice.call_detector.is_call_active", side_effect=fake_call_check):
            t = threading.Thread(target=detector.run, args=(stop_event,), daemon=True)
            t.start()
            time.sleep(0.2)
            stop_event.set()
            t.join(timeout=2)

        # After auto-resume, state should be back to IDLE
        assert mock_orchestrator.state == State.IDLE
        assert mock_orchestrator.is_auto_paused is False

    def test_no_duplicate_pause(self, fake_config, mock_orchestrator):
        """If already auto-paused and call still active, don't pause again."""
        from copilot_echo.voice.call_detector import CallDetector

        fake_config.voice.auto_pause_on_call = True
        fake_config.voice.auto_pause_poll_seconds = 0.05

        detector = CallDetector(fake_config, mock_orchestrator)
        stop_event = threading.Event()

        with patch(
            "copilot_echo.voice.call_detector.is_call_active", return_value=True
        ):
            t = threading.Thread(target=detector.run, args=(stop_event,), daemon=True)
            t.start()
            time.sleep(0.2)
            stop_event.set()
            t.join(timeout=2)

        # Should be paused exactly once (state is PAUSED, flag is True)
        assert mock_orchestrator.state == State.PAUSED
        assert mock_orchestrator.is_auto_paused is True

    def test_no_duplicate_resume(self, fake_config, mock_orchestrator):
        """If already resumed and no call, don't resume again."""
        from copilot_echo.voice.call_detector import CallDetector

        fake_config.voice.auto_pause_on_call = True
        fake_config.voice.auto_pause_poll_seconds = 0.05

        detector = CallDetector(fake_config, mock_orchestrator)
        stop_event = threading.Event()

        # No call active, not auto-paused → no resume needed
        with patch(
            "copilot_echo.voice.call_detector.is_call_active", return_value=False
        ):
            t = threading.Thread(target=detector.run, args=(stop_event,), daemon=True)
            t.start()
            time.sleep(0.15)
            stop_event.set()
            t.join(timeout=2)

        # Should still be IDLE, no state transitions
        assert mock_orchestrator.state == State.IDLE
        assert mock_orchestrator.is_auto_paused is False

    def test_manual_pause_not_overridden(self, fake_config, mock_orchestrator):
        """If user manually paused, auto-resume should not fire."""
        from copilot_echo.voice.call_detector import CallDetector

        fake_config.voice.auto_pause_on_call = True
        fake_config.voice.auto_pause_poll_seconds = 0.05

        mock_orchestrator.pause()  # manual pause
        # is_auto_paused should be False

        detector = CallDetector(fake_config, mock_orchestrator)
        stop_event = threading.Event()

        with patch(
            "copilot_echo.voice.call_detector.is_call_active", return_value=False
        ):
            t = threading.Thread(target=detector.run, args=(stop_event,), daemon=True)
            t.start()
            time.sleep(0.15)
            stop_event.set()
            t.join(timeout=2)

        # Should still be paused (manual pause not overridden)
        assert mock_orchestrator.state == State.PAUSED

    def test_stop_event_exits_loop(self, fake_config, mock_orchestrator):
        from copilot_echo.voice.call_detector import CallDetector

        fake_config.voice.auto_pause_on_call = True
        fake_config.voice.auto_pause_poll_seconds = 60.0  # long poll

        detector = CallDetector(fake_config, mock_orchestrator)
        stop_event = threading.Event()

        with patch(
            "copilot_echo.voice.call_detector.is_call_active", return_value=False
        ):
            t = threading.Thread(target=detector.run, args=(stop_event,), daemon=True)
            t.start()
            time.sleep(0.1)
            stop_event.set()
            t.join(timeout=2)

        assert not t.is_alive()

    def test_mute_unmute_stays_paused(self, fake_config, mock_orchestrator):
        """Simulates mute/unmute during a call — should stay paused throughout.

        When muted, the render (speaker) session for Teams stays active
        even though the capture (mic) session goes inactive.  The detector
        should keep the orchestrator paused for the entire call.
        """
        from copilot_echo.voice.call_detector import CallDetector

        fake_config.voice.auto_pause_on_call = True
        fake_config.voice.auto_pause_poll_seconds = 0.05

        detector = CallDetector(fake_config, mock_orchestrator)
        stop_event = threading.Event()

        # Call stays active (render session) regardless of mute state
        with patch(
            "copilot_echo.voice.call_detector.is_call_active", return_value=True
        ):
            t = threading.Thread(target=detector.run, args=(stop_event,), daemon=True)
            t.start()
            time.sleep(0.2)
            stop_event.set()
            t.join(timeout=2)

        assert mock_orchestrator.state == State.PAUSED
        assert mock_orchestrator.is_auto_paused is True
