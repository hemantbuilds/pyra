"""Phase 5d — tool-calling through AgentBrokerSession (TestModel)."""

from __future__ import annotations

import pytest
from pydantic_ai.models.test import TestModel

from agent_runtime.agents.research import ResearchAgent
from agent_runtime.contracts import AgentTask, ExecutionStatus
from agent_runtime.registry import AgentRegistry
from agent_runtime.runtime import AgentRuntime
from device_broker.broker import DeviceBroker
from device_broker.client import BrokerClient
from device_broker.policy import BrokerPolicy
from master.model_gateway import ModelGateway
from project_os import ProjectOS


@pytest.fixture
def env(tmp_path):
    work = tmp_path / "PyraWork"
    work.mkdir()
    (work / "global").mkdir()
    (work / "projects").mkdir()
    pos = ProjectOS(work)
    broker = DeviceBroker(BrokerPolicy(work_root=work), project_resolver=pos.active_project)
    client = BrokerClient(broker)
    proj = pos.create(name="Tools", goal="5d")
    yield pos, client, broker, proj
    broker.close()
    pos.close()


def test_valid_tool_request_via_broker(env):
    pos, client, broker, proj = env
    gw = ModelGateway()
    # Call get_system_info then return structured report
    report = {
        "summary": "Host inspected via Broker tool.",
        "findings": ["system info retrieved"],
        "assumptions": [],
        "unknowns": [],
        "recommendations": ["continue"],
        "confidence": "medium",
        "requires_human_review": False,
    }
    gw.set_override_model(TestModel(call_tools=["get_system_info"], custom_output_args=report))
    rt = AgentRuntime(registry=AgentRegistry(), broker_client=client)
    rt.register(ResearchAgent(gateway=gw))
    result = rt.run(
        AgentTask(
            task_id="tt1",
            project_id=proj["id"],
            agent_id="research",
            description="Use system info if needed, then summarise host.",
            project_context={"project_id": proj["id"]},
        )
    )
    assert result.status == ExecutionStatus.COMPLETED
    # Broker evidence should show the tool call
    blob = str(result.evidence)
    assert "get_system_info" in blob or "broker_calls" in blob


def test_unknown_tool_denied_by_allowlist(env):
    from agent_runtime.broker_session import AgentBrokerSession
    from agent_runtime.errors import BrokerAccessDenied

    _, client, _, proj = env
    session = AgentBrokerSession(
        client,
        agent_id="research",
        project_id=proj["id"],
        allowed_tools=["get_system_info"],
        max_level="L0",
    )
    with pytest.raises(BrokerAccessDenied):
        session.call("flash_firmware", {})


def test_permission_denied_l1_with_l0_max(env):
    from agent_runtime.broker_session import AgentBrokerSession

    _, client, _, proj = env
    session = AgentBrokerSession(
        client,
        agent_id="research",
        project_id=proj["id"],
        allowed_tools=["write_text_file"],
        max_level="L0",
    )
    res = session.call("write_text_file", {"path": "x.txt", "content": "no"})
    assert res.ok is False
    assert res.status == "denied"


def test_invalid_tool_arguments_fail_cleanly(env):
    from agent_runtime.broker_session import AgentBrokerSession

    _, client, _, proj = env
    session = AgentBrokerSession(
        client,
        agent_id="research",
        project_id=proj["id"],
        allowed_tools=["read_text_file"],
        max_level="L0",
    )
    res = session.call("read_text_file", {"path": ""})
    assert res.ok is False


def test_project_isolation_no_cross_assign(env):
    pos, client, broker, proj = env
    other = pos.create(name="OtherIso", goal="iso")
    gw = ModelGateway()
    report = {
        "summary": f"project {proj['id']}",
        "findings": [],
        "assumptions": [],
        "unknowns": [],
        "recommendations": [],
        "confidence": "low",
        "requires_human_review": True,
    }
    gw.set_override_model(TestModel(call_tools=[], custom_output_args=report))
    rt = AgentRuntime(registry=AgentRegistry(), broker_client=client)
    rt.register(ResearchAgent(gateway=gw))
    r1 = rt.run(
        AgentTask(
            task_id="iso1",
            project_id=proj["id"],
            agent_id="research",
            description="Summarise project context only.",
            project_context={"project_id": proj["id"], "name": proj["name"]},
        )
    )
    r2 = rt.run(
        AgentTask(
            task_id="iso2",
            project_id=other["id"],
            agent_id="research",
            description="Summarise project context only.",
            project_context={"project_id": other["id"], "name": other["name"]},
        )
    )
    assert r1.status == ExecutionStatus.COMPLETED
    assert r2.status == ExecutionStatus.COMPLETED
    assert r1.project_id == proj["id"]
    assert r2.project_id == other["id"]
    assert r1.task_id != r2.task_id


def test_model_cannot_bypass_broker_for_disallowed_tool(env):
    """Even if the model requests a disallowed tool, Broker session denies it."""
    from agent_runtime.broker_session import AgentBrokerSession
    from agent_runtime.errors import BrokerAccessDenied

    _, client, _, proj = env
    session = AgentBrokerSession(
        client,
        agent_id="research",
        project_id=proj["id"],
        allowed_tools=["get_system_info"],
        max_level="L0",
    )
    with pytest.raises(BrokerAccessDenied):
        session.call("run_allowlisted_command", {"command": "true"})
