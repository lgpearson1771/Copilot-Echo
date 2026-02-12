"""Tests for copilot_echo.voice.wakeword."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ------------------------------------------------------------------
# WakeWordDetector — STT engine
# ------------------------------------------------------------------

class TestWakeWordSTT:
    @pytest.fixture
    def detector(self, mock_stt):
        with patch("copilot_echo.voice.wakeword.resolve_input_device", return_value=None):
            from copilot_echo.voice.wakeword import WakeWordDetector

            return WakeWordDetector(
                engine="stt",
                phrase="hey jarvis",
                stt=mock_stt,
                listen_seconds=1.0,
                sample_rate=16000,
                audio_device=None,
                audio_device_name=None,
                inference_framework="tflite",
                wakeword_models=[],
                threshold=0.6,
                chunk_size=1280,
                holdoff_seconds=1.0,
                vad_threshold=0.0,
                speex_noise_suppression=False,
            )

    def test_engine_is_stt(self, detector):
        assert detector.engine == "stt"

    def test_listen_stt_phrase_match(self, detector, mock_stt):
        mock_stt.transcribe_once.return_value = "hey jarvis what time is it"
        stop_event = threading.Event()
        result = detector._listen_stt(stop_event)
        assert result is True

    def test_listen_stt_no_match(self, detector, mock_stt):
        mock_stt.transcribe_once.return_value = "hello world"
        stop_event = threading.Event()
        result = detector._listen_stt(stop_event)
        assert result is False

    def test_listen_stt_empty(self, detector, mock_stt):
        mock_stt.transcribe_once.return_value = ""
        stop_event = threading.Event()
        result = detector._listen_stt(stop_event)
        assert result is False

    def test_listen_stt_stop_event(self, detector, mock_stt):
        stop_event = threading.Event()
        stop_event.set()
        result = detector._listen_stt(stop_event)
        assert result is False

    def test_listen_until_detected_dispatches_to_stt(self, detector, mock_stt):
        mock_stt.transcribe_once.return_value = "hey jarvis"
        stop_event = threading.Event()
        result = detector.listen_until_detected(stop_event)
        assert result is True

    def test_listen_until_detected_dispatches_to_openwakeword(self, mock_stt):
        with patch("copilot_echo.voice.wakeword.resolve_input_device", return_value=None):
            from copilot_echo.voice.wakeword import WakeWordDetector

            # Create with engine="stt" to avoid openwakeword import,
            # then override engine and model to test the openwakeword path.
            detector = WakeWordDetector(
                engine="stt",
                phrase="hey jarvis",
                stt=mock_stt,
                listen_seconds=1.0,
                sample_rate=16000,
                audio_device=None,
                audio_device_name=None,
                inference_framework="tflite",
                wakeword_models=[],
                threshold=0.6,
                chunk_size=1280,
                holdoff_seconds=1.0,
                vad_threshold=0.0,
                speex_noise_suppression=False,
            )
            detector.engine = "openwakeword"
            detector._model = None  # simulate model not initialized

            stop_event = threading.Event()
            # listen_until_detected dispatches to _listen_openwakeword
            result = detector.listen_until_detected(stop_event)
            assert result is False


# ------------------------------------------------------------------
# _is_triggered
# ------------------------------------------------------------------

class TestIsTriggered:
    @pytest.fixture
    def detector(self, mock_stt):
        with patch("copilot_echo.voice.wakeword.resolve_input_device", return_value=None):
            from copilot_echo.voice.wakeword import WakeWordDetector

            d = WakeWordDetector(
                engine="stt",
                phrase="hey jarvis",
                stt=mock_stt,
                listen_seconds=1.0,
                sample_rate=16000,
                audio_device=None,
                audio_device_name=None,
                inference_framework="tflite",
                wakeword_models=[],
                threshold=0.6,
                chunk_size=1280,
                holdoff_seconds=0.5,
                vad_threshold=0.0,
                speex_noise_suppression=False,
            )
            d._last_trigger = 0.0
            return d

    def test_above_threshold(self, detector):
        predictions = {"hey_jarvis": 0.8}
        assert detector._is_triggered(predictions) is True

    def test_below_threshold(self, detector):
        predictions = {"hey_jarvis": 0.3}
        assert detector._is_triggered(predictions) is False

    def test_holdoff_window(self, detector):
        predictions = {"hey_jarvis": 0.9}
        detector._is_triggered(predictions)  # triggers, sets _last_trigger
        # Immediately try again — should be blocked by holdoff
        assert detector._is_triggered(predictions) is False

    def test_holdoff_expires(self, detector):
        predictions = {"hey_jarvis": 0.9}
        detector._is_triggered(predictions)
        detector._last_trigger = time.time() - 1.0  # expired
        assert detector._is_triggered(predictions) is True

    def test_non_dict_predictions(self, detector):
        # If predictions isn't a dict, should return False
        assert detector._is_triggered("not a dict") is False
        assert detector._is_triggered(None) is False

    def test_multiple_models_any_above(self, detector):
        predictions = {"model_a": 0.1, "model_b": 0.9}
        assert detector._is_triggered(predictions) is True
