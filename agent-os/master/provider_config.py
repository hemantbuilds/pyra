"""Model provider configuration (Phase 5c) — separate from secrets."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    enabled: bool
    default_model: str
    base_url: str = ""
    # Name of env var holding the API key — never the secret itself.
    api_key_env: Optional[str] = None


@dataclass
class ProviderSettings:
    """Non-secret provider settings loaded from environment."""

    default_provider: str = "ollama"
    providers: dict[str, ProviderSpec] = field(default_factory=dict)

    @classmethod
    def load(cls) -> "ProviderSettings":
        ollama_host = _env("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
        # PydanticAI OllamaProvider expects OpenAI-compatible /v1 base.
        ollama_v1 = ollama_host if ollama_host.endswith("/v1") else f"{ollama_host}/v1"
        ollama_model = _env("OLLAMA_MODEL", "qwen2.5:3b")
        default_provider = _env("PYRA_DEFAULT_PROVIDER", "ollama").lower() or "ollama"

        providers = {
            "ollama": ProviderSpec(
                name="ollama",
                enabled=_env("PYRA_OLLAMA_ENABLED", "true").lower() in ("1", "true", "yes"),
                default_model=ollama_model,
                base_url=ollama_v1,
                api_key_env=None,
            ),
            "openai": ProviderSpec(
                name="openai",
                enabled=_env("PYRA_OPENAI_ENABLED", "false").lower() in ("1", "true", "yes"),
                default_model=_env("PYRA_OPENAI_MODEL", "gpt-4o-mini"),
                base_url=_env("PYRA_OPENAI_BASE_URL", "https://api.openai.com/v1"),
                api_key_env="OPENAI_API_KEY",
            ),
            "test": ProviderSpec(
                name="test",
                enabled=True,
                default_model="test",
                base_url="",
                api_key_env=None,
            ),
        }
        return cls(default_provider=default_provider, providers=providers)

    def get(self, name: str) -> ProviderSpec:
        key = (name or "").strip().lower()
        if key not in self.providers:
            raise KeyError(f"unknown provider: {name}")
        return self.providers[key]

    def public_status(self) -> dict[str, Any]:
        """Safe status for APIs/logs — never includes secrets."""
        out = {"default_provider": self.default_provider, "providers": {}}
        for name, spec in self.providers.items():
            out["providers"][name] = {
                "enabled": spec.enabled,
                "default_model": spec.default_model,
                "base_url": spec.base_url,
                "api_key_configured": bool(
                    spec.api_key_env and _env(spec.api_key_env, "")
                ),
                "api_key_env": spec.api_key_env,
            }
        return out


def read_api_key(env_name: Optional[str]) -> Optional[str]:
    if not env_name:
        return None
    val = _env(env_name, "")
    return val or None
