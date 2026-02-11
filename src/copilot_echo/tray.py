from __future__ import annotations

import logging
import threading
import time

import pystray
from PIL import Image, ImageDraw

from copilot_echo.config import Config
from copilot_echo.orchestrator import Orchestrator, State
from copilot_echo.voice.loop import VoiceLoop


class TrayApp:
    def __init__(self, config: Config, orchestrator: Orchestrator) -> None:
        self.config = config
        self.orchestrator = orchestrator
        self.icon = pystray.Icon(
            name=config.app.name,
            title=config.app.name,
            icon=_build_icon(),
            menu=pystray.Menu(
                pystray.MenuItem("Pause", self._pause),
                pystray.MenuItem("Resume", self._resume),
                pystray.MenuItem("Stop", self._stop),
                pystray.MenuItem("Quit", self._quit),
            ),
        )

    def run(self) -> None:
        stop_event = threading.Event()
        voice_loop = VoiceLoop(self.config, self.orchestrator)
        voice_thread = threading.Thread(
            target=voice_loop.run,
            args=(self._set_title, stop_event),
            daemon=True,
        )
        voice_thread.start()

        # Start the caps-lock triple-tap hotkey listener
        hotkey_thread = threading.Thread(
            target=_caps_lock_listener,
            args=(self.orchestrator, stop_event),
            daemon=True,
        )
        hotkey_thread.start()

        self.icon.run()
        stop_event.set()
        voice_thread.join(timeout=2)

    def _pause(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.orchestrator.pause()
        self._set_title("Paused")

    def _resume(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.orchestrator.resume()
        self._set_title("Idle")

    def _quit(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.icon.stop()

    def _stop(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        """Tray 'Stop' button — interrupts autonomous mode or TTS."""
        self.orchestrator.request_interrupt()

    def _set_title(self, status: str) -> None:
        self.icon.title = f"{self.config.app.name} - {status}"


def _build_icon() -> Image.Image:
    size = 64
    image = Image.new("RGB", (size, size), color=(20, 20, 20))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, 56, 56), fill=(90, 200, 160))
    return image


# ------------------------------------------------------------------
# Global hotkey: triple-tap Caps Lock to interrupt
# ------------------------------------------------------------------

_CAPS_TAP_WINDOW = 0.6  # all 3 taps must happen within this many seconds


def _caps_lock_listener(orchestrator: Orchestrator, stop_event: threading.Event) -> None:
    """Listen for triple-tap of Caps Lock and fire interrupt."""
    try:
        from pynput import keyboard
    except ImportError:
        logging.warning("pynput not installed — caps-lock hotkey disabled")
        return

    tap_times: list[float] = []

    def on_press(key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if key != keyboard.Key.caps_lock:
            return
        now = time.time()
        tap_times.append(now)
        # Keep only taps within the window
        while tap_times and now - tap_times[0] > _CAPS_TAP_WINDOW:
            tap_times.pop(0)
        if len(tap_times) >= 3:
            tap_times.clear()
            logging.info("Triple-tap Caps Lock detected — requesting interrupt")
            orchestrator.request_interrupt()

    with keyboard.Listener(on_press=on_press) as listener:
        logging.info("Caps-lock triple-tap hotkey listener started")
        while not stop_event.is_set():
            stop_event.wait(timeout=1.0)
        listener.stop()
