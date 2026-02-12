"""Custom exceptions for Copilot Echo error handling and resilience."""


class AgentCrashedError(Exception):
    """Raised when the Copilot CLI process appears to have crashed.

    Connection-type errors from the SDK (``ConnectionError``,
    ``EOFError``, etc.) are caught in :meth:`Agent._send` and re-raised
    as this exception so the caller can distinguish a crash from a
    transient error and attempt recovery.
    """


class DeviceDisconnectedError(Exception):
    """Raised when the audio input device is disconnected or unavailable.

    ``sounddevice.PortAudioError`` is caught in the STT and wake-word
    modules and re-raised as this exception so the voice loop can enter
    a device-recovery polling loop.
    """
