"""Tests for copilot_echo.voice.tts."""

from __future__ import annotations

import re
import threading
import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from copilot_echo.voice.tts import (
    INTERRUPT_LISTEN_SEC,
    INTERRUPT_PHRASES,
    InterruptibleSpeaker,
    TextToSpeech,
    _resolve_voice,
    speak_error,
)


# ------------------------------------------------------------------
# speak_error helper
# ------------------------------------------------------------------

class TestSpeakError:
    def test_speaks_via_tts(self, mock_tts):
        speak_error(mock_tts, "Something broke")
        mock_tts.speak.assert_called_once_with("Something broke")

    def test_fallback_to_beep_on_tts_failure(self, mock_tts):
        mock_tts.speak.side_effect = RuntimeError("TTS crashed")
        with patch("copilot_echo.voice.tts.winsound") as mock_ws:
            speak_error(mock_tts, "Error message")
        mock_ws.Beep.assert_called_once_with(1000, 400)

    def test_silent_if_both_fail(self, mock_tts):
        mock_tts.speak.side_effect = RuntimeError("TTS crashed")
        with patch("copilot_echo.voice.tts.winsound") as mock_ws:
            mock_ws.Beep.side_effect = RuntimeError("no speaker")
            # Should not raise
            speak_error(mock_tts, "Error message")


# ------------------------------------------------------------------
# TextToSpeech
# ------------------------------------------------------------------

class TestTextToSpeech:
    def test_speak_calls_engine(self):
        mock_engine = MagicMock()
        with patch("copilot_echo.voice.tts.pyttsx3") as mock_pyttsx3:
            mock_pyttsx3.init.return_value = mock_engine
            tts = TextToSpeech()
            tts.speak("Hello there")

        mock_engine.say.assert_called_once_with("Hello there")
        mock_engine.runAndWait.assert_called_once()
        mock_engine.stop.assert_called_once()

    def test_speak_exception_handled(self):
        mock_engine = MagicMock()
        mock_engine.runAndWait.side_effect = RuntimeError("audio error")
        with patch("copilot_echo.voice.tts.pyttsx3") as mock_pyttsx3:
            mock_pyttsx3.init.return_value = mock_engine
            tts = TextToSpeech()
            # Should not raise
            tts.speak("test")

    def test_engine_stop_called_in_finally(self):
        mock_engine = MagicMock()
        mock_engine.say.side_effect = RuntimeError("crash")
        with patch("copilot_echo.voice.tts.pyttsx3") as mock_pyttsx3:
            mock_pyttsx3.init.return_value = mock_engine
            tts = TextToSpeech()
            tts.speak("test")
        mock_engine.stop.assert_called_once()

    def test_voice_name_resolved_on_engine(self):
        mock_engine = MagicMock()
        voice_obj = MagicMock()
        voice_obj.name = "Microsoft David Desktop"
        voice_obj.id = "HKEY_david"
        mock_engine.getProperty.return_value = [voice_obj]
        with patch("copilot_echo.voice.tts.pyttsx3") as mock_pyttsx3:
            mock_pyttsx3.init.return_value = mock_engine
            tts = TextToSpeech(voice="David")
            tts.speak("Hi")
        mock_engine.setProperty.assert_any_call("voice", "HKEY_david")

    def test_voice_name_case_insensitive(self):
        mock_engine = MagicMock()
        voice_obj = MagicMock()
        voice_obj.name = "Microsoft Zira Desktop"
        voice_obj.id = "HKEY_zira"
        mock_engine.getProperty.return_value = [voice_obj]
        with patch("copilot_echo.voice.tts.pyttsx3") as mock_pyttsx3:
            mock_pyttsx3.init.return_value = mock_engine
            tts = TextToSpeech(voice="zira")
            tts.speak("Hi")
        mock_engine.setProperty.assert_any_call("voice", "HKEY_zira")

    def test_voice_name_no_match_logs_warning(self):
        mock_engine = MagicMock()
        voice_obj = MagicMock()
        voice_obj.name = "Microsoft David Desktop"
        voice_obj.id = "HKEY_david"
        mock_engine.getProperty.return_value = [voice_obj]
        with patch("copilot_echo.voice.tts.pyttsx3") as mock_pyttsx3:
            mock_pyttsx3.init.return_value = mock_engine
            tts = TextToSpeech(voice="NonExistent")
            with patch("copilot_echo.voice.tts.logging") as mock_log:
                tts.speak("Hi")
            mock_log.warning.assert_called_once()
            # Should NOT have set a voice property
            voice_calls = [
                c for c in mock_engine.setProperty.call_args_list
                if c.args[0] == "voice"
            ]
            assert len(voice_calls) == 0

    def test_rate_applied_to_engine(self):
        mock_engine = MagicMock()
        with patch("copilot_echo.voice.tts.pyttsx3") as mock_pyttsx3:
            mock_pyttsx3.init.return_value = mock_engine
            tts = TextToSpeech(rate=150)
            tts.speak("Hi")
        mock_engine.setProperty.assert_any_call("rate", 150)

    def test_volume_applied_to_engine(self):
        mock_engine = MagicMock()
        with patch("copilot_echo.voice.tts.pyttsx3") as mock_pyttsx3:
            mock_pyttsx3.init.return_value = mock_engine
            tts = TextToSpeech(volume=0.5)
            tts.speak("Hi")
        mock_engine.setProperty.assert_any_call("volume", 0.5)

    def test_volume_clamped_to_range(self):
        tts_high = TextToSpeech(volume=2.5)
        assert tts_high._volume == 1.0
        tts_low = TextToSpeech(volume=-0.5)
        assert tts_low._volume == 0.0

    def test_default_rate_and_volume(self):
        mock_engine = MagicMock()
        with patch("copilot_echo.voice.tts.pyttsx3") as mock_pyttsx3:
            mock_pyttsx3.init.return_value = mock_engine
            tts = TextToSpeech()
            tts.speak("Hi")
        mock_engine.setProperty.assert_any_call("rate", 200)
        mock_engine.setProperty.assert_any_call("volume", 1.0)

    def test_no_voice_property_when_none(self):
        mock_engine = MagicMock()
        with patch("copilot_echo.voice.tts.pyttsx3") as mock_pyttsx3:
            mock_pyttsx3.init.return_value = mock_engine
            tts = TextToSpeech()  # voice=None
            tts.speak("Hi")
        voice_calls = [
            c for c in mock_engine.setProperty.call_args_list
            if c.args[0] == "voice"
        ]
        assert len(voice_calls) == 0


