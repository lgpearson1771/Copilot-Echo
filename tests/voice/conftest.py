"""Voice-specific test fixtures."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_stt():
    """Return a MagicMock standing in for SpeechToText."""
    stt = MagicMock()
    stt.transcribe_once.return_value = ""
    stt.transcribe_until_silence.return_value = ""
    stt.sample_rate = 16000
    stt.audio_device = None
    return stt


@pytest.fixture
def mock_tts():
    """Return a MagicMock standing in for TextToSpeech."""
    tts = MagicMock()
    tts.speak.return_value = None
    return tts
