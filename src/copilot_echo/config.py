from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import yaml


@dataclass
class AppConfig:
    name: str = "Copilot Echo"
    log_level: str = "INFO"


@dataclass
class VoiceConfig:
    wakeword_engine: str = "stt"
    wake_word: str = "hey copilot"
    audio_device: Optional[int] = None
    audio_device_name: Optional[str] = None
    sample_rate: int = 16000
    wake_listen_seconds: float = 2.5
    command_listen_seconds: float = 5.0
    wakeword_model_paths: List[str] = None  # type: ignore[assignment]
    wakeword_threshold: float = 0.6
    wakeword_chunk_size: int = 1280
    wakeword_holdoff_seconds: float = 1.0
    stt_model: str = "base"
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"


@dataclass
class RepoConfig:
    default_path: Optional[str] = None
    require_confirmation: bool = True


@dataclass
class ToolsConfig:
    allowlist: List[str]


@dataclass
class Config:
    app: AppConfig
    voice: VoiceConfig
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
        repo=RepoConfig(**data.get("repo", {})),
        tools=ToolsConfig(**data.get("tools", {})),
    )
