"""Phase 7 — Master multi-specialist workflow orchestration."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_runtime.service import reset_agent_runtime
from master import capabilities
from master.broker_service import get_broker, reset_broker
from master.contracts import IntentKind
from master.engineering_service import reset_engineering_os
from master.engineering_workflow import run_engineering_workflow
from master.model_gateway import deterministic_intent
from master.orchestrator import Orchestrator
from master.project_service import reset_project_os
from project_os.engineering_artifacts import load_latest_artifact


RT1170_USB = {
    "vid": "1fc9",
    "pid": "0143",
    "manufacturer": "NXP",
    "product": "MCU-Link CMSIS-DAP",
    "sysfs_path": "/sys/bus/usb/devices/1-1",
}


@pytest.fixture
def env(tmp_path):
    work = tmp_path / "PyraWork"
    work.mkdir()
    (work / "global").mkdir()
    (work / "projects").mkdir()

    capabilities.reset_registry()
    pos = reset_project_os(work)
    broker = reset_broker(work)
    reset_engineering_os()

    def ok_runner(argv, cwd, timeout, env_map):
        bdir = Path(cwd) / "build" / "zephyr"
        bdir.mkdir(parents=True, exist_ok=True)
        (bdir / "zephyr.bin").write_bytes(b"ELFBIN")
        (bdir / "zephyr.elf").write_bytes(b"ELF")
        return {
            "exit_code": 0,
            "timed_out": False,
            "stdout": "ninja: build success",
            "stderr": "",
            "resolved_executable": "/usr/bin/west",
        }

    executed = {"n": 0}

    def program_runner(**kwargs):
        executed["n"] += 1
        return {"success": True, "backend": "test", "stdout": "programmed", "stderr": ""}

    broker._build_runner = ok_runner
    broker._program_runner = program_runner
    reset_agent_runtime(broker_client=None, bootstrap=True)

    def which(name):
        return {
            "west": "/usr/bin/west",
            "cmake": "/usr/bin/cmake",
            "ninja": "/usr/bin/ninja",
            "arm-none-eabi-gcc": "/usr/bin/arm-none-eabi-gcc",
            "git": "/usr/bin/git",
            "python3": "/usr/bin/python3",
        }.get(name)

    yield {
        "work": work,
        "pos": pos,
        "broker": broker,
        "executed": executed,
        "which": which,
    }
    reset_agent_runtime()
    reset_engineering_os()
    reset_broker(work)
    reset_project_os(work)
    capabilities.reset_registry()


def test_intent_engineering_workflow():
    text = (
        "Start an embedded project using the development board. "
        "Plan the project, analyze the system requirements, identify the hardware, "
        "design the implementation, develop basic LED blink firmware, build it, "
        "ask for my approval before programming, program the board, test it, "
        "and prepare a complete engineering report."
    )
    intent = deterministic_intent(text)
    assert intent.kind == IntentKind.ENGINEERING_WORKFLOW


def test_workflow_to_approval_then_complete(env):
    from engineering_os.service import EngineeringOS

    orig = EngineeringOS.bringup_build

    def bringup_with_tools(self, **kwargs):
        kwargs.setdefault("which", env["which"])
        kwargs.setdefault("skip_live_discovery", True)
        kwargs.setdefault("inject_usb", [RT1170_USB])
        kwargs.setdefault("inject_serial", [])
        return orig(self, **kwargs)

    EngineeringOS.bringup_build = bringup_with_tools  # type: ignore[method-assign]
    try:
        result = run_engineering_workflow(
            request_text=(
                "Start an embedded project. Plan the project, analyze system requirements, "
                "prepare firmware, build it, request approval before programming, "
                "and prepare a complete engineering report."
            ),
            skip_live_discovery=True,
            inject_usb=[RT1170_USB],
            inject_serial=[],
        )
    finally:
        EngineeringOS.bringup_build = orig  # type: ignore[method-assign]

    assert result.capability == "engineering_workflow"
    assert result.project_id
    assert result.needs_confirm is not None
    assert result.needs_confirm.level.value == "L3"
    assert result.evidence["stage"] == "awaiting_programming_approval"

    plan = load_latest_artifact(env["work"], result.project_id, "project_plan")
    assert plan is not None
    reqs = load_latest_artifact(env["work"], result.project_id, "requirements")
    assert reqs is not None

    confirm_id = result.needs_confirm.id
    done = run_engineering_workflow(
        request_text="resume",
        project_id=result.project_id,
        confirm_id=confirm_id,
        confirm_approved=True,
    )
    prog = done.evidence.get("programming_result") or {}
    assert prog.get("success") is True
    assert env["executed"]["n"] == 1
    report = load_latest_artifact(env["work"], result.project_id, "engineering_report")
    assert report is not None
    assert done.evidence["stage"] == "complete"


def test_orchestrator_classifies_mark_request(env):
    orch = Orchestrator()
    text = (
        "Mark, I want to start an embedded project using the development board connected "
        "to this Linux device. Identify the hardware, plan the project, analyze the system "
        "requirements, determine the hardware and software architecture, prepare the firmware, "
        "build it, ask for my approval before programming, program the board, test it, and "
        "prepare a complete engineering report."
    )
    intent, _ = orch.gateway.classify_intent(text)
    assert intent.kind == IntentKind.ENGINEERING_WORKFLOW
