"""Tests for copilot_echo.voice.stt."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import numpy as np
import pytest


class TestSpeechToTextInit:
    def test_stores_config(self):
        mock_model = MagicMock()
        with patch("copilot_echo.voice.stt.WhisperModel", return_value=mock_model), \
             patch("copilot_echo.voice.stt.resolve_input_device", return_value=None):
            from copilot_echo.voice.stt import SpeechToText

            stt = SpeechToText(
                model_name="tiny",
                device="cpu",
                compute_type="int8",
                sample_rate=16000,
                audio_device=None,
            )
        assert stt.sample_rate == 16000
        assert stt.model is mock_model


class TestTranscribeOnce:
    def test_records_and_transcribes(self):
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "hello world"
        mock_model.transcribe.return_value = ([mock_segment], None)

        mock_audio = np.zeros((16000, 1), dtype=np.float32)

        with patch("copilot_echo.voice.stt.WhisperModel", return_value=mock_model), \
             patch("copilot_echo.voice.stt.resolve_input_device", return_value=None), \
             patch("copilot_echo.voice.stt.sd") as mock_sd:
            mock_sd.rec.return_value = mock_audio
            from copilot_echo.voice.stt import SpeechToText

            stt = SpeechToText("tiny", "cpu", "int8", 16000, None)
            result = stt.transcribe_once(1.0)

        assert result == "hello world"
        mock_sd.rec.assert_called_once()
        mock_sd.wait.assert_called_once()

    def test_empty_transcription(self):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], None)

        mock_audio = np.zeros((16000, 1), dtype=np.float32)

        with patch("copilot_echo.voice.stt.WhisperModel", return_value=mock_model), \
             patch("copilot_echo.voice.stt.resolve_input_device", return_value=None), \
             patch("copilot_echo.voice.stt.sd") as mock_sd:
            mock_sd.rec.return_value = mock_audio
            from copilot_echo.voice.stt import SpeechToText

            stt = SpeechToText("tiny", "cpu", "int8", 16000, None)
            result = stt.transcribe_once(1.0)

        assert result == ""

    def test_multiple_segments_joined(self):
        mock_model = MagicMock()
        seg1 = MagicMock()
        seg1.text = "hello"
        seg2 = MagicMock()
        seg2.text = "world"
        mock_model.transcribe.return_value = ([seg1, seg2], None)

        mock_audio = np.zeros((16000, 1), dtype=np.float32)

        with patch("copilot_echo.voice.stt.WhisperModel", return_value=mock_model), \
             patch("copilot_echo.voice.stt.resolve_input_device", return_value=None), \
             patch("copilot_echo.voice.stt.sd") as mock_sd:
            mock_sd.rec.return_value = mock_audio
            from copilot_echo.voice.stt import SpeechToText

            stt = SpeechToText("tiny", "cpu", "int8", 16000, None)
            result = stt.transcribe_once(1.0)

        assert result == "hello world"


class TestTranscribeUntilSilence:
    def test_no_speech_returns_empty(self):
        """If energy never exceeds threshold, return empty string."""
        mock_model = MagicMock()

        # Simulate silence (very low energy audio)
        silent_audio = np.zeros((1600, 1), dtype=np.float32)  # 100ms at 16kHz

        mock_stream = MagicMock()
        read_count = 0

        def mock_read(n):
            nonlocal read_count
            read_count += 1
            return silent_audio, None

        mock_stream.read = mock_read
        mock_stream.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = MagicMock(return_value=False)

        with patch("copilot_echo.voice.stt.WhisperModel", return_value=mock_model), \
             patch("copilot_echo.voice.stt.resolve_input_device", return_value=None), \
             patch("copilot_echo.voice.stt.sd") as mock_sd:
            mock_sd.InputStream.return_value = mock_stream
            from copilot_echo.voice.stt import SpeechToText

            stt = SpeechToText("tiny", "cpu", "int8", 16000, None)
            result = stt.transcribe_until_silence(
                silence_timeout=0.2,  # Very short for testing
                utterance_end_seconds=0.1,
                max_duration=1.0,
                energy_threshold=0.01,
            )

        assert result == ""

    def test_exception_returns_empty(self):
        mock_model = MagicMock()

        with patch("copilot_echo.voice.stt.WhisperModel", return_value=mock_model), \
             patch("copilot_echo.voice.stt.resolve_input_device", return_value=None), \
             patch("copilot_echo.voice.stt.sd") as mock_sd:
            mock_sd.InputStream.side_effect = RuntimeError("device error")
            from copilot_echo.voice.stt import SpeechToText

            stt = SpeechToText("tiny", "cpu", "int8", 16000, None)
            result = stt.transcribe_until_silence()

        assert result == ""
