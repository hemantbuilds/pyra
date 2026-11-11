"""Phase 7 engineering specialists — PydanticAI + deterministic synthesize."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from agent_runtime.contracts import AgentManifest, AgentResult, AgentTask, ExecutionStatus
from agent_runtime.context import ExecutionContext
from agent_runtime.engineering_contracts import (
    ArchitectureComponent,
    EngineeringReport,
    FirmwareDesign,
    HardwareDesign,
    ProjectPlan,
    Requirement,
    SystemArchitecture,
    SystemRequirements,
    TestCase,
    VerificationPlan,
    VerificationReport,
)
from agent_runtime.pydantic_adapter import PydanticAISpecialistAgent


def _completed(
    agent_id: str,
    task: AgentTask,
    ctx: ExecutionContext,
    *,
    summary: str,
    output: BaseModel,
    evidence: Optional[list] = None,
) -> AgentResult:
    return AgentResult(
        agent_id=agent_id,
        task_id=task.task_id,
        project_id=ctx.project_id,
        status=ExecutionStatus.COMPLETED,
        summary=summary,
        result=output.model_dump(mode="json"),
        evidence=evidence or [],
        correlation_id=task.correlation_id,
    )


class _EngineeringBase(PydanticAISpecialistAgent):
    """Shared run path with force_deterministic synthesize."""

    agent_id: str = "engineering"
    agent_name: str = "Engineering Specialist"
    description: str = ""
    capabilities: list[str] = []
    output_model: type[BaseModel] = BaseModel

    def manifest(self) -> AgentManifest:
        return AgentManifest(
            agent_id=self.agent_id,
            name=self.agent_name,
            description=self.description,
            capabilities=list(self.capabilities),
            allowed_tools=[],
            max_level="L0",
            timeout_s=90.0,
            framework="pydantic_ai",
            output_schema={"type": self.output_model.__name__},
        )

    def output_type(self) -> type[BaseModel]:
        return self.output_model

    def system_instructions(self) -> str:
        return (
            f"You are PYRA {self.agent_name}. Return only the structured output schema. "
            "Never invent hardware evidence, build results, flash results, or test passes. "
            "Distinguish user requirements from inferred assumptions. "
            "Use only the bounded project context provided."
        )

    def synthesize(self, task: AgentTask, ctx: ExecutionContext) -> BaseModel:
        raise NotImplementedError

    def map_output(self, output: BaseModel, *, task: AgentTask, ctx: ExecutionContext) -> AgentResult:
        return _completed(
            self.agent_id,
            task,
            ctx,
            summary=f"{self.agent_name} completed",
            output=output,
        )

    def run(self, task: AgentTask, ctx: ExecutionContext) -> AgentResult:
        ctx.assert_project_identity()
        if (task.inputs or {}).get("force_deterministic"):
            try:
                output = self.synthesize(task, ctx)
                mapped = self.map_output(output, task=task, ctx=ctx)
                if mapped.project_id != ctx.project_id:
                    mapped.status = ExecutionStatus.FAILED
                    mapped.errors = list(mapped.errors) + ["project identity mismatch"]
                    mapped.project_id = ctx.project_id
                return mapped
            except Exception as exc:  # noqa: BLE001
                return AgentResult(
                    agent_id=self.agent_id,
                    task_id=task.task_id,
                    project_id=ctx.project_id,
                    status=ExecutionStatus.FAILED,
                    summary="Deterministic synthesize failed",
                    errors=[f"{type(exc).__name__}: {exc}"],
                    correlation_id=task.correlation_id,
                )
        return super().run(task, ctx)


class PlanningAgent(_EngineeringBase):
    agent_id = "planning"
    agent_name = "Project Planning Specialist"
    description = "Produces structured ProjectPlan for embedded engineering projects"
    capabilities = ["planning", "project_plan", "milestones"]
    output_model = ProjectPlan

    def synthesize(self, task: AgentTask, ctx: ExecutionContext) -> ProjectPlan:
        objective = (task.description or "").strip() or "Embedded engineering project"
        return ProjectPlan(
            objective=objective[:2000],
            scope=(
                "Plan, requirements, architecture, hardware analysis, firmware design, "
                "build, approved programming, verification, and engineering report."
            ),
            deliverables=[
                "Project plan",
                "System requirements",
                "System architecture",
                "Hardware design analysis",
                "Firmware design and source",
                "Build evidence",
                "Verification plan and report",
                "Final engineering report",
            ],
            milestones=[
                "Planning complete",
                "Requirements approved",
                "Architecture defined",
                "Hardware identified",
                "Firmware designed and built",
                "Programming approved and executed (if supported)",
                "Verification complete",
                "Documentation complete",
            ],
            dependencies=[
                "Active Project OS project with workspace",
                "Hardware discovery evidence from Engineering OS",
                "Human approval before L3 programming",
            ],
            risks=[
                "Unsupported or ambiguous board identity",
                "Missing toolchain or programmer on host",
                "Missing serial ACM for runtime verification",
            ],
            assumptions=[
                "User wants a basic LED blink bring-up as the first qualification scenario "
                "unless otherwise stated",
            ],
            required_decisions=[
                "Confirm programming after reviewing artifact hash",
                "Clarify board if discovery is ambiguous",
            ],
            acceptance_criteria=[
                "Requirements recorded in Project OS",
                "Firmware build evidence captured via Device Broker",
                "Programming only after Broker-validated approval",
                "Verification distinguishes evidence-backed vs unverified results",
            ],
        )


class RequirementsAgent(_EngineeringBase):
    agent_id = "requirements"
    agent_name = "Requirements and Systems Engineering Specialist"
    description = "Produces SystemRequirements with explicit assumption tracking"
    capabilities = ["requirements", "systems_engineering"]
    output_model = SystemRequirements

    def synthesize(self, task: AgentTask, ctx: ExecutionContext) -> SystemRequirements:
        inputs = task.inputs or {}
        user_reqs = list(inputs.get("user_requirements") or [])
        reqs: list[Requirement] = []
        for i, text in enumerate(user_reqs, start=1):
            reqs.append(
                Requirement(
                    id=f"USR-{i:03d}",
                    description=str(text),
                    category="functional",
                    priority="must",
                    source="user",
                    rationale="Stated by user",
                    acceptance_criterion=str(text),
                    verification_method="test",
                    status="proposed",
                )
            )
        derived = [
            ("REQ-001", "Firmware must initialize the identified supported board.", "functional"),
            ("REQ-002", "Configured LED must toggle periodically when firmware runs.", "functional"),
            ("REQ-003", "Firmware must emit a startup signature on the runtime observation interface when available.", "functional"),
            ("REQ-004", "Firmware must be buildable with the supported host toolchain for the board profile.", "constraint"),
            ("REQ-005", "Programming requires explicit human approval bound to artifact SHA-256.", "constraint"),
            ("REQ-006", "Verification must not claim pass without recorded evidence.", "non_functional"),
        ]
        for rid, desc, cat in derived:
            reqs.append(
                Requirement(
                    id=rid,
                    description=desc,
                    category=cat,  # type: ignore[arg-type]
                    priority="must",
                    source="derived",
                    rationale="Derived for LED blink qualification demonstration",
                    acceptance_criterion=desc,
                    verification_method="test",
                    status="proposed",
                )
            )
        return SystemRequirements(
            requirements=reqs,
            open_questions=["Confirm physical LED observation method if no instrument is available."],
            assumptions=["LED blink is an acceptable first firmware deliverable for board bring-up."],
        )


class ArchitectureAgent(_EngineeringBase):
    agent_id = "architecture"
    agent_name = "System Architecture Specialist"
    description = "Produces project-level SystemArchitecture for the user embedded system"
    capabilities = ["architecture", "system_design"]
    output_model = SystemArchitecture

    def synthesize(self, task: AgentTask, ctx: ExecutionContext) -> SystemArchitecture:
        return SystemArchitecture(
            overview=(
                "MCU development board hosts firmware that toggles an on-board LED. "
                "Host Linux device builds and programs via Device Broker. Runtime evidence "
                "is observed via supported serial/debug interface when present."
            ),
            components=[
                ArchitectureComponent(name="MCU", responsibility="Execute firmware", allocation="hardware"),
                ArchitectureComponent(name="GPIO/LED", responsibility="Visual indication", allocation="hardware"),
                ArchitectureComponent(name="Firmware app", responsibility="Init + blink loop + startup signature", allocation="firmware"),
                ArchitectureComponent(name="Debug/program interface", responsibility="Load image / reset", allocation="interface"),
                ArchitectureComponent(name="Host Engineering OS", responsibility="Discover, build, program, verify", allocation="host"),
            ],
            interfaces=[
                "GPIO LED driver interface",
                "SWD/JTAG or board programmer interface",
                "UART/USB serial observation (optional)",
            ],
            data_flows=[
                "Host build → firmware artifact → programmer → MCU flash",
                "MCU → serial/debug → host capture (verification)",
            ],
            hardware_software_allocation=[
                "LED physical pin mapping owned by hardware design / board profile",
                "Blink timing and startup signature owned by firmware",
            ],
            constraints=[
                "No OTP/fuse programming",
                "L3 programming only with Broker approval",
            ],
            trade_offs=[
                "Zephyr blinky template vs bare-metal — prefer supported SDK from board profile",
            ],
            open_decisions=[
                "Exact LED pin if board profile does not define it",
            ],
        )


class HardwareEngAgent(_EngineeringBase):
    agent_id = "hardware_eng"
    agent_name = "Hardware Engineering Specialist"
    description = "Evidence-based HardwareDesign from discovery / board profiles"
    capabilities = ["hardware", "board_analysis"]
    output_model = HardwareDesign

    def synthesize(self, task: AgentTask, ctx: ExecutionContext) -> HardwareDesign:
        inputs = task.inputs or {}
        board = dict(inputs.get("board_identification") or {})
        discovery = dict(inputs.get("discovery") or {})
        evidence = []
        if discovery:
            evidence.append(f"discovery_keys={sorted(discovery.keys())}")
        if board.get("board_id") or board.get("profile_id"):
            evidence.append(f"board_match={board.get('board_id') or board.get('profile_id')}")
        if board.get("confidence"):
            evidence.append(f"confidence={board.get('confidence')}")
        unknowns = []
        if not (board.get("board_id") or board.get("profile_id") or board.get("zephyr_board")):
            unknowns.append("No qualified board identity from discovery evidence")
        if not board.get("gpio_led") and not board.get("led"):
            unknowns.append("LED pin mapping not confirmed in evidence")
        return HardwareDesign(
            board_id=board.get("board_id") or board.get("profile_id"),
            board_name=board.get("board_name") or board.get("name"),
            mcu_family=board.get("mcu_family"),
            mcu_model=board.get("mcu_model"),
            confidence=str(board.get("confidence") or "unknown"),
            evidence_summary=evidence,
            gpio_led=board.get("gpio_led") or board.get("led"),
            debug_interface=board.get("debug_interface") or board.get("probe"),
            recommended_sdk=board.get("sdk") or board.get("recommended_sdk") or "zephyr",
            programming_method=board.get("programming_method") or board.get("flasher"),
            unknowns=unknowns,
            assumptions=[],
            invented_claims=[],
        )


class FirmwareEngAgent(_EngineeringBase):
    agent_id = "firmware_eng"
    agent_name = "Firmware Engineering Specialist"
    description = "Produces FirmwareDesign from approved requirements and hardware"
    capabilities = ["firmware", "firmware_design"]
    output_model = FirmwareDesign

    def synthesize(self, task: AgentTask, ctx: ExecutionContext) -> FirmwareDesign:
        inputs = task.inputs or {}
        hw = dict(inputs.get("hardware_design") or {})
        target = hw.get("zephyr_board") or (inputs.get("board_identification") or {}).get("zephyr_board")
        return FirmwareDesign(
            architecture_overview=(
                "Single-application Zephyr (or supported SDK) blink sample: board init, "
                "GPIO LED toggle loop, optional startup console signature."
            ),
            modules=["main", "gpio_led", "startup_banner"],
            drivers=["gpio"],
            interfaces=["LED GPIO", "console UART if available"],
            execution_model="single_main_loop",
            source_structure=["app/src/main.c", "app/CMakeLists.txt", "app/prj.conf"],
            build_system="zephyr_west",
            build_target=target,
            test_strategy=[
                "Build validation via Broker west_build",
                "Programming validation after approval",
                "Startup signature capture when serial available",
            ],
            known_limitations=[
                "Does not invent board pin maps; uses profile / hardware design only",
                "Physical LED observation may remain unverified without instruments",
            ],
        )


class VerificationAgent(_EngineeringBase):
    agent_id = "verification"
    agent_name = "Verification and Testing Specialist"
    description = "Produces VerificationPlan / VerificationReport from evidence"
    capabilities = ["verification", "testing"]
    output_model = VerificationReport

    def synthesize(self, task: AgentTask, ctx: ExecutionContext) -> BaseModel:
        inputs = task.inputs or {}
        mode = (inputs.get("mode") or "report").lower()
        reqs = list((inputs.get("requirements") or {}).get("requirements") or inputs.get("requirement_ids") or [])
        if mode == "plan":
            cases = []
            for item in reqs:
                if isinstance(item, dict):
                    rid = item.get("id") or "REQ"
                    desc = item.get("description") or rid
                else:
                    rid = str(item)
                    desc = rid
                cases.append(
                    TestCase(
                        test_id=f"TC-{rid}",
                        requirement_id=rid,
                        objective=f"Verify {desc}",
                        preconditions=["Approved requirements available"],
                        procedure=["Execute corresponding Engineering OS stage", "Collect evidence"],
                        expected_result="Evidence matches acceptance criterion",
                        status="planned",
                    )
                )
            if not cases:
                cases = [
                    TestCase(
                        test_id="TC-BUILD",
                        requirement_id="REQ-004",
                        objective="Confirm firmware compiles",
                        procedure=["Run west_build via Device Broker"],
                        expected_result="exit_code=0 and artifact present",
                        status="planned",
                    ),
                    TestCase(
                        test_id="TC-PROG",
                        requirement_id="REQ-005",
                        objective="Confirm programming after approval",
                        procedure=["Mint approval", "Human confirm", "program_firmware"],
                        expected_result="Broker reports success",
                        status="planned",
                    ),
                    TestCase(
                        test_id="TC-START",
                        requirement_id="REQ-003",
                        objective="Confirm startup signature",
                        procedure=["Reset/start", "serial_capture_passive"],
                        expected_result="Signature present in capture",
                        status="planned",
                    ),
                ]
            return VerificationPlan(test_cases=cases, notes=["No test marked passed without evidence."])

        # report mode
        build = dict(inputs.get("build_result") or {})
        prog = dict(inputs.get("programming_result") or {})
        serial = dict(inputs.get("serial_result") or {})
        plan = dict(inputs.get("verification_plan") or {})
        cases_in = list(plan.get("test_cases") or [])
        out_cases: list[TestCase] = []
        satisfied: list[str] = []
        failed: list[str] = []
        unverified: list[str] = []
        limitations: list[str] = []

        def _eval(tc: dict) -> TestCase:
            tid = tc.get("test_id") or "TC"
            rid = tc.get("requirement_id") or ""
            status = "not_run"
            actual = ""
            evidence: list[str] = []
            if "BUILD" in tid.upper() or rid == "REQ-004":
                if build.get("success") is True or build.get("exit_code") == 0:
                    status = "passed"
                    actual = "Build succeeded"
                    evidence.append("build_result")
                    satisfied.append(rid)
                elif build:
                    status = "failed"
                    actual = "Build did not succeed"
                    evidence.append("build_result")
                    failed.append(rid)
                else:
                    status = "blocked"
                    actual = "No build evidence"
                    unverified.append(rid)
            elif "PROG" in tid.upper() or rid == "REQ-005":
                if prog.get("success") is True:
                    status = "passed"
                    actual = "Programming succeeded with approval"
                    evidence.append("programming_result")
                    satisfied.append(rid)
                elif prog.get("denied") or prog.get("blocked"):
                    status = "blocked"
                    actual = str(prog.get("reason") or "Programming blocked")
                    unverified.append(rid)
                    limitations.append(actual)
                elif prog:
                    status = "failed"
                    actual = "Programming failed"
                    failed.append(rid)
                else:
                    status = "not_run"
                    actual = "Programming not attempted"
                    unverified.append(rid)
            elif "START" in tid.upper() or rid == "REQ-003":
                text = ""
                if isinstance(serial.get("text"), str):
                    text = serial["text"]
                elif isinstance(serial.get("data"), (bytes, bytearray)):
                    text = bytes(serial["data"]).decode("utf-8", errors="replace")
                elif isinstance(serial.get("data"), str):
                    text = serial["data"]
                if text and ("PYRA" in text or "blink" in text.lower() or "boot" in text.lower()):
                    status = "passed"
                    actual = "Startup evidence present"
                    evidence.append("serial_result")
                    satisfied.append(rid)
                elif serial:
                    status = "failed"
                    actual = "Serial captured but signature not found"
                    failed.append(rid)
                    limitations.append("Physical LED not inferred from serial alone")
                else:
                    status = "blocked"
                    actual = "No serial capture evidence"
                    unverified.append(rid)
                    limitations.append("Runtime serial verification unavailable")
            else:
                status = "not_run"
                unverified.append(rid)
            return TestCase(
                test_id=tid,
                requirement_id=rid,
                objective=tc.get("objective") or "",
                preconditions=list(tc.get("preconditions") or []),
                procedure=list(tc.get("procedure") or []),
                expected_result=tc.get("expected_result") or "",
                actual_result=actual,
                evidence=evidence,
                status=status,  # type: ignore[arg-type]
            )

        if cases_in:
            out_cases = [_eval(c if isinstance(c, dict) else {}) for c in cases_in]
        else:
            out_cases = [
                _eval({"test_id": "TC-BUILD", "requirement_id": "REQ-004", "objective": "Build"}),
                _eval({"test_id": "TC-PROG", "requirement_id": "REQ-005", "objective": "Program"}),
                _eval({"test_id": "TC-START", "requirement_id": "REQ-003", "objective": "Startup"}),
            ]

        if failed:
            overall = "fail"
        elif satisfied and not unverified:
            overall = "pass"
        elif satisfied:
            overall = "partial"
        else:
            overall = "blocked"
        return VerificationReport(
            test_cases=out_cases,
            satisfied_requirements=sorted(set(x for x in satisfied if x)),
            failed_requirements=sorted(set(x for x in failed if x)),
            unverified_requirements=sorted(set(x for x in unverified if x)),
            overall_status=overall,  # type: ignore[arg-type]
            limitations=limitations,
        )

    def map_output(self, output: BaseModel, *, task: AgentTask, ctx: ExecutionContext) -> AgentResult:
        kind = type(output).__name__
        return _completed(
            self.agent_id,
            task,
            ctx,
            summary=f"Verification produced {kind}",
            output=output,
        )


class DocumentationAgent(_EngineeringBase):
    agent_id = "documentation"
    agent_name = "Documentation and Reporting Specialist"
    description = "Produces EngineeringReport from Project OS evidence only"
    capabilities = ["documentation", "engineering_report"]
    output_model = EngineeringReport

    def synthesize(self, task: AgentTask, ctx: ExecutionContext) -> EngineeringReport:
        inputs = task.inputs or {}
        plan = dict(inputs.get("project_plan") or {})
        reqs = dict(inputs.get("requirements") or {})
        arch = dict(inputs.get("architecture") or {})
        hw = dict(inputs.get("hardware_design") or {})
        fw = dict(inputs.get("firmware_design") or {})
        build = dict(inputs.get("build_result") or {})
        prog = dict(inputs.get("programming_result") or {})
        ver = dict(inputs.get("verification_report") or {})
        missing = []
        if not plan:
            missing.append("project_plan")
        if not reqs:
            missing.append("requirements")
        if not build:
            missing.append("build_evidence")
        final = ver.get("overall_status") or inputs.get("final_status") or "incomplete"
        return EngineeringReport(
            objective=plan.get("objective") or (task.description or "")[:500],
            project_plan_summary=(plan.get("scope") or "")[:1000] if plan else "Not available",
            requirements_summary=f"{len(reqs.get('requirements') or [])} requirements recorded" if reqs else "Not available",
            architecture_summary=(arch.get("overview") or "Not available")[:1000],
            hardware_summary=(
                f"board={hw.get('board_id') or 'unknown'} confidence={hw.get('confidence') or 'unknown'}"
                if hw
                else "Not available"
            ),
            firmware_summary=(fw.get("architecture_overview") or "Not available")[:1000],
            implementation_summary=str(inputs.get("implementation_summary") or "See firmware source in project workspace"),
            build_summary=str(build.get("summary") or build or "No build evidence"),
            programming_summary=str(prog.get("summary") or prog or "Programming not executed or not evidenced"),
            verification_summary=str(ver.get("overall_status") or ver or "No verification report"),
            open_issues=list(inputs.get("open_issues") or missing),
            risks=list(plan.get("risks") or []),
            limitations=list(ver.get("limitations") or []) + (
                ["Report omits fabricated evidence for missing stages"] if missing else []
            ),
            final_status=str(final),
            evidence_refs=list(inputs.get("evidence_refs") or []),
        )
