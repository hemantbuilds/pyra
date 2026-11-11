"""Phase 5d — cancellation propagation through Runtime → specialist."""

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
from master.invocation import CancellationToken
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
    proj = pos.create(name="Cancel", goal="5d")
    gw = ModelGateway()
    report = {
        "summary": "cancelled path",
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
    yield rt, proj
    broker.close()
    pos.close()


def test_cancelled_before_model_returns_cancelled(env):
    rt, proj = env
    token = CancellationToken()
    token.cancel()
    result = rt.run(
        AgentTask(
            task_id="tc1",
            project_id=proj["id"],
            agent_id="research",
            description="Explain SPI",
            project_context={"project_id": proj["id"]},
            inputs={"cancel_token": token},
        )
    )
    assert result.status == ExecutionStatus.CANCELLED


def test_uncancelled_sibling_still_runs(env):
    rt, proj = env
    bad = CancellationToken()
    bad.cancel()
    good = CancellationToken()
    r1 = rt.run(
        AgentTask(
            task_id="tc_bad",
            project_id=proj["id"],
            agent_id="research",
            description="Explain SPI",
            project_context={"project_id": proj["id"]},
            inputs={"cancel_token": bad},
        )
    )
    r2 = rt.run(
        AgentTask(
            task_id="tc_good",
            project_id=proj["id"],
            agent_id="research",
            description="Explain SPI",
            project_context={"project_id": proj["id"]},
            inputs={"cancel_token": good},
        )
    )
    assert r1.status == ExecutionStatus.CANCELLED
    assert r2.status == ExecutionStatus.COMPLETED
    assert r2.task_id == "tc_good"
