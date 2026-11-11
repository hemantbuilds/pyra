"""
Research Agent — first PydanticAI-powered specialist (Phase 5c).

Tools go only through AgentBrokerSession → BrokerClient → Device Broker.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.output import NativeOutput

from agent_runtime.contracts import AgentManifest, AgentResult, AgentTask, ExecutionStatus
from agent_runtime.context import ExecutionContext
from agent_runtime.errors import BrokerAccessDenied
from agent_runtime.pydantic_adapter import PydanticAISpecialistAgent, SpecialistDeps
from agent_runtime.research_models import ResearchReport

_RESEARCH_INSTRUCTIONS = """
You are PYRA Research Agent — a technical research specialist.

Rules (mandatory):
1. Distinguish observed/supplied facts from assumptions.
2. List unknowns explicitly when information is missing.
3. Never invent connected hardware, MCU identity, board names, test results,
   repository file contents, or tool execution outcomes.
4. If asked which MCU/board is connected and no discovery evidence is in context,
   set confidence=low, requires_human_review=true, and recommend hardware discovery
   via Engineering OS / Device Broker — do not guess.
5. Use only the bounded project context provided. Never claim knowledge of other projects.
6. Do not request unrestricted shell, flash, erase, serial TX, or L2/L3 operations.
7. If you call a tool, only use tools provided to you; treat Broker denials as authoritative.
8. Return a complete ResearchReport with non-empty summary.
9. Keep findings/assumptions/unknowns/recommendations concise and technical.
""".strip()

_ALLOWED_TOOLS = [
    "get_system_info",
    "get_platform_info",
    "get_available_toolchains",
    "get_installed_tool_versions",
    "list_directory",
    "read_text_file",
]


def _broker_call(deps: SpecialistDeps, tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    broker = deps.ctx.broker
    if broker is None:
        raise BrokerAccessDenied("no broker session")
    result = broker.call(tool, arguments or {})
    return result.to_dict()


class ResearchAgent(PydanticAISpecialistAgent):
    """AI research specialist registered as agent_id=research."""

    def manifest(self) -> AgentManifest:
        return AgentManifest(
            agent_id="research",
            name="Research Agent",
            description="PydanticAI technical research specialist with structured ResearchReport output",
            capabilities=["research", "technical_analysis", "engineering_research"],
            allowed_tools=list(_ALLOWED_TOOLS),
            max_level="L0",
            timeout_s=60.0,
            framework="pydantic_ai",
            input_schema={"description": "string research request + project_context"},
            output_schema={"type": "ResearchReport"},
        )

    def output_type(self) -> type[BaseModel]:
        return ResearchReport

    def system_instructions(self) -> str:
        return _RESEARCH_INSTRUCTIONS

    def _build_agent(self, model) -> Agent[SpecialistDeps, Any]:
        # Phase 5d: Ollama + json_schema (NativeOutput) is more reliable on Pi
        # than unconstrained JSON. TestModel does not support NativeOutput.
        if isinstance(model, OllamaModel):
            output: Any = NativeOutput(ResearchReport)
        else:
            output = ResearchReport
        agent: Agent[SpecialistDeps, Any] = Agent(
            model,
            deps_type=SpecialistDeps,
            output_type=output,
            instructions=self.system_instructions(),
        )
        for builder in self.tool_builders():
            builder(agent)
        return agent

    def tool_builders(self):
        def _register(agent: Agent[SpecialistDeps, Any]) -> None:
            @agent.tool
            def get_system_info(ctx: RunContext[SpecialistDeps]) -> dict[str, Any]:
                """Read-only host system info via Device Broker (L0)."""
                return _broker_call(ctx.deps, "get_system_info")

            @agent.tool
            def get_platform_info(ctx: RunContext[SpecialistDeps]) -> dict[str, Any]:
                """Read-only platform info via Device Broker (L0)."""
                return _broker_call(ctx.deps, "get_platform_info")

            @agent.tool
            def get_available_toolchains(ctx: RunContext[SpecialistDeps]) -> dict[str, Any]:
                """List detected toolchains via Device Broker (L0)."""
                return _broker_call(ctx.deps, "get_available_toolchains")

            @agent.tool
            def get_installed_tool_versions(ctx: RunContext[SpecialistDeps]) -> dict[str, Any]:
                """Installed tool versions via Device Broker (L0)."""
                return _broker_call(ctx.deps, "get_installed_tool_versions")

            @agent.tool
            def list_directory(ctx: RunContext[SpecialistDeps], path: str = ".") -> dict[str, Any]:
                """List a directory inside approved project roots via Device Broker."""
                return _broker_call(ctx.deps, "list_directory", {"path": path})

            @agent.tool
            def read_text_file(ctx: RunContext[SpecialistDeps], path: str) -> dict[str, Any]:
                """Read a text file inside approved project roots via Device Broker."""
                return _broker_call(ctx.deps, "read_text_file", {"path": path})

        return [_register]

    def map_output(
        self,
        output: BaseModel,
        *,
        task: AgentTask,
        ctx: ExecutionContext,
    ) -> AgentResult:
        report = output if isinstance(output, ResearchReport) else ResearchReport.model_validate(output)
        warnings: list[str] = []
        if report.confidence == "low":
            warnings.append("low confidence")
        if report.requires_human_review:
            warnings.append("human review recommended")
        if report.unknowns:
            warnings.append(f"{len(report.unknowns)} unknown(s) listed")

        next_action = None
        if any("discover" in u.lower() or "hardware" in u.lower() for u in report.unknowns + report.recommendations):
            next_action = "run_hardware_discovery"
        elif report.requires_human_review:
            next_action = "human_review"

        evidence = [
            {
                "type": "research_report",
                "confidence": report.confidence,
                "requires_human_review": report.requires_human_review,
            }
        ]
        # Always record Broker mediation (including empty) so skipped tool-use is visible.
        if ctx.broker is not None:
            evidence.append({"broker_calls": list(ctx.broker.calls)})

        return AgentResult(
            agent_id="research",
            task_id=task.task_id,
            project_id=ctx.project_id,
            status=ExecutionStatus.COMPLETED,
            summary=report.summary,
            result=report.model_dump(),
            evidence=evidence,
            warnings=warnings,
            errors=[],
            recommended_next_action=next_action,
            correlation_id=task.correlation_id,
        )
