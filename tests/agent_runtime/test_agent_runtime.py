"""Phase 5b — Agent Runtime foundation tests (no hardware)."""

from __future__ import annotations

import time

import pytest
from pydantic import ValidationError

from agent_runtime.agent import SpecialistAgent
from agent_runtime.agents import BrokerProbeAgent, EchoAgent
from agent_runtime.broker_session import AgentBrokerSession
from agent_runtime.contracts import AgentManifest, AgentResult, AgentTask, ExecutionStatus
from agent_runtime.context import ExecutionContext
from agent_runtime.errors import BrokerAccessDenied, DuplicateAgentError, UnknownAgentError
from agent_runtime.registry import AgentRegistry
from agent_runtime.runtime import AgentRuntime
from agent_runtime.service import reset_agent_runtime
from device_broker.client import BrokerClient
from device_broker.policy import BrokerPolicy
from device_broker.broker import DeviceBroker
from master import capabilities
from master.broker_service import reset_broker
from master.contracts import IntentKind, InteractRequest
from master.engineering_service import reset_engineering_os
from master.model_gateway import deterministic_intent
from master.orchestrator import Orchestrator
from master.project_service import reset_project_os
from integrations.dot.gateway import DotGateway
from project_os import ProjectOS


@pytest.fixture
def work(tmp_path):
    root = tmp_path / "PyraWork"
    root.mkdir()
    (root / "global").mkdir()
    (root / "projects").mkdir()
    return root


@pytest.fixture
def pos(work):
    p = ProjectOS(work)
    yield p
    p.close()


@pytest.fixture
def broker(work, pos):
    policy = BrokerPolicy(work_root=work)
    b = DeviceBroker(policy, project_resolver=pos.active_project)
    yield b
    b.close()


@pytest.fixture
def client(broker):
    return BrokerClient(broker)


@pytest.fixture
def runtime(client):
    rt = AgentRuntime(registry=AgentRegistry(), broker_client=client)
    rt.register(EchoAgent())
    rt.register(BrokerProbeAgent())
    return rt


@pytest.fixture
def project(pos):
    return pos.create(name="Runtime Test", goal="phase5b")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_register_and_lookup(client):
    reg = AgentRegistry()
    rt = AgentRuntime(registry=reg, broker_client=client)
    m = rt.register(EchoAgent())
    assert m.agent_id == "echo"
    assert rt.registry.get("echo").manifest().name == "Echo Agent"
    assert "echo" in rt.list_capabilities() or "runtime_self_test" in rt.list_capabilities()


def test_duplicate_registration_rejected(client):
    rt = AgentRuntime(broker_client=client)
    rt.register(EchoAgent())
    with pytest.raises(DuplicateAgentError):
        rt.register(EchoAgent())


def test_unknown_agent_rejected(runtime, project):
    result = runtime.run(
        AgentTask(
            task_id="t1",
            project_id=project["id"],
            agent_id="no_such_agent",
            description="x",
        )
    )
    assert result.status == ExecutionStatus.FAILED
    assert "unknown" in result.errors[0].lower()


def test_capability_discovery(runtime):
    caps = runtime.list_capabilities()
    assert "echo" in caps or "runtime_self_test" in caps
    agents = runtime.list_agents()
    ids = {a.agent_id for a in agents}
    assert "echo" in ids
    assert "broker_probe" in ids


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------


def test_valid_task(project):
    task = AgentTask(
        task_id="t1",
        project_id=project["id"],
        agent_id="echo",
        description="hello",
    )
    assert task.resolve_target() == "echo"


def test_invalid_task_missing_project():
    with pytest.raises(ValidationError):
        AgentTask(task_id="t1", project_id="", agent_id="echo", description="x")


def test_valid_result(project):
    r = AgentResult(
        agent_id="echo",
        task_id="t1",
        project_id=project["id"],
        status=ExecutionStatus.COMPLETED,
        summary="ok",
    )
    assert r.status == ExecutionStatus.COMPLETED


def test_invalid_result_missing_fields():
    with pytest.raises(ValidationError):
        AgentResult(agent_id="echo", task_id="t1", project_id="p", status="NOT_A_STATUS")


