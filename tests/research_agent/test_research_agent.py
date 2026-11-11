"""Research Agent functional + security + scenario tests (deterministic TestModel)."""

from __future__ import annotations

import concurrent.futures
import threading

import pytest
from pydantic_ai.models.test import TestModel

from agent_runtime.agents.research import ResearchAgent
from agent_runtime.contracts import AgentTask, ExecutionStatus
from agent_runtime.research_models import ResearchReport
from agent_runtime.service import get_agent_runtime, get_specialist_gateway
from master.contracts import IntentKind, InteractRequest
from master.model_gateway import ModelGateway, ProviderError, deterministic_intent
from master.orchestrator import Orchestrator
from master.project_service import get_project_os
from master.provider_config import ProviderSettings, ProviderSpec
from integrations.dot.gateway import DotGateway

from helpers import make_test_model, sample_report


def _run_research(description: str, project_id: str, *, report=None, inputs=None):
    gw = get_specialist_gateway()
    gw.set_override_model(make_test_model(report))
    rt = get_agent_runtime()
    return rt.run(
        AgentTask(
            task_id="t_research",
            project_id=project_id,
            agent_id="research",
            description=description,
            inputs=inputs or {},
            project_context={"project_id": project_id, "name": "ProjA"},
        )
    )


def test_research_registered(runtime_env):
    ids = {m.agent_id for m in get_agent_runtime().list_agents()}
    assert "research" in ids
    assert "echo" in ids
    assert "broker_probe" in ids


def test_scenario_a_general_explanation(runtime_env):
    pos = get_project_os()
    proj = pos.create(name="ProjA", goal="uart")
    result = _run_research(
        "Explain the difference between polling and interrupt-driven UART communication.",
        proj["id"],
        report=sample_report(summary="Polling vs interrupt UART explained."),
    )
    assert result.status == ExecutionStatus.COMPLETED
    report = ResearchReport.model_validate(result.result)
    assert report.summary
    assert report.findings


def test_scenario_b_project_context(runtime_env):
    pos = get_project_os()
    proj = pos.create(name="WatchdogProj", goal="mcu watchdog", description="ARM Cortex-M firmware")
    result = get_agent_runtime().run(
        AgentTask(
            task_id="t_wd",
            project_id=proj["id"],
            agent_id="research",
            description="Based on this project's architecture, explain how an MCU watchdog should be integrated.",
            project_context={
                "project_id": proj["id"],
                "name": proj["name"],
                "description": "ARM Cortex-M firmware with RTOS",
            },
        )
    )
    assert result.status == ExecutionStatus.COMPLETED
    assert result.project_id == proj["id"]
    assert "project_id" in str(result.result) or result.summary


def test_scenario_c_engineering_compare(runtime_env):
    pos = get_project_os()
    proj = pos.create(name="FW", goal="firmware")
    result = _run_research(
        "Compare PlatformIO and Zephyr for an embedded firmware project.",
        proj["id"],
        report=sample_report(
            summary="PlatformIO vs Zephyr comparison.",
            findings=["PlatformIO is Arduino-friendly", "Zephyr is RTOS-centric"],
            recommendations=["Choose Zephyr for multi-vendor SoC support"],
        ),
    )
    assert result.status == ExecutionStatus.COMPLETED
    assert len(result.result["findings"]) >= 1


def test_scenario_d_insufficient_mcu_info(runtime_env):
    pos = get_project_os()
    proj = pos.create(name="HW", goal="unknown board")
    result = _run_research(
        "Which exact MCU is connected to my Raspberry Pi?",
        proj["id"],
        report=sample_report(
            summary="Cannot identify MCU without discovery evidence.",
            findings=[],
            assumptions=[],
            unknowns=["No USB/serial/probe discovery evidence supplied"],
            recommendations=["Run Engineering OS hardware discovery"],
            confidence="low",
            requires_human_review=True,
        ),
    )
    assert result.status == ExecutionStatus.COMPLETED
    assert result.result["confidence"] == "low"
    assert result.result["requires_human_review"] is True
    assert result.recommended_next_action == "run_hardware_discovery"
    # Must not invent a board identity in summary
    assert "arduino uno" not in result.summary.lower()


def test_scenario_e_context_isolation(runtime_env):
    pos = get_project_os()
    a = pos.create(name="ProjectA", goal="alpha")
    b = pos.create(name="ProjectB", goal="secret-beta")
    result = get_agent_runtime().run(
        AgentTask(
            task_id="t_iso",
            project_id=a["id"],
            agent_id="research",
            description="Summarise this project only.",
            project_context={"project_id": a["id"], "name": "ProjectA", "goal": "alpha"},
        )
    )
    assert result.project_id == a["id"]
    blob = str(result.model_dump()).lower()
    assert b["id"].lower() not in blob
    assert "secret-beta" not in blob


