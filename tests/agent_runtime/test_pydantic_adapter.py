"""PydanticAI adapter integration tests (deterministic TestModel)."""

from __future__ import annotations

import pytest
from pydantic_ai.models.test import TestModel

from agent_runtime.agents.research import ResearchAgent
from agent_runtime.contracts import AgentTask, ExecutionStatus
from agent_runtime.research_models import ResearchReport
from agent_runtime.runtime import AgentRuntime
from agent_runtime.registry import AgentRegistry
from device_broker.broker import DeviceBroker
from device_broker.client import BrokerClient
from device_broker.policy import BrokerPolicy
from master.model_gateway import ModelGateway
from project_os import ProjectOS


@pytest.fixture
def work(tmp_path):
    root = tmp_path / "PyraWork"
    root.mkdir()
    (root / "global").mkdir()
    (root / "projects").mkdir()
    return root


@pytest.fixture
def env(work):
    pos = ProjectOS(work)
    broker = DeviceBroker(BrokerPolicy(work_root=work), project_resolver=pos.active_project)
    client = BrokerClient(broker)
    proj = pos.create(name="Adapter", goal="5c")
    gw = ModelGateway()
    report = {
        "summary": "Adapter path works.",
        "findings": ["structured output ok"],
        "assumptions": [],
        "unknowns": [],
        "recommendations": ["continue"],
        "confidence": "medium",
        "requires_human_review": False,
    }
    gw.set_override_model(TestModel(call_tools=[], custom_output_args=report))
    agent = ResearchAgent(gateway=gw)
    rt = AgentRuntime(registry=AgentRegistry(), broker_client=client)
    rt.register(agent)
    yield rt, proj, gw, client
    broker.close()
    pos.close()


def test_adapter_successful_execution(env):
    rt, proj, gw, _ = env
    result = rt.run(
        AgentTask(
            task_id="t1",
            project_id=proj["id"],
            agent_id="research",
            description="Explain I2C briefly.",
            project_context={"project_id": proj["id"]},
        )
    )
    assert result.status == ExecutionStatus.COMPLETED
    ResearchReport.model_validate(result.result)
    assert result.agent_id == "research"


def test_adapter_maps_to_agent_result_contract(env):
    rt, proj, _, _ = env
    result = rt.run(
        AgentTask(
            task_id="t2",
            project_id=proj["id"],
            agent_id="research",
            description="Topic",
            project_context={"project_id": proj["id"]},
        )
    )
    assert set(result.model_dump()) >= {
        "agent_id",
        "task_id",
        "project_id",
        "status",
        "summary",
        "result",
        "evidence",
        "warnings",
        "errors",
    }


def test_no_provider_details_in_result(env):
    rt, proj, _, _ = env
    result = rt.run(
        AgentTask(
            task_id="t3",
            project_id=proj["id"],
            agent_id="research",
            description="Topic",
            project_context={"project_id": proj["id"]},
        )
    )
    blob = str(result.model_dump()).lower()
    assert "api_key" not in blob
    assert "sk-" not in blob


def test_echo_still_independent_of_pydantic(env):
    """Importing research must not force echo to use PydanticAI."""
    from agent_runtime.agents.echo import EchoAgent

    rt, proj, _, client = env
    rt2 = AgentRuntime(registry=AgentRegistry(), broker_client=client)
    rt2.register(EchoAgent())
    result = rt2.run(
        AgentTask(
            task_id="te",
            project_id=proj["id"],
            agent_id="echo",
            description="ping",
            project_context={"project_id": proj["id"]},
        )
    )
    assert result.status == ExecutionStatus.COMPLETED
    assert result.result["echo"] == "ping"
