"""Phase 7 — structured specialist I/O contracts (Pydantic)."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ProjectPlan(BaseModel):
    objective: str = Field(..., min_length=1)
    scope: str = Field(..., min_length=1)
    deliverables: list[str] = Field(default_factory=list)
    milestones: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    required_decisions: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)


class Requirement(BaseModel):
    id: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    category: Literal["functional", "non_functional", "interface", "constraint"] = "functional"
    priority: Literal["must", "should", "may"] = "must"
    source: Literal["user", "inferred", "derived"] = "derived"
    rationale: str = ""
    acceptance_criterion: str = ""
    verification_method: Literal["inspection", "analysis", "test", "demonstration"] = "test"
    status: Literal["proposed", "approved", "satisfied", "failed", "deferred"] = "proposed"


class SystemRequirements(BaseModel):
    requirements: list[Requirement] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class ArchitectureComponent(BaseModel):
    name: str
    responsibility: str
    allocation: Literal["hardware", "firmware", "host", "interface"] = "firmware"


class SystemArchitecture(BaseModel):
    overview: str = Field(..., min_length=1)
    components: list[ArchitectureComponent] = Field(default_factory=list)
    interfaces: list[str] = Field(default_factory=list)
    data_flows: list[str] = Field(default_factory=list)
    hardware_software_allocation: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    trade_offs: list[str] = Field(default_factory=list)
    open_decisions: list[str] = Field(default_factory=list)


class HardwareDesign(BaseModel):
    board_id: Optional[str] = None
    board_name: Optional[str] = None
    mcu_family: Optional[str] = None
    mcu_model: Optional[str] = None
    confidence: str = "unknown"
    evidence_summary: list[str] = Field(default_factory=list)
    gpio_led: Optional[str] = None
    debug_interface: Optional[str] = None
    recommended_sdk: Optional[str] = None
    programming_method: Optional[str] = None
    unknowns: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    invented_claims: list[str] = Field(default_factory=list)


class FirmwareDesign(BaseModel):
    architecture_overview: str = Field(..., min_length=1)
    modules: list[str] = Field(default_factory=list)
    drivers: list[str] = Field(default_factory=list)
    interfaces: list[str] = Field(default_factory=list)
    execution_model: str = "single_main_loop"
    source_structure: list[str] = Field(default_factory=list)
    build_system: str = "zephyr_west"
    build_target: Optional[str] = None
    test_strategy: list[str] = Field(default_factory=list)
    known_limitations: list[str] = Field(default_factory=list)


class TestCase(BaseModel):
    test_id: str
    requirement_id: str
    objective: str
    preconditions: list[str] = Field(default_factory=list)
    procedure: list[str] = Field(default_factory=list)
    expected_result: str = ""
    actual_result: str = ""
    evidence: list[str] = Field(default_factory=list)
    status: Literal["planned", "passed", "failed", "blocked", "not_run"] = "planned"


class VerificationPlan(BaseModel):
    test_cases: list[TestCase] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class VerificationReport(BaseModel):
    test_cases: list[TestCase] = Field(default_factory=list)
    satisfied_requirements: list[str] = Field(default_factory=list)
    failed_requirements: list[str] = Field(default_factory=list)
    unverified_requirements: list[str] = Field(default_factory=list)
    overall_status: Literal["pass", "fail", "partial", "blocked"] = "blocked"
    limitations: list[str] = Field(default_factory=list)


class EngineeringReport(BaseModel):
    objective: str = ""
    project_plan_summary: str = ""
    requirements_summary: str = ""
    architecture_summary: str = ""
    hardware_summary: str = ""
    firmware_summary: str = ""
    implementation_summary: str = ""
    build_summary: str = ""
    programming_summary: str = ""
    verification_summary: str = ""
    open_issues: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    final_status: str = "incomplete"
    evidence_refs: list[str] = Field(default_factory=list)
