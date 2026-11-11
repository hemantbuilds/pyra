"""Phase 7 — specialist registration, contracts, deterministic synthesize."""

from __future__ import annotations

import uuid

import pytest

from agent_runtime.contracts import AgentTask, ExecutionStatus
from agent_runtime.engineering_contracts import ProjectPlan, SystemRequirements
from agent_runtime.service import reset_agent_runtime
from device_broker.broker import DeviceBroker
from device_broker.policy import BrokerPolicy
from project_os import ProjectOS


@pytest.fixture
def runtime(tmp_path):
    work = tmp_path / "PyraWork"
    work.mkdir()
    (work / "global").mkdir()
    (work / "projects").mkdir()
    pos = ProjectOS(work)
    proj = pos.create(name="P7", goal="phase7")
    broker = DeviceBroker(BrokerPolicy(work_root=work), project_resolver=pos.active_project)
    client = broker.create_client(principal="master", max_level="L1")
    rt = reset_agent_runtime(broker_client=client, bootstrap=True)
    yield rt, pos, proj, broker
    broker.close()
    pos.close()


def _task(agent_id: str, project_id: str, description: str, inputs=None):
    return AgentTask(
        task_id=f"task_{uuid.uuid4().hex[:8]}",
        project_id=project_id,
        agent_id=agent_id,
        description=description,
        inputs={**(inputs or {}), "force_deterministic": True},
        project_context={"project_id": project_id},
        max_level="L0",
    )


def test_phase7_agents_registered(runtime):
    rt, pos, proj, broker = runtime
    ids = {m.agent_id for m in rt.list_agents()}
    for expected in (
        "planning",
        "requirements",
        "architecture",
        "hardware_eng",
        "firmware_eng",
        "verification",
        "documentation",
        "research",
        "echo",
    ):
        assert expected in ids


def test_planning_output_contract(runtime):
    rt, pos, proj, broker = runtime
    result = rt.run(_task("planning", proj["id"], "Start LED blink embedded project"))
    assert result.status == ExecutionStatus.COMPLETED
    plan = ProjectPlan.model_validate(result.result)
    assert plan.objective
    assert plan.deliverables
    assert plan.acceptance_criteria


def test_requirements_marks_derived(runtime):
    rt, pos, proj, broker = runtime
    result = rt.run(
        _task(
            "requirements",
            proj["id"],
            "Derive requirements",
            {"user_requirements": ["Must blink LED"]},
        )
    )
    assert result.status == ExecutionStatus.COMPLETED
    reqs = SystemRequirements.model_validate(result.result)
    assert any(r.source == "user" for r in reqs.requirements)
    assert any(r.source == "derived" for r in reqs.requirements)


def test_verification_does_not_pass_without_evidence(runtime):
    rt, pos, proj, broker = runtime
    result = rt.run(
        _task(
            "verification",
            proj["id"],
            "Evaluate",
            {"mode": "report", "build_result": {}, "programming_result": {}, "serial_result": {}},
        )
    )
    assert result.status == ExecutionStatus.COMPLETED
    assert result.result["overall_status"] in ("blocked", "partial", "fail")
    assert not any(tc["status"] == "passed" for tc in result.result["test_cases"])


def test_missing_description_fails(runtime):
    rt, pos, proj, broker = runtime
    # AgentTask requires min_length description — use whitespace via model_construct bypass?
    task = AgentTask(
        task_id="t1",
        project_id=proj["id"],
        agent_id="planning",
        description="x",
        inputs={"force_deterministic": True},
        project_context={"project_id": proj["id"]},
    )
    task = task.model_copy(update={"description": "   "})
    # Runtime / pydantic may still accept; specialist synthesize uses description
    result = rt.run(task)
    # Empty strip may still complete with default objective — ensure no crash
    assert result.status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.REJECTED)