def test_project_identity_mismatch_rejected(runtime, project, pos):
    other = pos.create(name="Other", goal="iso")
    result = runtime.run(
        {
            "task_id": "t1",
            "project_id": project["id"],
            "agent_id": "echo",
            "description": "leak?",
            "project_context": {"project_id": other["id"], "name": "Other"},
        }
    )
    assert result.status == ExecutionStatus.REJECTED
    assert "mismatch" in result.summary.lower() or "mismatch" in result.errors[0].lower()


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def test_successful_echo(runtime, project):
    result = runtime.run(
        AgentTask(
            task_id="t_ok",
            project_id=project["id"],
            agent_id="echo",
            description="ping",
            project_context={"project_id": project["id"], "name": project["name"]},
        )
    )
    assert result.status == ExecutionStatus.COMPLETED
    assert result.result["echo"] == "ping"
    assert "TASK_VALIDATED" in result.lifecycle
    assert "RESULT_VALIDATED" in result.lifecycle


def test_agent_forced_failure(runtime, project):
    result = runtime.run(
        AgentTask(
            task_id="t_fail",
            project_id=project["id"],
            agent_id="echo",
            description="fail",
            inputs={"force_fail": True},
            project_context={"project_id": project["id"]},
        )
    )
    assert result.status == ExecutionStatus.FAILED


def test_invalid_agent_result(runtime, project):
    result = runtime.run(
        AgentTask(
            task_id="t_bad",
            project_id=project["id"],
            agent_id="echo",
            description="bad",
            inputs={"force_invalid_result": True},
            project_context={"project_id": project["id"]},
        )
    )
    assert result.status == ExecutionStatus.FAILED
    assert "invalid" in result.summary.lower() or any(
        "validation" in e.lower() or "invalid" in e.lower() for e in result.errors
    )


def test_timeout(client, project):
    class SlowAgent(SpecialistAgent):
        def manifest(self) -> AgentManifest:
            return AgentManifest(
                agent_id="slow",
                name="Slow",
                description="sleeps",
                allowed_tools=[],
                max_level="L0",
                timeout_s=0.2,
            )

        def run(self, task, ctx):
            time.sleep(2.0)
            return AgentResult(
                agent_id="slow",
                task_id=task.task_id,
                project_id=ctx.project_id,
                status=ExecutionStatus.COMPLETED,
                summary="late",
            )

    rt = AgentRuntime(broker_client=client)
    rt.register(SlowAgent())
    result = rt.run(
        AgentTask(
            task_id="t_slow",
            project_id=project["id"],
            agent_id="slow",
            description="wait",
            timeout_s=0.3,
            project_context={"project_id": project["id"]},
        )
    )
    assert result.status == ExecutionStatus.FAILED
    assert any("timeout" in e.lower() for e in result.errors)


def test_blocked_without_broker(project):
    rt = AgentRuntime(broker_client=None)
    rt.register(EchoAgent())
    result = rt.run(
        AgentTask(
            task_id="t_nb",
            project_id=project["id"],
            agent_id="echo",
            description="x",
            project_context={"project_id": project["id"]},
        )
    )
    assert result.status == ExecutionStatus.BLOCKED


# ---------------------------------------------------------------------------
# BrokerClient / AgentBrokerSession
# ---------------------------------------------------------------------------


def test_broker_probe_success(runtime, project):
    result = runtime.run(
        AgentTask(
            task_id="t_bp",
            project_id=project["id"],
            agent_id="broker_probe",
            description="probe system",
            project_context={"project_id": project["id"]},
        )
    )
    assert result.status == ExecutionStatus.COMPLETED
    assert "system_info" in result.result
    # Evidence should include broker operation refs
    flat = str(result.evidence)
    assert "operation_id" in flat or "broker_calls" in flat


def test_broker_disallowed_tool(runtime, project):
    result = runtime.run(
        AgentTask(
            task_id="t_deny",
            project_id=project["id"],
            agent_id="broker_probe",
            description="try shell",
            inputs={"mode": "disallowed_tool"},
            project_context={"project_id": project["id"]},
        )
    )
    assert result.status == ExecutionStatus.BLOCKED


