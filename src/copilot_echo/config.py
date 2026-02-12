from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class AppConfig:
    name: str = "Copilot Echo"
    log_level: str = "INFO"


@dataclass
class VoiceConfig:
    wakeword_engine: str = "stt"
    wake_word: str = "hey jarvis"
    audio_device: int | None = None
    audio_device_name: str | None = None
    sample_rate: int = 16000
    wake_listen_seconds: float = 2.5
    command_listen_seconds: float = 5.0
    utterance_end_seconds: float = 1.5
    max_listen_seconds: float = 60.0
    stt_energy_threshold: float = 0.01
    post_tts_cooldown_seconds: float = 0.5
    conversation_window_seconds: float = 30.0
    wakeword_inference_framework: str = "tflite"
    wakeword_models: list[str] = field(default_factory=list)
    wakeword_threshold: float = 0.6
    wakeword_chunk_size: int = 1280
    wakeword_holdoff_seconds: float = 1.0
    wakeword_vad_threshold: float = 0.0
    wakeword_speex_noise_suppression: bool = False
    stt_model: str = "base"
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"
    tts_voice: str | None = None
    tts_rate: int = 200
    tts_volume: float = 1.0
    auto_pause_on_call: bool = False
    auto_pause_apps: list[str] = field(
        default_factory=lambda: ["ms-teams.exe", "Teams.exe", "Zoom.exe"]
    )
    auto_pause_poll_seconds: float = 5.0


@dataclass
class AutonomousRoutine:
    name: str = ""
    trigger_phrases: list[str] = field(default_factory=list)
    prompt: str = ""
    max_steps: int | None = None  # overrides global default if set


@dataclass
class AgentConfig:
    knowledge_file: str | None = None
    projects_dir: str = "config/projects"
    project_max_chars: int = 4000
    autonomous_routines: list[AutonomousRoutine] = field(default_factory=list)
    autonomous_max_steps: int = 10
    autonomous_max_minutes: int = 10


@dataclass
class RepoConfig:
    default_path: str | None = None
    require_confirmation: bool = True


@dataclass
class ToolsConfig:
    allowlist: list[str]


@dataclass
class Config:
    app: AppConfig
    voice: VoiceConfig
    agent: AgentConfig
    repo: RepoConfig
    tools: ToolsConfig


def load_config() -> Config:
    root = Path(__file__).resolve().parents[2]
    path = root / "config" / "config.yaml"

    if not path.exists():
        path = root / "config" / "example.yaml"

    data = yaml.safe_load(path.read_text(encoding="utf-8"))

    return Config(
        app=AppConfig(**data.get("app", {})),
        voice=VoiceConfig(**data.get("voice", {})),
        agent=_load_agent_config(data.get("agent", {})),
        repo=RepoConfig(**data.get("repo", {})),
        tools=ToolsConfig(**data.get("tools", {})),
    )


def _load_agent_config(data: dict) -> AgentConfig:
    """Build AgentConfig, converting raw routine dicts to dataclasses."""
    routines_raw = data.pop("autonomous_routines", [])
    cfg = AgentConfig(**data)
    if routines_raw:
        cfg.autonomous_routines = [
            AutonomousRoutine(**r) for r in routines_raw
        ]
    return cfg
