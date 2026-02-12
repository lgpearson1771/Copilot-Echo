# MVP Progress Tracker

What needs to be done before Copilot Echo is ready for a full launch.

---

## Core Voice Pipeline — DONE

- [x] Wake word detection (openwakeword, ONNX, "hey jarvis")
- [x] Local STT with VAD-based utterance detection (faster-whisper)
- [x] Local TTS with sentence-by-sentence playback (pyttsx3)
- [x] Interruptible TTS via voice phrases ("stop", "let me interrupt", "listen up")
- [x] Conversation mode with configurable silence window
- [x] Voice commands: "stop listening", "resume listening", "hold on a sec"

## Agent & MCP Integration — DONE

- [x] Copilot SDK agent integration (async bridge, sync API for voice loop)
- [x] MCP server auto-loading from global CLI config (`~/.copilot/config.json`)
- [x] MCP env merging, cwd auto-detection, 60s startup timeout
- [x] Auto-permission approval for MCP tool calls
- [x] Personal knowledge file injected into system prompt

## System Tray — DONE

- [x] Tray icon with status display (Idle / Conversation / Processing / Working / Paused)
- [x] Pause / Resume / Stop / Quit menu items
- [x] Triple-tap Caps Lock global hotkey to interrupt (via pynput)

## Documentation — DONE

- [x] README with features, setup, voice commands, configuration, architecture
- [x] COMMANDS.md with dev commands and voice command reference
- [x] example.yaml with all current settings and comments
- [x] Knowledge file section in README
- [x] Wake word training guide (docs/wakeword_training.md)

---

## Remaining MVP Work

> **Recommended build order:** Testing & Polish → Teams Auto-Pause →
> Error Handling & Resilience.  Testing is next so the core pipeline,
> project KB, and autonomous mode are validated end-to-end before adding
> more features on top.  Error handling goes last because it's a
> hardening pass that benefits from having all features in place first.
### Project Knowledge Base \u2014 DONE

> Per-project knowledge files that accumulate context over a project's
> lifetime — work items, PRs, decisions, blockers, lessons learned.
> See [docs/project_knowledge.md](project_knowledge.md) for the full design.

- [x] Create `config/projects/active/` and `archive/` directory structure
- [x] Voice command: "start a project called {name}" → create project file from template
- [x] Voice command: "finish project {name}" → archive project, summarize to knowledge.md
- [x] Voice command: "list my projects" → read active/archived project names
- [x] Inject all active project files into agent system prompt at startup
- [x] Auto-capture: agent appends work item/PR/decision entries during conversations
- [x] Size management: summarize older entries when project file approaches cap
- [x] On-demand loading of archived projects when user asks about past work
- [x] Config: `agent.projects_dir`, `agent.project_max_chars`

### "Get to Work" Autonomous Mode — DONE

> Voice command that tells the agent to work through a plan autonomously
> (e.g., triage work items, summarize PRs, run a checklist) with periodic
> voice status updates.

- [x] Define supported autonomous workflows (daily standup prep, PR review, etc.)
- [x] Add "get to work" / trigger phrase voice command detection in loop.py
- [x] Build autonomous loop: agent sends itself follow-up prompts step by step
- [x] Periodic TTS status updates with interruptible sentence-by-sentence playback
- [x] Interrupt support: voice phrases between sentences/steps
- [x] Interrupt support: triple-tap Caps Lock hotkey (instant, cancels mid-flight agent call)
- [x] Interrupt support: tray Stop button
- [x] Ad-hoc "get to work on {task}" for one-off autonomous tasks
- [x] Config: `agent.autonomous_routines`, `autonomous_max_steps`, `autonomous_max_minutes`

### Teams Auto-Pause — DONE

> Automatically pause the listener when a Teams/Zoom call is active to avoid
> picking up meeting audio, and resume when the call ends.

- [x] Detect active Teams/Zoom call (audio session detection via WASAPI — render + capture endpoints)
- [x] Auto-pause orchestrator when call detected
- [x] Auto-resume when call ends
- [x] Visual notification on pause/resume (tray shows "Paused (Call)" status)
- [x] Config: `voice.auto_pause_on_call` toggle
- [x] Config: `voice.auto_pause_apps` list (default: Teams, Zoom)

### Error Handling & Resilience

- [ ] Graceful recovery when Copilot CLI process crashes mid-session
- [ ] Retry logic for transient MCP server failures
- [ ] User-facing TTS error messages instead of silent failures
- [ ] Handle microphone disconnection / device change gracefully

### Testing & Polish — DONE

> Comprehensive pytest-based unit test suite covering all modules.
> 294 tests, 84% overall coverage. All hardware dependencies mocked
> (audio, TTS, STT, Copilot SDK, pystray, pynput, openwakeword).
> Test infrastructure: pytest + pytest-asyncio + pytest-cov.

- [x] Unit tests for Orchestrator (state transitions, send_to_agent, cancel, autonomous lifecycle, auto-pause) — 29 tests, 100% coverage
- [x] Unit tests for Agent (init, send, cancel, async startup/shutdown, tool logging) — 17 tests, 68% coverage
- [x] Unit tests for Config (dataclass defaults, YAML loading, autonomous routines) — 13 tests, 92% coverage
- [x] Unit tests for MCP config (server loading, sanitization, env merging, project MCP) — 14 tests, 100% coverage
- [x] Unit tests for Projects (slugify, create, archive, list, load, append, replace, read) — 39 tests, 93% coverage
- [x] Unit tests for Project MCP tools (list, get, append, compact, file chars) — 11 tests, 92% coverage
- [x] Unit tests for Prompt Builder (system prompt, knowledge loading, session config, permissions) — 15 tests, 94% coverage
- [x] Unit tests for Paths — 3 tests, 100% coverage
- [x] Unit tests for Logging — 3 tests, 100% coverage
- [x] Unit tests for Tray (icon, title, callbacks, caps lock triple-tap) — 9 tests, 53% coverage
- [x] Unit tests for Voice Loop (paused state, auto-pause, conversation loop, commands, autonomous, agent replies) — 11 tests, 89% coverage
- [x] Unit tests for Voice Commands (pattern matching, execution, name extraction, regex) — 36 tests, 86% coverage
- [x] Unit tests for Autonomous Mode (strip_marker, interrupt phrases, triggers, run loop, interrupt watcher) — 31 tests, 91% coverage
- [x] Unit tests for TTS (speak, interruptible, sentence splitting, interrupt phrases) — 13 tests, 93% coverage
- [x] Unit tests for STT (init, transcribe_once, transcribe_until_silence) — 6 tests, 75% coverage
- [x] Unit tests for Wake Word Detector (STT engine, openwakeword dispatch, _is_triggered) — 13 tests, 71% coverage
- [x] Unit tests for Call Detector (audio session detection, WASAPI enumeration, polling loop) — 22 tests, 80% coverage
- [x] Unit tests for Audio (resolve_input_device, list_input_devices) — 9 tests, 100% coverage

---

## Post-MVP / Nice to Have

- [ ] Repo edit confirmation flow (agent proposes edits, user confirms by voice)
- [ ] Custom wake word model training (currently limited to built-in phrases)
- [ ] TTS voice selection / speed configuration
- [ ] Conversation history / session logging
- [ ] Multi-language STT support
- [ ] GPU acceleration for STT (CUDA)
