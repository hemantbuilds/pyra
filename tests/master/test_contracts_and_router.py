"""Phase 1 unit tests — no hardware required."""

from __future__ import annotations

import pytest

from agent_runtime.service import reset_agent_runtime
from master import capabilities
from master.broker_service import reset_broker
from master.contracts import IntentKind, InteractRequest
from master.engineering_service import reset_engineering_os
from master.model_gateway import deterministic_intent
from master.orchestrator import Orchestrator
from master.project_service import reset_project_os
from integrations.dot.gateway import DotGateway


@pytest.fixture(autouse=True)
def _isolate_work(tmp_path):
    capabilities.reset_registry()
    work = tmp_path / "PyraWork"
    reset_project_os(work)
    reset_broker(work)
    reset_engineering_os()
    reset_agent_runtime()
    capabilities.bootstrap_builtin_capabilities()
    yield
    capabilities.reset_registry()


@pytest.mark.parametrize(
    "text,kind",
    [
        ("hello", IntentKind.GREETING),
        ("list my projects", IntentKind.PROJECT_LIST),
        ("create a new project for the flight computer", IntentKind.PROJECT_CREATE),
        ("switch to the drone project", IntentKind.PROJECT_SWITCH),
        ("continue the firmware work", IntentKind.PROJECT_CONTINUE),
        ("Dot, ask PYRA to bring up the connected development board", IntentKind.HARDWARE_BRINGUP),
        ("discover the connected hardware", IntentKind.HARDWARE_BRINGUP),
        ("what can you do", IntentKind.CAPABILITY_QUERY),
        ("status", IntentKind.STATUS),
        ("list agents", IntentKind.AGENT_LIST),
        ("run echo agent", IntentKind.AGENT_RUN),
        ("run research agent", IntentKind.AGENT_RUN),
        ("research this technical topic", IntentKind.AGENT_RUN),
    ],
)
def test_deterministic_intent(text, kind):
    intent = deterministic_intent(text)
    assert intent.kind == kind


def test_orchestrator_status_without_ollama(monkeypatch):
    orch = Orchestrator()
    monkeypatch.setattr(orch.gateway, "ollama_reachable", lambda: False)
    resp = orch.handle(InteractRequest(text="status", source="cli"))
    assert resp.status in ("ok", "degraded")
    assert resp.capability == "system_status"
    assert "PYRA" in resp.speech
    assert resp.evidence.get("intent_backend") == "deterministic"


def test_dot_routes_mark_request(monkeypatch):
    orch = Orchestrator()
    monkeypatch.setattr(orch.gateway, "ollama_reachable", lambda: False)
    dot = DotGateway(orch)
    resp = dot.route(
        InteractRequest(
            text="bring up the connected development board",
            source="mark",
            metadata={"from_mark": True},
        )
    )
    assert resp.intent.kind == IntentKind.HARDWARE_BRINGUP
    assert resp.capability == "engineering_os"
    assert resp.evidence.get("via") == "dot"
    assert resp.evidence.get("hardcoded_arduino") is False
    assert resp.evidence.get("flash_attempted") is False


def test_bringup_does_not_claim_board_identity(monkeypatch):
    orch = Orchestrator()
    monkeypatch.setattr(orch.gateway, "ollama_reachable", lambda: False)
    resp = orch.handle(InteractRequest(text="identify and bring up the board", source="dot"))
    assert resp.intent.kind == IntentKind.HARDWARE_BRINGUP
    assert resp.capability == "engineering_os"
    assert resp.status == "ok"
    assert resp.evidence.get("flash_attempted") is False
    speech_l = resp.speech.lower()
    assert (
        "flash" in speech_l
        or "discovery" in speech_l
        or "phase 7" in speech_l
        or "not been verified" in speech_l
        or "blocked" in speech_l
        or "identified" in speech_l
    )


def test_project_list_via_project_os(monkeypatch):
    orch = Orchestrator()
    monkeypatch.setattr(orch.gateway, "ollama_reachable", lambda: False)
    resp = orch.handle(InteractRequest(text="list my projects", source="cli"))
    assert resp.capability == "project_os"
    assert resp.status == "ok"
    assert "projects" in resp.evidence



def test_fastapi_dot_endpoint(monkeypatch):
    from fastapi.testclient import TestClient
    from master import api as api_mod

    monkeypatch.setattr(api_mod.gateway, "ollama_reachable", lambda: False)
    client = TestClient(api_mod.app)
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["service"] == "pyra-master"

    r = client.post(
        "/dot/v1/interact",
        json={"text": "what can you do", "source": "mark", "metadata": {"from_mark": True}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["capability"] == "capability_query"
    assert body["speech"]
