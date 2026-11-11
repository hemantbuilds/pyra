"""Phase 5d.1 — ModelGateway hardening qualification tests."""

from __future__ import annotations

import json
import threading
import time
from typing import Literal

import httpx
import pytest
from pydantic import BaseModel, Field, ValidationError

from master.config import Settings
from master.invocation import (
    CancellationToken,
    FailureKind,
    RetryPolicy,
    classify_http_error,
    redact_error_text,
)
from master.model_gateway import ModelGateway
from master.model_profiles import ModelCapabilityProfile, get_profile, profiles_public
from master.provider_config import ProviderSettings, ProviderSpec


class StrictQualOut(BaseModel):
    """No defaults — missing fields must fail validation."""

    summary: str = Field(..., min_length=1)
    confidence: Literal["low", "medium", "high"]
    score: int


@pytest.fixture
def gw():
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
        },
    )
    g = ModelGateway(settings=settings, provider_settings=providers)
    g.ollama_reachable = lambda: True  # type: ignore[method-assign]
    g.list_ollama_models = lambda: [{"name": "qwen2.5:3b"}]  # type: ignore[method-assign]
    return g


def test_redact_error_text_strips_secrets():
    assert "[redacted]" in redact_error_text("HTTPError: Bearer sk-abc123 failed")
    assert "normal" in redact_error_text("ValueError: normal failure")


def test_classify_status_codes():
    class FakeResp:
        def __init__(self, code):
            self.status_code = code

    class FakeHTTP(Exception):
        def __init__(self, code):
            self.response = FakeResp(code)
            super().__init__(f"status {code}")

    assert classify_http_error(FakeHTTP(429)) == FailureKind.RATE_LIMIT
    assert classify_http_error(FakeHTTP(503)) == FailureKind.SERVER_ERROR
    assert classify_http_error(FakeHTTP(401)) == FailureKind.AUTH
    assert classify_http_error(FakeHTTP(404)) == FailureKind.MODEL_UNAVAILABLE


def test_server_error_retried_then_exhausted(gw):
    calls = {"n": 0}

    def fake_post(url, payload, timeout):
        calls["n"] += 1
        exc = httpx.HTTPStatusError(
            "server",
            request=httpx.Request("POST", url),
            response=httpx.Response(503, request=httpx.Request("POST", url)),
        )
        raise exc

    gw._http_post = fake_post
    gw.retry_policy = RetryPolicy(max_retries=1, backoff_s=0.0)
    res = gw.complete_text("x")
    assert res.ok is False
    assert res.failure_kind == FailureKind.SERVER_ERROR
    assert calls["n"] == 2


def test_rate_limit_classified(gw):
    def fake_post(url, payload, timeout):
        raise httpx.HTTPStatusError(
            "rl",
            request=httpx.Request("POST", url),
            response=httpx.Response(429, request=httpx.Request("POST", url)),
        )

    gw._http_post = fake_post
    gw.retry_policy = RetryPolicy(max_retries=0, backoff_s=0.0)
    res = gw.complete_text("x")
    assert res.failure_kind == FailureKind.RATE_LIMIT


def test_overall_timeout_budget_not_reset_by_retries(gw):
    """Retries must not extend wall clock beyond total_budget."""
    def fake_post(url, payload, timeout):
        time.sleep(0.15)
        raise TimeoutError("slow")

    gw._http_post = fake_post
    gw.retry_policy = RetryPolicy(max_retries=5, backoff_s=0.0)
    t0 = time.monotonic()
    res = gw.complete_text("x", timeout_s=0.35)
    elapsed = time.monotonic() - t0
    assert res.ok is False
    assert res.failure_kind in (FailureKind.TIMEOUT, FailureKind.TIMEOUT)
    assert elapsed < 0.9  # well under 5 * 0.15 with unbounded retries
    assert res.metadata.get("total_budget_s") == 0.35
    assert res.attempts <= 4


def test_empty_structured_output_rejected(gw):
    gw._http_post = lambda u, p, t: {"message": {"content": "   "}}
    gw.retry_policy = RetryPolicy(max_retries=0, backoff_s=0.0)
    res = gw.complete_json("x")
    assert res.ok is False
    assert res.failure_kind == FailureKind.VALIDATION
    assert "empty" in (res.error or "").lower()


def test_invalid_json_rejected(gw):
    gw._http_post = lambda u, p, t: {"message": {"content": "{not json"}}
    gw.retry_policy = RetryPolicy(max_retries=0, backoff_s=0.0)
    res = gw.complete_json("x")
    assert res.ok is False
    assert res.failure_kind == FailureKind.VALIDATION


def test_json_array_root_rejected(gw):
    gw._http_post = lambda u, p, t: {"message": {"content": "[1,2]"}}
    gw.retry_policy = RetryPolicy(max_retries=0, backoff_s=0.0)
    res = gw.complete_json("x")
    assert res.ok is False
    assert res.failure_kind == FailureKind.VALIDATION


def test_pydantic_missing_required_rejected(gw):
    gw._http_post = lambda u, p, t: {
        "message": {"content": json.dumps({"summary": "only"})}
    }
    gw.retry_policy = RetryPolicy(max_retries=0, backoff_s=0.0)
    res = gw.complete_json("x", pydantic_model=StrictQualOut)
    assert res.ok is False
    assert res.failure_kind == FailureKind.VALIDATION
    assert res.data is None


