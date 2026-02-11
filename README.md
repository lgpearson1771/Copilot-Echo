# Copilot Echo

A local-only Windows tray app that listens for a wake word, routes voice commands to the GitHub Copilot SDK agent (with MCP server integrations), and reads responses aloud via text-to-speech.

## Features

- **Wake word detection** — always-listening via openwakeword (ONNX). Uses the built-in "hey jarvis" model by default; custom phrases require training a new model (see `docs/wakeword_training.md`).
- **Local speech-to-text** — faster-whisper (base model, CPU, int8) with VAD-based recording that captures your full utterance.
- **Local text-to-speech** — pyttsx3, sentence-by-sentence with interruptible playback.
- **Conversation mode** — after the wake word, stays in a listening loop (configurable window) so you can have multi-turn conversations without repeating the wake word.
- **Copilot SDK agent** — routes your voice input to GitHub Copilot via the `github-copilot-sdk`, with full async bridge.
- **MCP server integration** — automatically loads all MCP servers from the global Copilot CLI config (`~/.copilot/config.json`). Supports stdio servers with env merging, cwd auto-detection, and 60s startup timeout.
- **Knowledge file** — a personal markdown file injected into the agent's system prompt so it remembers your org, project, repos, and preferences across sessions.
- **System tray UI** — runs as a Windows tray icon with Pause / Resume / Quit controls and status display.
- **Voice commands** — built-in phrases for controlling the app hands-free (see below).

## Requirements

- Windows 10/11
- Python 3.11+
- GitHub Copilot CLI installed and authenticated (`copilot auth login`)
- MCP servers configured in `~/.copilot/config.json` (for Azure DevOps, etc.)

## Quick Start

```powershell
# 1. Create venv and install dependencies
./run.ps1 -m pip install -r requirements.txt
./run.ps1 -m pip install -e .

# 2. Copy and edit config
copy config\example.yaml config\config.yaml

# 3. (Optional) Create a personal knowledge file
copy NUL config\knowledge.md   # then edit it — see Knowledge File section

# 4. Run
./run.ps1 -m copilot_echo.app
```

Or use `run.bat` instead of `run.ps1`.

## Voice Commands

| Phrase | Effect |
| --- | --- |
| **"Hey Jarvis"** (wake word) | Activates conversation mode |
| **"Stop listening"** | Pauses the listener (tray shows Paused) |
| **"Resume listening"** or wake word while paused | Resumes the listener |
| **"Hold on a sec" / "Give me more time"** | Extends the conversation window by 30 seconds |
| **"Stop" / "Let me interrupt" / "Listen up"** | Interrupts TTS playback mid-sentence, says "Go ahead" |
| **"Start a project called {name}"** | Creates a new project knowledge base |
| **"Finish / close / archive project {name}"** | Archives the project |
| **"List my projects"** | Reads out active and archived project names |

## Knowledge File

Copilot Echo supports a **personal knowledge file** — a plain markdown file whose contents are injected into the agent's system prompt at startup. This lets you teach the agent facts it should always know without repeating them every session.

1. Create `config/knowledge.md` (gitignored — personal to each developer).
2. Set `agent.knowledge_file` in your `config/config.yaml`:

   ```yaml
   agent:
     knowledge_file: "config/knowledge.md"
   ```

3. Write any persistent context in markdown. Example:

   ```markdown
   # Agent Knowledge

   ## Azure DevOps
   - Organization: msazure
   - Default project: One
   - Primary repo: EngSys-MDA-MetricsAndHealth

   ## Preferences
   - Keep answers concise (voice assistant).
   ```

4. Restart the app. You'll see `Loaded knowledge file (N chars)` in the startup log.

## Project Knowledge Base

For long-running projects (weeks/months), Copilot Echo can maintain **per-project knowledge bases** that accumulate context over time — work items completed, PR outcomes, design decisions, blockers, and lessons learned.

