"""Tests for copilot_echo.voice.audio."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from copilot_echo.voice.audio import list_input_devices, resolve_input_device


class TestResolveInputDevice:
    def test_with_index(self):
        result = resolve_input_device(3, None)
        assert result == 3

    def test_index_takes_priority_over_name(self):
        result = resolve_input_device(5, "Some Device")
        assert result == 5

    def test_both_none(self):
        result = resolve_input_device(None, None)
        assert result is None

    def test_name_match(self):
        devices = [
            {"name": "Speakers (Output)", "max_input_channels": 0},
            {"name": "Microphone (Realtek)", "max_input_channels": 2},
            {"name": "Line In (Realtek)", "max_input_channels": 2},
        ]
        with patch("copilot_echo.voice.audio.sd.query_devices", return_value=devices):
            result = resolve_input_device(None, "microphone")
        assert result == 1

    def test_name_no_match(self):
        devices = [
            {"name": "Speakers", "max_input_channels": 0},
            {"name": "Microphone", "max_input_channels": 2},
        ]
        with patch("copilot_echo.voice.audio.sd.query_devices", return_value=devices):
            result = resolve_input_device(None, "usb audio")
        assert result is None

    def test_name_case_insensitive(self):
        devices = [
            {"name": "USB MICROPHONE", "max_input_channels": 1},
        ]
        with patch("copilot_echo.voice.audio.sd.query_devices", return_value=devices):
            result = resolve_input_device(None, "usb microphone")
        assert result == 0


class TestListInputDevices:
    def test_filters_input_only(self):
        devices = [
            {"name": "Speakers", "max_input_channels": 0},
            {"name": "Mic A", "max_input_channels": 2},
            {"name": "HDMI Out", "max_input_channels": 0},
            {"name": "Mic B", "max_input_channels": 1},
        ]
        with patch("copilot_echo.voice.audio.sd.query_devices", return_value=devices):
            result = list(list_input_devices())
        assert len(result) == 2
        assert result[0] == (1, "Mic A")
        assert result[1] == (3, "Mic B")

    def test_empty_devices(self):
        with patch("copilot_echo.voice.audio.sd.query_devices", return_value=[]):
            result = list(list_input_devices())
        assert result == []

    def test_missing_name_key(self):
        devices = [{"max_input_channels": 2}]
        with patch("copilot_echo.voice.audio.sd.query_devices", return_value=devices):
            result = list(list_input_devices())
        assert result == [(0, "Unknown")]
