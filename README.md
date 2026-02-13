# Copilot Echo

A local-only Windows tray app that listens for a wake word, routes voice commands to the GitHub Copilot SDK agent (with MCP server integrations), and reads responses aloud via text-to-speech.

## Features

- **Wake word detection** — always-listening via openwakeword (ONNX). Ships with a custom-trained "hey echo" model; custom phrases can be trained using [openwakeword-trainer](https://github.com/lgpearson1771/openwakeword-trainer).
- **Local speech-to-text** — faster-whisper (base model, CPU, int8) with VAD-based recording that captures your full utterance.
- **Local text-to-speech** — pyttsx3, sentence-by-sentence with interruptible playback.
- **Conversation mode** — after the wake word, stays in a listening loop (configurable window) so you can have multi-turn conversations without repeating the wake word.
- **Copilot SDK agent** — routes your voice input to GitHub Copilot via the `github-copilot-sdk`, with full async bridge.
- **MCP server integration** — automatically loads all MCP servers from the global Copilot CLI config (`~/.copilot/config.json`). Also runs a local project knowledge MCP server so the agent can read and write project files autonomously. Supports stdio servers with env merging, cwd auto-detection, and 60s startup timeout.
- **Knowledge file** — a personal markdown file injected into the agent's system prompt so it remembers your org, project, repos, and preferences across sessions.
- **System tray UI** — runs as a Windows tray icon with Pause / Resume / Stop / Quit controls and status display.
- **"Get to Work" autonomous mode** — pre-configured routines (standup prep, PR review) and ad-hoc "get to work on {task}" for multi-step agent workflows. The agent works step-by-step, speaking progress aloud, with interruptible playback and safety limits.
- **Teams/Zoom auto-pause** — automatically pauses the listener when a configured app (Teams, Zoom) is in an active call, detected via Windows Audio Session API (both render and capture endpoints so muting doesn't cause a false resume). Resumes when the call ends. Fully configurable.
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
| **"Hey Echo"** (wake word) | Activates conversation mode |
| **"Stop listening"** | Pauses the listener (tray shows Paused) |
| **"Resume listening"** or wake word while paused | Resumes the listener |
| **"Hold on a sec" / "Give me more time"** | Extends the conversation window by 30 seconds |
| **"Stop" / "Let me interrupt" / "Listen up"** | Interrupts TTS playback mid-sentence, says "Go ahead" |
| **"Start a project called {name}"** | Creates a new project knowledge base |
| **"Finish / close / archive project {name}"** | Archives the project |
| **"List my projects"** | Reads out active and archived project names |
| **"Morning standup"** (or configured trigger) | Starts a pre-configured autonomous routine |
| **"Get to work on {task}"** | Starts an ad-hoc autonomous routine for the given task |
| **"Stop" / interrupt phrases** (during routine) | Stops autonomous mode and returns to conversation |
| **Triple-tap Caps Lock** | Instantly interrupts TTS or autonomous mode (even mid-agent-call) |
| **Tray → Stop** | Same as hotkey — interrupts current operation |

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
- The agent **auto-captures** relevant activity using MCP tools — appending entries for work items resolved, PRs merged, decisions made, and blockers
- When a project file approaches the character cap, the agent autonomously **summarizes** older entries to stay within limits
- **"Finish project {name}"** → archives the project, summarizes key takeaways into your knowledge file
- Archived projects are **loaded on demand** — the agent sees their names and autonomously loads context when relevant to a question

All project files are gitignored — each developer maintains their own.

See [docs/project_knowledge.md](docs/project_knowledge.md) for the full design, voice commands, lifecycle, and configuration.

## Autonomous Mode ("Get to Work")

Copilot Echo can execute multi-step agent workflows autonomously — the agent works step by step, speaking progress aloud, while you listen (or interrupt at any point).

### Pre-configured Routines

Define routines in `config/config.yaml`:

```yaml
agent:
  autonomous_max_steps: 10
  autonomous_max_minutes: 10
  autonomous_routines:
    - name: "Morning Standup"
      trigger_phrases: ["morning standup", "daily standup"]
      prompt: >
        Prepare my morning standup summary. Check my active work items,
        review any PRs I'm assigned to, and summarize what I worked on
        yesterday.
      max_steps: 5
```

Say any trigger phrase (e.g. "morning standup") during conversation mode to start the routine.

### Ad-hoc Tasks

Say **"get to work on {task}"** for any one-off autonomous workflow:

> "Hey Echo… get to work on reviewing the open PRs for the metrics repo"

### How It Works

1. The agent receives your routine/task as a structured prompt with instructions to work step by step.
2. After each step, the agent speaks a concise summary and signals `NEXT` (more to do) or `DONE` (finished).
3. Between steps, the mic listens briefly — say **"stop"** or any interrupt phrase to halt and return to conversation mode.
4. Safety limits (`autonomous_max_steps`, `autonomous_max_minutes`) prevent runaway loops.

### Stopping a Routine

You have three ways to interrupt an autonomous routine:

- **Voice** — say "stop", "let me interrupt", or "listen up" between sentences or steps
- **Triple-tap Caps Lock** — works instantly, even while the agent is processing or TTS is speaking (cancels the in-flight agent request)
- **Tray → Stop** — right-click the tray icon and click Stop

After interrupting, you return to conversation mode and can keep chatting.

## Configuration

Edit `config/config.yaml`. Key settings:

| Setting | Default | Description |
| --- | --- | --- |
| `voice.wakeword_engine` | `openwakeword` | `stt` (keyword match) or `openwakeword` (recommended) |
| `voice.wake_word` | `hey echo` | Wake phrase |
| `voice.wakeword_inference_framework` | `onnx` | `onnx` or `tflite` |
| `voice.wakeword_models` | `["models/hey_echo.onnx"]` | Model names or paths under `models/` |
| `voice.wakeword_threshold` | `0.8` | Detection confidence threshold |
| `voice.conversation_window_seconds` | `5.0` | Silence timeout before exiting conversation mode |
| `voice.utterance_end_seconds` | `1.5` | Silence after speech that ends an utterance |
| `voice.stt_energy_threshold` | `0.01` | RMS energy level to detect speech |
| `voice.post_tts_cooldown_seconds` | `1.0` | Delay after TTS to avoid self-triggering |
| `voice.tts_voice` | `null` | Substring match against SAPI5 voice name (e.g. `"David"`) |
| `voice.tts_rate` | `200` | TTS speech rate in words per minute |
| `voice.tts_volume` | `1.0` | TTS playback volume (0.0–1.0) |
| `voice.stt_model` | `base` | Whisper model size |
| `agent.knowledge_file` | `null` | Path to personal knowledge file |
| `agent.projects_dir` | `config/projects` | Directory for project knowledge bases |
| `agent.project_max_chars` | `4000` | Max chars per project file before summarization |
| `agent.autonomous_max_steps` | `10` | Max agent round-trips per autonomous routine |
| `agent.autonomous_max_minutes` | `10` | Hard time limit per autonomous routine |
| `agent.autonomous_routines` | `[]` | List of pre-configured routines (see example.yaml) |
| `voice.auto_pause_on_call` | `false` | Auto-pause listener during Teams/Zoom calls |
| `voice.auto_pause_apps` | `["ms-teams.exe", "Teams.exe", "Zoom.exe"]` | Process names to detect as active calls |
| `voice.auto_pause_poll_seconds` | `5.0` | How often to check for active calls |

To list available audio input devices:

```powershell
./run.ps1 -m copilot_echo.voice.list_devices
```

Set `audio_device` (index) or `audio_device_name` (substring match) to select a mic.

### TTS Voice & Speed

Copilot Echo uses the system default SAPI5 voice by default. To change the voice, speech rate, or volume, add these settings to your `config/config.yaml`:

```yaml
voice:
  tts_voice: "David"    # substring match against installed voice name
  tts_rate: 180          # words per minute (default 200, range 100–300)
  tts_volume: 0.8        # 0.0–1.0 (default 1.0)
```

To see which voices are installed on your machine:

```powershell
./run.ps1 -m copilot_echo.voice.list_voices
```

Use any substring from the voice name (e.g. `"Zira"`, `"David"`, `"Hazel"`). If the configured name doesn't match any installed voice, the system default is used and a warning is logged.

### Custom Wake Word Models

To train your own custom wake word (e.g., "hey computer", "ok assistant"), use the companion training toolkit:

**[openwakeword-trainer](https://github.com/lgpearson1771/openwakeword-trainer)** — A granular 13-step pipeline that handles TTS synthesis, augmentation, training, and ONNX export.

1. Train a model using openwakeword-trainer.
2. Copy the exported `.onnx` (and `.onnx.data`) files to `models/`.
3. Update `config/config.yaml`:

   ```yaml
   voice:
     wake_word: "your phrase"
     wakeword_models: ["models/your_model.onnx"]
     wakeword_threshold: 0.5
   ```

## Architecture

```text
app.py              → Entry point, starts agent + tray
tray.py             → System tray icon (pystray), Caps Lock hotkey listener, spawns voice loop thread
orchestrator.py     → State machine (Idle/Listening/Processing/Autonomous/Paused)
agent.py            → Async Copilot SDK bridge (slim — delegates config to prompt_builder)
paths.py            → Shared project root path utility
config.py           → Dataclass config, YAML loader
mcp_config.py       → MCP server loading from global CLI config + project MCP registration
prompt_builder.py   → System prompt assembly, knowledge file loading, session config
projects.py         → Project knowledge base management (create/archive/list/load)
project_mcp.py      → Local MCP server exposing project knowledge tools to the agent
voice/
  loop.py           → Main voice loop: wake word → conversation → agent → TTS
  commands.py       → Voice command handler for project knowledge base commands
  autonomous.py     → Autonomous "Get to Work" mode with interrupt watcher
  call_detector.py  → Teams/Zoom auto-pause via Windows Audio Session API (render + capture)
  wakeword.py       → Wake word detection (openwakeword / STT fallback)
  stt.py            → Speech-to-text (faster-whisper), fixed + VAD-based recording
  tts.py            → Text-to-speech (pyttsx3), interruptible sentence-by-sentence speaker
  audio.py          → Audio device resolution helpers
  list_devices.py   → CLI tool to list input devices
  list_voices.py    → CLI tool to list available TTS voices
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
- [x] "Get to work" autonomous mode
- [x] Comprehensive unit test suite (294 tests, 84% coverage)
- [x] Teams/Zoom auto-pause integration
- [ ] Error handling & resilience hardening
- [ ] Repo edit confirmation flow

See [docs/MVP.md](docs/MVP.md) for the full MVP progress tracker with detailed subtasks.