def test_pydantic_wrong_type_rejected(gw):
    gw._http_post = lambda u, p, t: {
        "message": {
            "content": json.dumps(
                {"summary": "ok", "confidence": "high", "score": "nope"}
            )
        }
    }
    gw.retry_policy = RetryPolicy(max_retries=0, backoff_s=0.0)
    res = gw.complete_json("x", pydantic_model=StrictQualOut)
    assert res.ok is False
    assert res.failure_kind == FailureKind.VALIDATION


def test_pydantic_bad_enum_rejected(gw):
    gw._http_post = lambda u, p, t: {
        "message": {
            "content": json.dumps(
                {"summary": "ok", "confidence": "extreme", "score": 1}
            )
        }
    }
    gw.retry_policy = RetryPolicy(max_retries=0, backoff_s=0.0)
    res = gw.complete_json("x", pydantic_model=StrictQualOut)
    assert res.ok is False


def test_pydantic_valid_accepted_no_fabrication(gw):
    payload = {"summary": "ok", "confidence": "low", "score": 3}
    gw._http_post = lambda u, p, t: {"message": {"content": json.dumps(payload)}}
    res = gw.complete_json("x", pydantic_model=StrictQualOut)
    assert res.ok is True
    assert res.data == payload


def test_extra_fields_stripped_or_kept_by_pydantic(gw):
    """Extra fields must not bypass schema — model_validate ignores extras by default."""
    gw._http_post = lambda u, p, t: {
        "message": {
            "content": json.dumps(
                {
                    "summary": "ok",
                    "confidence": "medium",
                    "score": 1,
                    "secret_auth": "sk-should-not-pass",
                }
            )
        }
    }
    res = gw.complete_json("x", pydantic_model=StrictQualOut)
    assert res.ok is True
    assert "secret_auth" not in res.data


def test_concurrent_independent_timeouts(gw):
    results = {}

    def slow(url, payload, timeout):
        time.sleep(0.08)
        return {"message": {"content": f"done:{payload['messages'][-1]['content']}"}}

    gw._http_post = slow

    def run(key, prompt, budget):
        results[key] = gw.complete_text(prompt, timeout_s=budget)

    t_a = threading.Thread(target=run, args=("a", "A", 2.0))
    t_b = threading.Thread(target=run, args=("b", "B", 2.0))
    t_a.start()
    t_b.start()
    t_a.join()
    t_b.join()
    assert results["a"].ok and "A" in results["a"].text
    assert results["b"].ok and "B" in results["b"].text
    assert results["a"].text != results["b"].text


def test_cancel_midflight_closes_http_client(monkeypatch):
    """Local slow server: cancel must abort client-side HTTP."""
    import http.server
    import socketserver

    started = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            started.set()
            time.sleep(8.0)
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"message":{"content":"late"}}')
            except BrokenPipeError:
                return

        def log_message(self, *args):
            return

    httpd = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    thr = threading.Thread(target=httpd.serve_forever, daemon=True)
    thr.start()
    try:
        settings = Settings(
            ollama_host=f"http://127.0.0.1:{port}",
            ollama_model="qwen2.5:3b",
            gateway_timeout_s=3.0,
            gateway_max_retries=0,
            gateway_retry_backoff_s=0.0,
        )
        g = ModelGateway(settings=settings)
        g.ollama_reachable = lambda: True  # type: ignore[method-assign]
        g.list_ollama_models = lambda: [{"name": "qwen2.5:3b"}]  # type: ignore[method-assign]
        # Force real cancellable path (no _http_post inject)
        token = CancellationToken()

        def cancel_soon():
            started.wait(timeout=2.0)
            time.sleep(0.05)
            token.cancel()

        threading.Thread(target=cancel_soon, daemon=True).start()
        t0 = time.monotonic()
        res = g.complete_text("cancel-me", cancel_token=token, timeout_s=3.0)
        elapsed = time.monotonic() - t0
        assert res.ok is False
        assert res.failure_kind == FailureKind.CANCELLED
        assert elapsed < 2.0  # must not wait full server sleep / full timeout
        assert (res.metadata or {}).get("provider_side_note")
        assert (res.metadata or {}).get("clients_closed", 0) >= 1
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_max_request_duration_exposed(gw):
    assert gw.max_request_duration_s() == 2.0
    assert gw.max_request_duration_s(10.0) == 10.0
    st = gw.provider_status()
    assert st["max_request_duration_s"] == 2.0
    assert "model_capability_profiles" in st


def test_profiles_seeded():
    assert get_profile("ollama", "qwen2.5:3b") is not None
    assert get_profile("ollama", "gemma3:1b") is not None
    pubs = profiles_public()
    assert any(p["model_id"] == "qwen2.5:3b" for p in pubs)
    # No secrets
    assert "sk-" not in json.dumps(pubs)


def test_invocation_result_redacts_metadata_keys(gw):
    gw._http_post = lambda u, p, t: {
        "message": {"content": "hi"},
        "eval_count": 1,
        "eval_duration": 1_000_000_000,
    }
    res = gw.complete_text("x")
    res.metadata["api_key"] = "sk-leak"
    pub = res.to_public_dict()
    assert "api_key" not in pub["metadata"]
