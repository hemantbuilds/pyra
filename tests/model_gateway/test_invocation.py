"""Phase 5d — ModelGateway invoke, retry, cancel, structured JSON, concurrency."""

from __future__ import annotations

import threading
import time

import pytest

from master.config import Settings
from master.invocation import (
    CancellationToken,
    CancelledError,
    FailureKind,
    RetryPolicy,
    classify_http_error,
)
from master.model_gateway import ModelGateway
from master.provider_config import ProviderSettings, ProviderSpec


@pytest.fixture
def gw_local():
    settings = Settings(
        ollama_host="http://127.0.0.1:9",
        ollama_model="qwen2.5:3b",
        gateway_timeout_s=2.0,
        gateway_max_retries=1,
        gateway_retry_backoff_s=0.01,
    )
    providers = ProviderSettings(
        default_provider="ollama",
        providers={
            "ollama": ProviderSpec(
                name="ollama",
                enabled=True,
                default_model="qwen2.5:3b",
                base_url="http://127.0.0.1:9/v1",
            ),
            "test": ProviderSpec(name="test", enabled=True, default_model="test"),
        },
    )
    return ModelGateway(settings=settings, provider_settings=providers)


def test_retry_policy_transient_only():
    p = RetryPolicy(max_retries=2)
    assert p.allow(FailureKind.TIMEOUT, 0) is True
    assert p.allow(FailureKind.TIMEOUT, 2) is False
    assert p.allow(FailureKind.AUTH, 0) is False
    assert p.allow(FailureKind.CANCELLED, 0) is False
    assert p.allow(FailureKind.MODEL_UNAVAILABLE, 0) is False


def test_classify_http_error():
    assert classify_http_error(TimeoutError("x")) == FailureKind.TIMEOUT
    assert classify_http_error(ConnectionError("refused")) == FailureKind.CONNECTION
    assert classify_http_error(CancelledError("c")) == FailureKind.CANCELLED


def test_complete_text_provider_unavailable(gw_local):
    gw_local.ollama_reachable = lambda: False  # type: ignore[method-assign]
    res = gw_local.complete_text("hello")
    assert res.ok is False
    assert res.failure_kind == FailureKind.PROVIDER_UNAVAILABLE


def test_complete_text_model_unavailable(gw_local):
    gw_local.ollama_reachable = lambda: True  # type: ignore[method-assign]
    gw_local.list_ollama_models = lambda: [{"name": "other:1b"}]  # type: ignore[method-assign]
    res = gw_local.complete_text("hello", model="missing:7b")
    assert res.ok is False
    assert res.failure_kind == FailureKind.MODEL_UNAVAILABLE


def test_complete_text_success_and_metadata(gw_local):
    gw_local.ollama_reachable = lambda: True  # type: ignore[method-assign]
    gw_local.list_ollama_models = lambda: [{"name": "qwen2.5:3b"}]  # type: ignore[method-assign]

    def fake_post(url, payload, timeout):
        assert payload["model"] == "qwen2.5:3b"
        return {
            "message": {"content": "SPI controller drives the clock."},
            "eval_count": 10,
            "eval_duration": 2_000_000_000,
            "prompt_eval_count": 5,
        }

    gw_local._http_post = fake_post
    res = gw_local.complete_text("explain SPI")
    assert res.ok is True
    assert "SPI" in res.text
    assert res.attempts == 1
    assert res.metadata.get("tokens_per_s") == 5.0
    pub = res.to_public_dict()
    assert "api_key" not in str(pub)


def test_complete_json_validation_and_retry(gw_local):
    gw_local.ollama_reachable = lambda: True  # type: ignore[method-assign]
    gw_local.list_ollama_models = lambda: [{"name": "qwen2.5:3b"}]  # type: ignore[method-assign]
    calls = {"n": 0}

    def fake_post(url, payload, timeout):
        calls["n"] += 1
        assert payload.get("format") == "json" or isinstance(payload.get("format"), dict)
        if calls["n"] == 1:
            return {"message": {"content": "not-json"}, "eval_count": 1}
        return {
            "message": {
                "content": '{"summary":"ok","findings":["a"],"confidence":"high",'
                '"limitations":[],"recommendations":["b"]}'
            },
            "eval_count": 2,
            "eval_duration": 1_000_000_000,
        }

    gw_local._http_post = fake_post
    gw_local.retry_policy = RetryPolicy(max_retries=1, backoff_s=0.0)
    res = gw_local.complete_json("structured", json_schema=None)
    assert res.ok is True
    assert res.attempts == 2
    assert res.data["summary"] == "ok"


