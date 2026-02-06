# Copilot Echo

A local-only Windows tray app that listens for a wake word, uses GitHub Copilot SDK to fetch Azure DevOps work items via MCP, reads them aloud, and performs repo changes with confirmation.

## Status
Starter scaffold. Voice pipeline, tray UI, and Copilot SDK wiring are stubbed.

## Requirements
- Windows 10/11
- Python 3.11+
- GitHub Copilot CLI installed and authenticated
- Copilot CLI MCP config already set up for Azure DevOps

## Quick start
1) Create and activate a virtual environment.
2) Install dependencies:
   - `./run.ps1 -m pip install -r requirements.txt`
   - Or: `run.bat -m pip install -r requirements.txt`
3) Install editable package:
   - `./run.ps1 -m pip install -e .`
   - Or: `run.bat -m pip install -e .`
4) Copy the config:
   - `copy config\example.yaml config\config.yaml`
5) Run:
   - `./run.ps1 -m copilot_echo.app`
   - Or: `run.bat -m copilot_echo.app`

## Configuration
Edit `config\config.yaml` for wake word, audio device, repo path, and tool allowlist.

To list audio input devices:

```
./run.ps1 -m copilot_echo.voice.devices
```

Set either `audio_device` (index) or `audio_device_name` (substring match) in config.

Wake word engines:
- `stt`: keyword check via short transcription (simple, less strict)
- `openwakeword`: real wake word engine (recommended). Configure `wakeword_model_paths` if you want to use custom models.

Openwakeword supports selecting a specific model by name. Examples from the default set:
`alexa`, `hey mycroft`, `hey jarvis`, `hey rhasspy`, `current weather`, `timers`.
Set `wakeword_models` to a single name to avoid triggering on other phrases.

Custom wake word models:
1) Train a model with openwakeword's Colab notebook for your phrase (e.g., "hey copilot").
2) Save the exported model file under `models/` (for example, `models/hey_copilot.tflite`).
3) Set `wakeword_engine: "openwakeword"` and `wakeword_models: ["models/hey_copilot.tflite"]`.

Guide: see `docs/wakeword_training.md` for training "hey echo".

## Roadmap
- Wire wake word and local STT/TTS
- Implement tray icon and status
- Add MCP-based work item lookup
- Add repo edit confirmation flow
- Add Teams auto-pause
