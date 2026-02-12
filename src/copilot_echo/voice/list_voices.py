"""List available SAPI5 TTS voices on this machine.

Usage::

    python -m copilot_echo.voice.list_voices
"""
from __future__ import annotations

from collections.abc import Iterable

import pyttsx3


def list_voices() -> Iterable[tuple[str, str]]:
    """Yield ``(id, name)`` pairs for each installed TTS voice."""
    engine = pyttsx3.init()
    try:
        for voice in engine.getProperty("voices"):
            yield voice.id, voice.name
    finally:
        try:
            engine.stop()
        except Exception:
            pass


def main() -> None:
    print("Available TTS voices:")
    for voice_id, name in list_voices():
        print(f"  {name}")
        print(f"    ID: {voice_id}")


if __name__ == "__main__":
    main()
