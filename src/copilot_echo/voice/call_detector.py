"""Detect active calls (Teams, Zoom) via Windows Audio Session API.

Polls both capture (microphone) and render (speaker) audio sessions to
determine whether a configured application is in an active call.
Checking render sessions is critical because the user may be muted
during a call — the render session (incoming audio from other
participants) stays active for the entire duration of the call.

When a call is detected the orchestrator is auto-paused; when the call
ends it is auto-resumed.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import psutil

from copilot_echo.config import Config
from copilot_echo.orchestrator import Orchestrator

# Optional: pycaw + comtypes for WASAPI audio-session detection.
try:
    import comtypes
    from pycaw.pycaw import AudioUtilities
    from pycaw.api.audiopolicy import IAudioSessionControl2, IAudioSessionManager2

    _HAS_PYCAW = True
except ImportError:  # pragma: no cover
    _HAS_PYCAW = False


# ------------------------------------------------------------------
# Audio session detection (WASAPI via pycaw / comtypes)
# ------------------------------------------------------------------

@dataclass
class AudioSession:
    """A process with an active audio session (capture or render)."""
    pid: int
    process_name: str


def get_active_audio_sessions() -> list[AudioSession]:
    """Return processes that currently have an active audio session.

    Enumerates both **capture** (microphone) and **render** (speaker)
    endpoints so that conferencing apps are detected even when the user
    is muted — they still have an active render session for incoming
    audio from other call participants.

    Returns an empty list on any COM or platform error so callers never
    need to handle exceptions.
    """
    if not _HAS_PYCAW:
        logging.debug("pycaw/comtypes not available — audio session detection disabled")
        return []

    sessions: list[AudioSession] = []
    seen_pids: set[int] = set()  # deduplicate across endpoints

    try:
        comtypes.CoInitialize()
        initialized_com = True
    except OSError:
        # COM already initialized on this thread
        initialized_com = False

    try:
        # eRender (0) = speaker/playback, eCapture (1) = microphone
        devices = _get_audio_endpoints(0) + _get_audio_endpoints(1)
        for device in devices:
            try:
                mgr = device.Activate(
                    IAudioSessionManager2._iid_, 0, None  # CLSCTX_ALL
                )
                mgr = mgr.QueryInterface(IAudioSessionManager2)
                enumerator = mgr.GetSessionEnumerator()
                count = enumerator.GetCount()

                for i in range(count):
                    ctl = enumerator.GetSession(i)
                    try:
                        ctl2 = ctl.QueryInterface(IAudioSessionControl2)
                        pid = ctl2.GetProcessId()
                        state = ctl.GetState()
                    except Exception:
                        continue

                    # Skip system sounds (PID 0), duplicates, and the audio engine
                    if pid == 0 or pid in seen_pids:
                        continue

                    # AudioSessionStateActive == 1
                    if state != 1:
                        continue

                    try:
                        proc_name = psutil.Process(pid).name()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

                    if proc_name.lower() == "audiodg.exe":
                        continue

                    seen_pids.add(pid)
                    sessions.append(AudioSession(pid=pid, process_name=proc_name))
            except Exception:
                logging.debug("Failed to enumerate sessions on audio device", exc_info=True)
    except Exception:
        logging.debug("Failed to enumerate audio devices", exc_info=True)
    finally:
        if initialized_com:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass

    return sessions


def _get_audio_endpoints(data_flow: int) -> list:
    """Return active audio endpoint devices.

    *data_flow*: 0 = eRender (playback/speaker), 1 = eCapture (microphone).
    """
    try:
        enumerator = AudioUtilities.GetDeviceEnumerator()
        collection = enumerator.EnumAudioEndpoints(data_flow, 0x1)  # DEVICE_STATE_ACTIVE
        count = collection.GetCount()
        return [collection.Item(i) for i in range(count)]
    except Exception:
        logging.debug("Could not enumerate audio endpoints (flow=%d)", data_flow, exc_info=True)
        return []


def is_call_active(app_names: set[str]) -> bool:
    """Check whether any of *app_names* have an active audio session.

    Checks both capture (mic) and render (speaker) sessions so calls
    are detected even when the user is muted.  Comparison is
    case-insensitive.
    """
    lower_names = {n.lower() for n in app_names}
    for session in get_active_audio_sessions():
        if session.process_name.lower() in lower_names:
            return True
    return False


# ------------------------------------------------------------------
# Background call-detector loop
# ------------------------------------------------------------------

class CallDetector:
    """Polls for active calls and auto-pauses/resumes the orchestrator.

    TTS notifications are intentionally omitted — pyttsx3 is not
    thread-safe and collides with the voice loop's TTS engine.  The
    tray icon shows "Paused (Call)" as visual feedback instead.
    """

    def __init__(
        self,
        config: Config,
        orchestrator: Orchestrator,
    ) -> None:
        self.config = config
        self.orchestrator = orchestrator

    def run(self, stop_event: threading.Event) -> None:
        """Main polling loop — runs on a background thread."""
        if not self.config.voice.auto_pause_on_call:
            logging.info("Call auto-pause disabled in config")
            return

        app_names = set(self.config.voice.auto_pause_apps)
        poll_interval = self.config.voice.auto_pause_poll_seconds
        logging.info(
            "Call detector started (apps=%s, poll=%.1fs)",
            sorted(app_names),
            poll_interval,
        )

        while not stop_event.is_set():
            try:
                in_call = is_call_active(app_names)
            except Exception:
                logging.debug("Audio session check failed", exc_info=True)
                in_call = False

            if in_call and not self.orchestrator.is_auto_paused:
                logging.info("Call detected — auto-pausing")
                self.orchestrator.auto_pause()
            elif not in_call and self.orchestrator.is_auto_paused:
                logging.info("Call ended — auto-resuming")
                self.orchestrator.auto_resume()

            stop_event.wait(timeout=poll_interval)

        logging.info("Call detector stopped")
