"""Environment-backed Master configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8765
    token: str = "dev-local-token"
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:3b"
    work_root: Path = Path.home() / "PyraWork"
    request_timeout_s: float = 45.0

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            host=_env("PYRA_HOST", "127.0.0.1"),
            port=int(_env("PYRA_PORT", "8765")),
            token=_env("PYRA_TOKEN", "dev-local-token"),
            ollama_host=_env("OLLAMA_HOST", "http://127.0.0.1:11434"),
            ollama_model=_env("OLLAMA_MODEL", "qwen2.5:3b"),
            work_root=Path(_env("PYRA_WORK_ROOT", str(Path.home() / "PyraWork"))).expanduser(),
            request_timeout_s=float(_env("PYRA_TIMEOUT_S", "45")),
        )


SETTINGS = Settings.load()