# ------------------------------------------------------------------
# _resolve_voice helper
# ------------------------------------------------------------------

class TestResolveVoice:
    def test_match_found(self):
        engine = MagicMock()
        v1 = MagicMock(); v1.name = "Microsoft David Desktop"; v1.id = "id_david"
        v2 = MagicMock(); v2.name = "Microsoft Zira Desktop"; v2.id = "id_zira"
        engine.getProperty.return_value = [v1, v2]
        assert _resolve_voice(engine, "David") == "id_david"

    def test_no_match(self):
        engine = MagicMock()
        v1 = MagicMock(); v1.name = "Microsoft David Desktop"; v1.id = "id_david"
        engine.getProperty.return_value = [v1]
        assert _resolve_voice(engine, "Cortana") is None

    def test_case_insensitive(self):
        engine = MagicMock()
        v1 = MagicMock(); v1.name = "Microsoft Zira Desktop"; v1.id = "id_zira"
        engine.getProperty.return_value = [v1]
        assert _resolve_voice(engine, "zIrA") == "id_zira"

    def test_first_match_returned(self):
        engine = MagicMock()
        v1 = MagicMock(); v1.name = "Voice Alpha"; v1.id = "id_a"
        v2 = MagicMock(); v2.name = "Voice Alpha Beta"; v2.id = "id_b"
        engine.getProperty.return_value = [v1, v2]
        assert _resolve_voice(engine, "Alpha") == "id_a"


# ------------------------------------------------------------------
# InterruptibleSpeaker
# ------------------------------------------------------------------

class TestInterruptibleSpeaker:
    @pytest.fixture
    def speaker(self, mock_tts, mock_stt, fake_config, mock_orchestrator):
        return InterruptibleSpeaker(mock_tts, mock_stt, mock_orchestrator, fake_config)

    def test_empty_text_returns_false(self, speaker):
        result = speaker.speak("")
        assert result is False

    def test_whitespace_only_returns_false(self, speaker):
        result = speaker.speak("   ")
        assert result is False

    def test_single_sentence_no_interrupt(self, speaker, mock_tts):
        result = speaker.speak("Hello world")
        assert result is False
        mock_tts.speak.assert_called_once_with("Hello world")

    def test_multi_sentence_no_interrupt(self, speaker, mock_tts, mock_stt):
        mock_stt.transcribe_once.return_value = ""
        result = speaker.speak("First sentence. Second sentence.")
        assert result is False
        assert mock_tts.speak.call_count == 2

    def test_interrupt_phrase_detected(self, speaker, mock_tts, mock_stt, mock_orchestrator):
        mock_stt.transcribe_once.return_value = "stop"
        result = speaker.speak("First sentence. Second sentence. Third one.")
        assert result is True
        # Should have spoken "First sentence" + "Go ahead."
        calls = [c.args[0] for c in mock_tts.speak.call_args_list]
        assert "First sentence" in calls[0]
        assert "Go ahead." in calls

    def test_hotkey_interrupt(self, speaker, mock_tts, mock_stt, mock_orchestrator):
        mock_orchestrator.interrupt_event.set()
        result = speaker.speak("One. Two. Three.")
        assert result is True
        # Should have spoken first sentence then "Go ahead."
        calls = [c.args[0] for c in mock_tts.speak.call_args_list]
        assert "Go ahead." in calls

    def test_sentence_splitting(self, speaker, mock_tts, mock_stt):
        mock_stt.transcribe_once.return_value = ""
        speaker.speak("Hello! How are you? I'm fine; thanks: bye.")
        # Splits on [.!?;:] followed by whitespace → 5 sentences:
        # "Hello!", "How are you?", "I'm fine;", "thanks:", "bye."
        assert mock_tts.speak.call_count == 5


class TestInterruptPhrases:
    def test_known_phrases(self):
        assert "stop" in INTERRUPT_PHRASES
        assert "let me interrupt" in INTERRUPT_PHRASES
        assert "listen up" in INTERRUPT_PHRASES

    def test_listen_sec_is_positive(self):
        assert INTERRUPT_LISTEN_SEC > 0
