from __future__ import annotations

from collections.abc import Iterable

import sounddevice as sd


def list_input_devices() -> Iterable[tuple[int, str]]:
    devices = sd.query_devices()
    for index, device in enumerate(devices):
        if device.get("max_input_channels", 0) > 0:
            yield index, device.get("name", "Unknown")


def resolve_input_device(
    device_index: int | None, device_name: str | None
) -> int | None:
    if device_index is not None:
        return device_index

    if not device_name:
        return None

    target = device_name.lower()
    for index, name in list_input_devices():
        if target in name.lower():
            return index

    return None