- **"Start a project called {name}"** → creates a structured project file in `config/projects/active/`
- Active project files are **auto-injected** into the agent's system prompt alongside your knowledge file
- The agent **auto-captures** relevant activity (work items resolved, PRs merged, decisions made)
- **"Finish project {name}"** → archives the project, summarizes key takeaways into your knowledge file
- Archived projects can still be queried on demand

All project files are gitignored — each developer maintains their own.

See [docs/project_knowledge.md](docs/project_knowledge.md) for the full design, voice commands, lifecycle, and configuration.

## Configuration

Edit `config/config.yaml`. Key settings:

| Setting | Default | Description |
| --- | --- | --- |
| `voice.wakeword_engine` | `openwakeword` | `stt` (keyword match) or `openwakeword` (recommended) |
| `voice.wake_word` | `hey jarvis` | Wake phrase |
| `voice.wakeword_inference_framework` | `onnx` | `onnx` or `tflite` |
| `voice.wakeword_models` | `["hey jarvis"]` | Model names or paths under `models/` |
| `voice.wakeword_threshold` | `0.8` | Detection confidence threshold |
| `voice.conversation_window_seconds` | `5.0` | Silence timeout before exiting conversation mode |
| `voice.utterance_end_seconds` | `1.5` | Silence after speech that ends an utterance |
| `voice.stt_energy_threshold` | `0.01` | RMS energy level to detect speech |
| `voice.post_tts_cooldown_seconds` | `1.0` | Delay after TTS to avoid self-triggering |
| `voice.stt_model` | `base` | Whisper model size |
| `agent.knowledge_file` | `null` | Path to personal knowledge file |
| `agent.projects_dir` | `config/projects` | Directory for project knowledge bases |
| `agent.project_max_chars` | `4000` | Max chars per project file before summarization |

To list available audio input devices:

```powershell
./run.ps1 -m copilot_echo.voice.devices
```

Set `audio_device` (index) or `audio_device_name` (substring match) to select a mic.

### Custom Wake Word Models

1. Train a model with openwakeword's Colab notebook for your phrase.
2. Save the exported file under `models/` (e.g., `models/hey_echo.onnx`).
3. Set `wakeword_models: ["models/hey_echo.onnx"]` in config.

See `docs/wakeword_training.md` for a step-by-step guide.

## Architecture

```text
app.py              → Entry point, starts agent + tray
tray.py             → System tray icon (pystray), spawns voice loop thread
orchestrator.py     → State machine (Idle/Listening/Processing/Paused)
agent.py            → Async Copilot SDK bridge, MCP server loading, knowledge injection
voice/
  loop.py           → Main voice loop: wake word → conversation → agent → TTS
  wakeword.py       → Wake word detection (openwakeword / STT fallback)
  stt.py            → Speech-to-text (faster-whisper), fixed + VAD-based recording
  tts.py            → Text-to-speech (pyttsx3)
  audio.py          → Audio device resolution helpers
  devices.py        → CLI tool to list input devices
config.py           → Dataclass config, YAML loader
projects.py         → Project knowledge base management (create/archive/list/load)
```

## Roadmap

- [x] Wake word detection (openwakeword, ONNX)
- [x] Local STT with VAD-based utterance detection
- [x] Local TTS with sentence-by-sentence playback
- [x] Interruptible TTS via voice phrases
- [x] Conversation mode with configurable silence window
- [x] System tray icon with status display
- [x] Copilot SDK agent integration
- [x] MCP server auto-loading from global CLI config
- [x] Personal knowledge file for persistent agent context
- [x] Project knowledge base for long-running projects
- [ ] "Get to work" autonomous mode
- [ ] Teams/Zoom auto-pause integration
- [ ] Error handling & resilience hardening
- [ ] End-to-end testing
- [ ] Repo edit confirmation flow

See [docs/MVP.md](docs/MVP.md) for the full MVP progress tracker with detailed subtasks.
