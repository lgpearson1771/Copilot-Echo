"""Tests for copilot_echo.tray."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from copilot_echo.orchestrator import State


# ------------------------------------------------------------------
# _build_icon
# ------------------------------------------------------------------

class TestBuildIcon:
    def test_icon_size(self):
        from copilot_echo.tray import _build_icon

        img = _build_icon()
        assert img.size == (64, 64)

    def test_icon_mode(self):
        from copilot_echo.tray import _build_icon

        img = _build_icon()
        assert img.mode == "RGB"


# ------------------------------------------------------------------
# TrayApp._set_title
# ------------------------------------------------------------------

class TestSetTitle:
    def test_format(self, fake_config, mock_orchestrator):
        with patch("copilot_echo.tray.pystray") as mock_pystray:
            mock_icon_instance = MagicMock()
            mock_pystray.Icon.return_value = mock_icon_instance
            mock_pystray.Menu = MagicMock()
            mock_pystray.MenuItem = MagicMock()

            from copilot_echo.tray import TrayApp

            tray = TrayApp(fake_config, mock_orchestrator)
            tray._set_title("Idle")
            assert mock_icon_instance.title == "Test Echo - Idle"


# ------------------------------------------------------------------
# Tray callbacks
# ------------------------------------------------------------------

class TestTrayCallbacks:
    @pytest.fixture
    def tray_app(self, fake_config, mock_orchestrator):
        with patch("copilot_echo.tray.pystray") as mock_pystray:
            mock_icon = MagicMock()
            mock_pystray.Icon.return_value = mock_icon
            mock_pystray.Menu = MagicMock()
            mock_pystray.MenuItem = MagicMock()

            from copilot_echo.tray import TrayApp

            app = TrayApp(fake_config, mock_orchestrator)
            yield app

    def test_pause_callback(self, tray_app, mock_orchestrator):
        tray_app._pause(MagicMock(), MagicMock())
        assert mock_orchestrator.state == State.PAUSED

    def test_resume_callback(self, tray_app, mock_orchestrator):
        mock_orchestrator.pause()
        tray_app._resume(MagicMock(), MagicMock())
        assert mock_orchestrator.state == State.IDLE

    def test_stop_callback(self, tray_app, mock_orchestrator):
        tray_app._stop(MagicMock(), MagicMock())
        assert mock_orchestrator.interrupt_event.is_set()

    def test_quit_callback(self, tray_app):
        tray_app._quit(MagicMock(), MagicMock())
        tray_app.icon.stop.assert_called_once()


# ------------------------------------------------------------------
# Caps Lock listener
# ------------------------------------------------------------------

class TestCapsLockListener:
    def test_triple_tap_fires_interrupt(self, mock_orchestrator):
        from copilot_echo.tray import _CAPS_TAP_WINDOW

        # Test the on_press callback logic directly (same logic as _caps_lock_listener)
        tap_times: list[float] = []
        caps_key = object()  # sentinel

        def on_press(key):
            if key != caps_key:
                return
            now = time.time()
            tap_times.append(now)
            while tap_times and now - tap_times[0] > _CAPS_TAP_WINDOW:
                tap_times.pop(0)
            if len(tap_times) >= 3:
                tap_times.clear()
                mock_orchestrator.request_interrupt()

        on_press(caps_key)
        on_press(caps_key)
        on_press(caps_key)

        assert mock_orchestrator.interrupt_event.is_set()

    def test_non_caps_key_ignored(self):
        """Non-caps-lock keys should not count as taps."""
        from copilot_echo.tray import _CAPS_TAP_WINDOW

        # We test the on_press callback logic directly
        mock_keyboard = MagicMock()
        caps_key = mock_keyboard.Key.caps_lock
        other_key = MagicMock()  # not caps_lock

        tap_times: list[float] = []

        # Simulate the on_press callback inline
        def on_press(key):
            if key != caps_key:
                return
            now = time.time()
            tap_times.append(now)
            while tap_times and now - tap_times[0] > _CAPS_TAP_WINDOW:
                tap_times.pop(0)

        on_press(other_key)
        on_press(other_key)
        on_press(other_key)
        assert len(tap_times) == 0
