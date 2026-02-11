# Commands

Use the local virtual environment for all Python commands.
Substitute `run.bat` for `run.ps1` if preferred.

## Install dependencies

```powershell
./run.ps1 -m pip install -r requirements.txt
```

## Install editable package

```powershell
./run.ps1 -m pip install -e .
```

## Run the app

```powershell
./run.ps1 -m copilot_echo.app
```

## List audio input devices

```powershell
./run.ps1 -m copilot_echo.voice.devices
```

## Voice Commands (in-app)

| Phrase | Effect |
| --- | --- |
| **"Hey Jarvis"** | Activates conversation mode |
| **"Stop listening"** | Pauses the listener |
| **"Resume listening"** / wake word (while paused) | Resumes the listener |
| **"Hold on a sec"** / **"Give me more time"** | Extends conversation window by 30s |
| **"Stop"** / **"Let me interrupt"** / **"Listen up"** | Interrupts TTS playback |

## Configuration Files

| File | Purpose |
| --- | --- |
| `config/config.yaml` | Main configuration (gitignored, copy from `example.yaml`) |
| `config/knowledge.md` | Personal knowledge file for agent context (gitignored) |
| `config/example.yaml` | Template config checked into source control |
| `~/.copilot/config.json` | Global Copilot CLI config — MCP servers are loaded from here |
