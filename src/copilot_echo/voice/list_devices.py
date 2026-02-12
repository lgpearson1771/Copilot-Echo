from __future__ import annotations

from copilot_echo.voice.audio import list_input_devices


def main() -> None:
    print("Input devices:")
    for index, name in list_input_devices():
        print(f"  {index}: {name}")


if __name__ == "__main__":
    main()
