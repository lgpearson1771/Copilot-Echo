from __future__ import annotations

import threading

import pystray
from PIL import Image, ImageDraw

from copilot_echo.config import Config
from copilot_echo.orchestrator import Orchestrator
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

    def _set_title(self, status: str) -> None:
        self.icon.title = f"{self.config.app.name} - {status}"


def _build_icon() -> Image.Image:
    size = 64
    image = Image.new("RGB", (size, size), color=(20, 20, 20))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, 56, 56), fill=(90, 200, 160))
    return image