def test_empty_request(runtime_env):
    pos = get_project_os()
    proj = pos.create(name="E", goal="e")
    # AgentTask requires min_length=1 on description — Runtime REJECTED at contract
    result = get_agent_runtime().run(
        {
            "task_id": "t_empty",
            "project_id": proj["id"],
            "agent_id": "research",
            "description": " ",
        }
    )
    assert result.status in (ExecutionStatus.REJECTED, ExecutionStatus.FAILED)


def test_provider_unavailable_does_not_crash(runtime_env):
    gw = get_specialist_gateway()
    gw.clear_override_model()
    # Force ollama path while unreachable by monkeypatching
    gw.ollama_reachable = lambda: False  # type: ignore[method-assign]
    pos = get_project_os()
    proj = pos.create(name="P", goal="g")
    result = get_agent_runtime().run(
        AgentTask(
            task_id="t_down",
            project_id=proj["id"],
            agent_id="research",
            description="Explain DMA briefly.",
            project_context={"project_id": proj["id"]},
        )
    )
    assert result.status == ExecutionStatus.BLOCKED
    assert any("provider" in e.lower() or "ollama" in e.lower() for e in result.errors)


def test_disallowed_tool_via_session(runtime_env):
    """Research allowlist excludes shell; session must deny."""
    from agent_runtime.broker_session import AgentBrokerSession
    from master.broker_service import get_broker_client

    pos = get_project_os()
    proj = pos.create(name="S", goal="s")
    session = AgentBrokerSession(
        get_broker_client(),
        agent_id="research",
        project_id=proj["id"],
        allowed_tools=["get_system_info"],
        max_level="L0",
    )
    with pytest.raises(Exception):
        session.call("run_allowed_command", {"argv": ["uname", "-a"]})


def test_cannot_raise_max_level(runtime_env):
    from agent_runtime.broker_session import AgentBrokerSession
    from master.broker_service import get_broker_client

    pos = get_project_os()
    proj = pos.create(name="L", goal="l")
    session = AgentBrokerSession(
        get_broker_client(),
        agent_id="research",
        project_id=proj["id"],
        allowed_tools=["write_text_file"],
        max_level="L0",
    )
    res = session.call("write_text_file", {"path": "x.txt", "content": "no"})
    assert res.ok is False
    assert res.status == "denied"


def test_master_run_research(runtime_env, monkeypatch):
    get_project_os().create(name="MasterResearch", goal="r")
    orch = Orchestrator()
    monkeypatch.setattr(orch.gateway, "ollama_reachable", lambda: False)
    resp = orch.handle(InteractRequest(text="run research agent", source="cli"))
    assert resp.capability == "agent_runtime"
    assert resp.status == "ok"
    ar = resp.evidence["agent_result"]
    assert ar["agent_id"] == "research"
    assert ar["status"] == "COMPLETED"
    assert "summary" in ar["result"]


def test_dot_research_path(runtime_env, monkeypatch):
    get_project_os().create(name="DotResearch", goal="r")
    orch = Orchestrator()
    monkeypatch.setattr(orch.gateway, "ollama_reachable", lambda: False)
    # Ensure specialist gateway override still active for research agent
    resp = DotGateway(orch).route(
        InteractRequest(text="ask research agent to analyse this project", source="mark")
    )
    assert resp.capability == "agent_runtime"
    assert resp.evidence.get("agent_result", {}).get("agent_id") == "research"


def test_deterministic_research_intent():
    assert deterministic_intent("run research agent").kind == IntentKind.AGENT_RUN
    assert "research" in deterministic_intent("research this technical topic").agent_hints


def test_concurrent_research_isolation(runtime_env):
    pos = get_project_os()
    a = pos.create(name="ConcA", goal="a")
    b = pos.create(name="ConcB", goal="b")
    rt = get_agent_runtime()

    def _one(pid, label):
        get_specialist_gateway().set_override_model(
            make_test_model(sample_report(summary=f"Report for {label}"))
        )
        return rt.run(
            AgentTask(
                task_id=f"t_{label}",
                project_id=pid,
                agent_id="research",
                description=f"Research {label}",
                project_context={"project_id": pid, "name": label},
            )
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        fa = pool.submit(_one, a["id"], "A")
        fb = pool.submit(_one, b["id"], "B")
        ra, rb = fa.result(), fb.result()
    assert ra.project_id == a["id"]
    assert rb.project_id == b["id"]
    assert ra.task_id != rb.task_id


def test_secret_not_in_result(runtime_env, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret-SHOULD-NOT-LEAK")
    pos = get_project_os()
    proj = pos.create(name="Sec", goal="s")
    result = _run_research("Explain SPI briefly.", proj["id"])
    blob = str(result.model_dump())
    assert "sk-test-secret" not in blob
    assert "OPENAI_API_KEY" not in blob or "sk-test" not in blob
