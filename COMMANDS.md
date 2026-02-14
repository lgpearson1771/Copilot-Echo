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
./run.ps1 -m copilot_echo.voice.list_devices
```

## Voice Commands (in-app)

| Phrase | Effect |
| --- | --- |
| **"Hey Echo"** | Activates conversation mode |
| **"Stop listening"** | Pauses the listener |
| **"Resume listening"** / wake word (while paused) | Resumes the listener |
| **"Hold on a sec"** / **"Give me more time"** | Extends conversation window by 30s |
| **"Stop"** / **"Let me interrupt"** / **"Listen up"** | Interrupts TTS playback |
| **"Start a project called {name}"** | Creates a new project knowledge base |
| **"Finish / close / archive project {name}"** | Archives the project |
| **"List my projects"** | Reads out active and archived project names |
| **"Morning standup"** (or any configured trigger phrase) | Starts a pre-configured autonomous routine |
| **"Get to work on {task}"** | Starts an ad-hoc autonomous routine for the given task |
| **Triple-tap Caps Lock** | During autonomous TTS: stops speech and listens for direction (soft interrupt — say nothing to continue, give direction to guide the next step, or say "stop" to exit). During agent processing: cancels the request and exits autonomous mode. In normal conversation: interrupts TTS playback. |
| **Tray → Stop** | Same as hotkey — interrupts current operation |

## Configuration Files

| File | Purpose |
| --- | --- |
| `config/config.yaml` | Main configuration (gitignored, copy from `example.yaml`) |
| `config/knowledge.md` | Personal knowledge file for agent context (gitignored) |
| `config/projects/` | Project knowledge base files (active & archive, gitignored) |
| `config/example.yaml` | Template config checked into source control |
| `~/.copilot/config.json` | Global Copilot CLI config — MCP servers are loaded from here |
