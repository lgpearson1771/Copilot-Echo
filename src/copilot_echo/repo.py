from __future__ import annotations

from pathlib import Path


class RepoResolver:
    def __init__(self, default_path: str | None) -> None:
        self.default_path = default_path

    def resolve(self) -> Path:
        # TODO: Prompt user or read config to pick a repo.
        if not self.default_path:
            raise ValueError("No default repo path configured")
        return Path(self.default_path)
