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

- [x] Tray icon with status display (Idle / Conversation / Processing / Paused)
- [x] Pause / Resume / Quit menu items

## Documentation — DONE

- [x] README with features, setup, voice commands, configuration, architecture
- [x] COMMANDS.md with dev commands and voice command reference
- [x] example.yaml with all current settings and comments
- [x] Knowledge file section in README
- [x] Wake word training guide (docs/wakeword_training.md)

---

## Remaining MVP Work

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

### "Get to Work" Autonomous Mode

> Voice command that tells the agent to work through a plan autonomously
> (e.g., triage work items, summarize PRs, run a checklist) with periodic
> voice status updates.

- [ ] Define supported autonomous workflows (daily standup prep, PR review, etc.)
- [ ] Add "get to work" / "start your routine" voice command detection in loop.py
- [ ] Build autonomous loop: agent sends itself follow-up prompts from a plan
- [ ] Periodic TTS status updates ("Checked 3 PRs, 2 need your attention")
- [ ] Interrupt support during autonomous mode (voice phrase to stop/redirect)
- [ ] Config: `agent.autonomous_routines` or similar for user-defined workflows

### Teams Auto-Pause

> Automatically pause the listener when a Teams/Zoom call is active to avoid
> picking up meeting audio, and resume when the call ends.

- [ ] Detect active Teams/Zoom call (process detection, audio session, or window title)
- [ ] Auto-pause orchestrator when call detected
- [ ] Auto-resume when call ends
- [ ] TTS notification on pause/resume ("Pausing for your call" / "Call ended, listening again")
- [ ] Config: `voice.auto_pause_on_call` toggle
- [ ] Config: `voice.auto_pause_apps` list (default: Teams, Zoom)

### Error Handling & Resilience

- [ ] Graceful recovery when Copilot CLI process crashes mid-session
- [ ] Retry logic for transient MCP server failures
- [ ] User-facing TTS error messages instead of silent failures
- [ ] Handle microphone disconnection / device change gracefully

### Testing & Polish

- [ ] End-to-end smoke test: wake word → question → agent reply → TTS
- [ ] Test all voice commands work reliably
- [ ] Test conversation mode timeout / extension behavior
- [ ] Test interrupt phrases during long TTS responses
- [ ] Test pause/resume cycle
- [ ] Verify knowledge file loads and agent uses the context
- [ ] Test with multiple MCP servers active simultaneously

---

## Post-MVP / Nice to Have

- [ ] Repo edit confirmation flow (agent proposes edits, user confirms by voice)
- [ ] Custom wake word model training (currently limited to built-in phrases)
- [ ] TTS voice selection / speed configuration
- [ ] Conversation history / session logging
- [ ] Multi-language STT support
- [ ] GPU acceleration for STT (CUDA)