def test_broker_session_allowlist(client, project):
    session = AgentBrokerSession(
        client,
        agent_id="test",
        project_id=project["id"],
        allowed_tools=["get_system_info"],
        max_level="L0",
    )
    ok = session.call("get_system_info", {})
    assert ok.ok
    with pytest.raises(BrokerAccessDenied):
        session.call("write_text_file", {"path": "x", "content": "y"})


def test_broker_permission_denial(client, project):
    """Agent allowlists an L1 tool but max_level is L0 → Broker denies."""

    class WriterAgent(SpecialistAgent):
        def manifest(self) -> AgentManifest:
            return AgentManifest(
                agent_id="writer_l0",
                name="Writer L0",
                description="tries L1 write with L0 max",
                allowed_tools=["write_text_file"],
                max_level="L0",
                timeout_s=5.0,
            )

        def run(self, task, ctx):
            assert ctx.broker is not None
            res = ctx.broker.call(
                "write_text_file",
                {"path": "notes.txt", "content": "nope"},
            )
            status = (
                ExecutionStatus.BLOCKED
                if res.status == "denied"
                else ExecutionStatus.FAILED
            )
            return AgentResult(
                agent_id="writer_l0",
                task_id=task.task_id,
                project_id=ctx.project_id,
                status=status if not res.ok else ExecutionStatus.FAILED,
                summary="permission check",
                result=res.to_dict(),
                errors=[] if not res.ok else ["expected denial"],
            )

    rt = AgentRuntime(broker_client=client)
    rt.register(WriterAgent())
    result = rt.run(
        AgentTask(
            task_id="t_perm",
            project_id=project["id"],
            agent_id="writer_l0",
            description="write",
            project_context={"project_id": project["id"]},
            max_level="L0",
        )
    )
    assert result.status == ExecutionStatus.BLOCKED
    assert result.result.get("status") == "denied" or result.result.get("ok") is False


def test_unknown_tool_via_broker(client, project):
    # Put a fake tool on allowlist; Broker returns denied for unknown tool.
    session = AgentBrokerSession(
        client,
        agent_id="test",
        project_id=project["id"],
        allowed_tools=["definitely_not_a_real_tool"],
        max_level="L1",
    )
    res = session.call("definitely_not_a_real_tool", {})
    assert res.ok is False
    assert res.status == "denied"


# ---------------------------------------------------------------------------
# Context isolation
# ---------------------------------------------------------------------------


def test_context_isolation_keys(runtime, project):
    result = runtime.run(
        AgentTask(
            task_id="t_ctx",
            project_id=project["id"],
            agent_id="echo",
            description="ctx",
            project_context={
                "project_id": project["id"],
                "name": project["name"],
                "secret_should_not_be_needed": "x",
            },
        )
    )
    assert result.status == ExecutionStatus.COMPLETED
    keys = result.result["context_keys"]
    assert "project_id" in keys
    # Agent only sees what Master passed — still must match project_id
    assert result.project_id == project["id"]


def test_agent_cannot_change_project_identity(client, project, pos):
    other = pos.create(name="OtherProj", goal="iso")

    class HijackAgent(SpecialistAgent):
        def manifest(self) -> AgentManifest:
            return AgentManifest(
                agent_id="hijack",
                name="Hijack",
                description="tries to change project_id",
                allowed_tools=[],
                max_level="L0",
            )

        def run(self, task, ctx):
            ctx.project_id = other["id"]  # mutate field
            try:
                ctx.assert_project_identity()
            except RuntimeError as exc:
                return AgentResult(
                    agent_id="hijack",
                    task_id=task.task_id,
                    project_id=ctx.frozen_project_id,
                    status=ExecutionStatus.FAILED,
                    summary="identity guard worked",
                    errors=[str(exc)],
                )
            return AgentResult(
                agent_id="hijack",
                task_id=task.task_id,
                project_id=other["id"],
                status=ExecutionStatus.COMPLETED,
                summary="hijacked",
            )

    rt = AgentRuntime(broker_client=client)
    rt.register(HijackAgent())
    result = rt.run(
        AgentTask(
            task_id="t_hijack",
            project_id=project["id"],
            agent_id="hijack",
            description="hijack",
            project_context={"project_id": project["id"]},
        )
    )
    # Either agent reports guard failure, or runtime fails identity mismatch
    assert result.status == ExecutionStatus.FAILED
    assert result.project_id == project["id"]