def test_complete_json_schema_format_passed(gw_local):
    gw_local.ollama_reachable = lambda: True  # type: ignore[method-assign]
    gw_local.list_ollama_models = lambda: [{"name": "qwen2.5:3b"}]  # type: ignore[method-assign]
    schema = {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}

    def fake_post(url, payload, timeout):
        assert payload["format"] == schema
        return {"message": {"content": '{"summary":"hi"}'}}

    gw_local._http_post = fake_post
    res = gw_local.complete_json("x", json_schema=schema)
    assert res.ok and res.data["summary"] == "hi"


def test_timeout_then_retry_exhaustion(gw_local):
    gw_local.ollama_reachable = lambda: True  # type: ignore[method-assign]
    gw_local.list_ollama_models = lambda: [{"name": "qwen2.5:3b"}]  # type: ignore[method-assign]
    calls = {"n": 0}

    def fake_post(url, payload, timeout):
        calls["n"] += 1
        raise TimeoutError("slow")

    gw_local._http_post = fake_post
    gw_local.retry_policy = RetryPolicy(max_retries=1, backoff_s=0.0)
    res = gw_local.complete_text("x")
    assert res.ok is False
    assert res.failure_kind == FailureKind.TIMEOUT
    assert res.attempts == 2  # initial + 1 retry


def test_auth_error_not_retried(gw_local):
    gw_local.ollama_reachable = lambda: True  # type: ignore[method-assign]
    gw_local.list_ollama_models = lambda: [{"name": "qwen2.5:3b"}]  # type: ignore[method-assign]
    calls = {"n": 0}

    def fake_post(url, payload, timeout):
        calls["n"] += 1
        raise RuntimeError("401 unauthorized")

    gw_local._http_post = fake_post
    gw_local.retry_policy = RetryPolicy(max_retries=3, backoff_s=0.0)
    res = gw_local.complete_text("x")
    assert res.ok is False
    assert res.failure_kind == FailureKind.AUTH
    assert calls["n"] == 1


def test_cancellation_before_invoke(gw_local):
    gw_local.ollama_reachable = lambda: True  # type: ignore[method-assign]
    gw_local.list_ollama_models = lambda: [{"name": "qwen2.5:3b"}]  # type: ignore[method-assign]
    token = CancellationToken()
    token.cancel()

    def fake_post(url, payload, timeout):
        raise AssertionError("should not be called")

    gw_local._http_post = fake_post
    res = gw_local.complete_text("x", cancel_token=token)
    assert res.ok is False
    assert res.failure_kind == FailureKind.CANCELLED


def test_cancellation_isolation_concurrent(gw_local):
    gw_local.ollama_reachable = lambda: True  # type: ignore[method-assign]
    gw_local.list_ollama_models = lambda: [{"name": "qwen2.5:3b"}]  # type: ignore[method-assign]
    lock = threading.Lock()
    seen = []

    def fake_post(url, payload, timeout):
        with lock:
            seen.append(payload["messages"][-1]["content"])
        time.sleep(0.05)
        return {"message": {"content": f"ok:{payload['messages'][-1]['content']}"}}

    gw_local._http_post = fake_post
    t1 = CancellationToken()
    t2 = CancellationToken()
    t1.cancel()

    r1 = gw_local.complete_text("A", cancel_token=t1)
    r2 = gw_local.complete_text("B", cancel_token=t2)
    assert r1.failure_kind == FailureKind.CANCELLED
    assert r2.ok is True and "B" in r2.text
    assert "A" not in seen


def test_provider_status_includes_models(monkeypatch):
    gw = ModelGateway()
    monkeypatch.setattr(gw, "ollama_reachable", lambda: True)
    monkeypatch.setattr(gw, "list_ollama_models", lambda: [{"name": "qwen2.5:3b"}])
    st = gw.provider_status()
    assert "qwen2.5:3b" in st["ollama_models"]
    assert "gateway_timeout_s" in st
