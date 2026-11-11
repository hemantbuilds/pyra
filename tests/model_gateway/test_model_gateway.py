"""ModelGateway provider resolution and secret-handling tests (Phase 5c)."""

from __future__ import annotations

import os

import pytest
from pydantic_ai.models.test import TestModel

from master.config import SETTINGS
from master.model_gateway import ModelGateway, ProviderError
from master.provider_config import ProviderSettings, ProviderSpec, read_api_key


def test_default_provider_selection():
    gw = ModelGateway()
    status = gw.provider_status()
    assert status["default_provider"] in ("ollama", "test", "openai")
    assert "ollama" in status["providers"]
    assert "api_key" not in str(status).lower() or status["providers"]["openai"]["api_key_env"] == "OPENAI_API_KEY"


def test_test_provider_model():
    settings = ProviderSettings(
        default_provider="test",
        providers={
            "test": ProviderSpec(name="test", enabled=True, default_model="test"),
            "ollama": ProviderSpec(name="ollama", enabled=False, default_model="x", base_url="http://x/v1"),
        },
    )
    gw = ModelGateway(provider_settings=settings)
    model = gw.resolve_agent_model(provider="test")
    assert isinstance(model, TestModel)


def test_disabled_provider():
    settings = ProviderSettings(
        default_provider="openai",
        providers={
            "openai": ProviderSpec(
                name="openai",
                enabled=False,
                default_model="gpt-4o-mini",
                api_key_env="OPENAI_API_KEY",
            ),
        },
    )
    gw = ModelGateway(provider_settings=settings)
    with pytest.raises(ProviderError) as ei:
        gw.resolve_agent_model(provider="openai")
    assert ei.value.code == "provider_disabled"


def test_unknown_provider():
    gw = ModelGateway()
    with pytest.raises(ProviderError) as ei:
        gw.resolve_agent_model(provider="not-a-provider")
    assert ei.value.code == "unknown_provider"


def test_missing_openai_credentials(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = ProviderSettings(
        default_provider="openai",
        providers={
            "openai": ProviderSpec(
                name="openai",
                enabled=True,
                default_model="gpt-4o-mini",
                api_key_env="OPENAI_API_KEY",
            ),
        },
    )
    gw = ModelGateway(provider_settings=settings)
    with pytest.raises(ProviderError) as ei:
        gw.resolve_agent_model(provider="openai")
    assert ei.value.code == "missing_credentials"
    assert "sk-" not in str(ei.value)


def test_ollama_unavailable():
    settings = ProviderSettings(
        default_provider="ollama",
        providers={
            "ollama": ProviderSpec(
                name="ollama",
                enabled=True,
                default_model="qwen2.5:3b",
                base_url="http://127.0.0.1:9/v1",
            ),
        },
    )
    gw = ModelGateway(provider_settings=settings)
    gw.ollama_reachable = lambda: False  # type: ignore[method-assign]
    with pytest.raises(ProviderError) as ei:
        gw.resolve_agent_model(provider="ollama")
    assert ei.value.code == "provider_unavailable"


def test_override_model_isolation():
    gw = ModelGateway()
    m1 = TestModel(call_tools=[], custom_output_text="a")
    gw.set_override_model(m1)
    assert gw.resolve_agent_model() is m1
    gw.clear_override_model()
    # Without override, resolving ollama may fail if down — use test provider
    settings = ProviderSettings(
        default_provider="test",
        providers={"test": ProviderSpec(name="test", enabled=True, default_model="test")},
    )
    gw.provider_settings = settings
    assert isinstance(gw.resolve_agent_model(), TestModel)


def test_read_api_key_not_logged(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value-xyz")
    assert read_api_key("OPENAI_API_KEY") == "sk-secret-value-xyz"
    status = ProviderSettings.load().public_status()
    assert "sk-secret-value-xyz" not in str(status)


def test_public_status_has_no_secret_values(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-appear")
    st = ProviderSettings.load().public_status()
    assert "sk-should-not-appear" not in str(st)
    assert st["providers"]["openai"]["api_key_configured"] is True