# ---------------------------------------------------------------------------
# Master / Dot integration
# ---------------------------------------------------------------------------


@pytest.fixture
def master_env(work):
    capabilities.reset_registry()
    reset_project_os(work)
    reset_broker(work)
    reset_engineering_os()
    reset_agent_runtime()
    capabilities.bootstrap_builtin_capabilities()
    yield
    capabilities.reset_registry()


def test_deterministic_agent_intents():
    assert deterministic_intent("list agents").kind == IntentKind.AGENT_LIST
    assert deterministic_intent("run echo agent").kind == IntentKind.AGENT_RUN
    assert deterministic_intent("run broker probe agent").kind == IntentKind.AGENT_RUN


def test_master_lists_agents(master_env, monkeypatch):
    orch = Orchestrator()
    monkeypatch.setattr(orch.gateway, "ollama_reachable", lambda: False)
    # Need a project only for run; list should work without
    resp = orch.handle(InteractRequest(text="list agents", source="cli"))
    assert resp.capability == "agent_runtime"
    assert resp.status == "ok"
    assert "echo" in resp.speech.lower() or "echo" in str(resp.evidence).lower()


def test_master_runs_echo_agent(master_env, monkeypatch):
    from master.project_service import get_project_os

    pos = get_project_os()
    pos.create(name="Master Agent Proj", goal="5b")
    orch = Orchestrator()
    monkeypatch.setattr(orch.gateway, "ollama_reachable", lambda: False)
    resp = orch.handle(InteractRequest(text="run echo agent", source="cli"))
    assert resp.capability == "agent_runtime"
    ar = resp.evidence.get("agent_result") or {}
    assert ar.get("status") == "COMPLETED"
    assert resp.status == "ok"


def test_master_handles_failed_agent(master_env, monkeypatch):
    """Unknown agent via Master → structured failure."""
    from master.project_service import get_project_os

    get_project_os().create(name="Fail Proj", goal="5b")
    orch = Orchestrator()
    monkeypatch.setattr(orch.gateway, "ollama_reachable", lambda: False)
    resp = orch.handle(InteractRequest(text="run agent missing_agent_xyz", source="cli"))
    assert resp.capability == "agent_runtime"
    assert resp.status == "error"
    ar = resp.evidence.get("agent_result") or {}
    assert ar.get("status") == "FAILED"


def test_master_blocked_without_project(master_env, monkeypatch):
    orch = Orchestrator()
    monkeypatch.setattr(orch.gateway, "ollama_reachable", lambda: False)
    resp = orch.handle(InteractRequest(text="run echo agent", source="cli"))
    assert resp.capability == "agent_runtime"
    assert resp.status == "error"
    assert "project" in resp.speech.lower()


def test_dot_still_routes(master_env, monkeypatch):
    orch = Orchestrator()
    monkeypatch.setattr(orch.gateway, "ollama_reachable", lambda: False)
    dot = DotGateway(orch)
    resp = dot.route(InteractRequest(text="list agents", source="mark", metadata={"from_mark": True}))
    assert resp.capability == "agent_runtime"
    assert resp.evidence.get("via") == "dot" or resp.evidence.get("source") == "mark"


def test_broker_probe_via_master(master_env, monkeypatch):
    from master.project_service import get_project_os

    get_project_os().create(name="Probe Proj", goal="5b")
    orch = Orchestrator()
    monkeypatch.setattr(orch.gateway, "ollama_reachable", lambda: False)
    resp = orch.handle(InteractRequest(text="run broker probe agent", source="cli"))
    assert resp.capability == "agent_runtime"
    ar = resp.evidence.get("agent_result") or {}
    assert ar.get("status") == "COMPLETED"
