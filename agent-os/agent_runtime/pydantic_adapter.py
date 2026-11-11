"""
PydanticAI specialist adapter — implements SpecialistAgent without becoming the Runtime.

Deterministic agents do not import this module at runtime registration time
except when the research agent is bootstrapped.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional, TypeVar

from pydantic import BaseModel, ValidationError
from pydantic_ai import Agent, RunContext

from master.model_gateway import ModelGateway, ProviderError

from .agent import SpecialistAgent
from .contracts import AgentManifest, AgentResult, AgentTask, ExecutionStatus
from .context import ExecutionContext
from .errors import BrokerAccessDenied

log = logging.getLogger("pyra.agent_runtime.pydantic")

OutputT = TypeVar("OutputT", bound=BaseModel)


@dataclass
class SpecialistDeps:
    """Deps injected into PydanticAI tools — bound to one execution."""

    task: AgentTask
    ctx: ExecutionContext


def _safe_exc(exc: BaseException) -> str:
    """Stringify exceptions without leaking env-like secrets."""
    text = f"{type(exc).__name__}: {exc}"
    for needle in ("api_key", "API_KEY", "Bearer ", "sk-", "OPENAI_API_KEY"):
        if needle in text:
            return f"{type(exc).__name__}: [redacted provider error]"
    return text[:500]


class PydanticAISpecialistAgent(SpecialistAgent):
    """
    Base for PydanticAI-backed specialists.

    Subclasses define manifest, instructions, output_type, and optional tools.
    """

    def __init__(
        self,
        gateway: ModelGateway | None = None,
        *,
        model: Any = None,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        self.gateway = gateway or ModelGateway()
        self._forced_model = model
        self._provider = provider
        self._model_name = model_name

    def output_type(self) -> type[BaseModel]:
        raise NotImplementedError

    def system_instructions(self) -> str:
        raise NotImplementedError

    def tool_builders(self) -> list[Callable]:
        """Return callables that register tools on an Agent (optional)."""
        return []

    def map_output(
        self,
        output: BaseModel,
        *,
        task: AgentTask,
        ctx: ExecutionContext,
    ) -> AgentResult:
        raise NotImplementedError

    def build_user_prompt(self, task: AgentTask, ctx: ExecutionContext) -> str:
        ctx_bits = []
        for k, v in (task.project_context or {}).items():
            if k.lower() in ("api_key", "token", "password", "secret"):
                continue
            ctx_bits.append(f"- {k}: {v}")
        context_block = "\n".join(ctx_bits) if ctx_bits else "- (no additional project metadata)"
        return (
            f"Task ID: {task.task_id}\n"
            f"Project ID: {ctx.project_id}\n"
            f"Request:\n{task.description}\n\n"
            f"Bounded project context (authoritative; do not invent beyond this):\n"
            f"{context_block}\n\n"
            f"Additional inputs: {task.inputs or {}}\n"
        )

    def _resolve_model(self):
        if self._forced_model is not None:
            return self._forced_model
        return self.gateway.resolve_agent_model(
            provider=self._provider,
            model_name=self._model_name,
        )

    def _build_agent(self, model) -> Agent[SpecialistDeps, Any]:
        agent: Agent[SpecialistDeps, Any] = Agent(
            model,
            deps_type=SpecialistDeps,
            output_type=self.output_type(),
            instructions=self.system_instructions(),
        )
        for builder in self.tool_builders():
            builder(agent)
        return agent

    def run(self, task: AgentTask, ctx: ExecutionContext) -> AgentResult:
        ctx.assert_project_identity()
        manifest = self.manifest()

        if not (task.description or "").strip():
            return AgentResult(
                agent_id=manifest.agent_id,
                task_id=task.task_id,
                project_id=ctx.project_id,
                status=ExecutionStatus.FAILED,
                summary="Empty research request",
                errors=["description is required"],
                correlation_id=task.correlation_id,
            )

        try:
            model = self._resolve_model()
        except ProviderError as exc:
            status = (
                ExecutionStatus.BLOCKED
                if exc.code in ("provider_unavailable", "missing_credentials", "provider_disabled")
                else ExecutionStatus.FAILED
            )
            return AgentResult(
                agent_id=manifest.agent_id,
                task_id=task.task_id,
                project_id=ctx.project_id,
                status=status,
                summary=f"Model provider error: {exc.code}",
                errors=[str(exc)],
                evidence=[{"provider_error_code": exc.code}],
                correlation_id=task.correlation_id,
            )
        except Exception as exc:
            return AgentResult(
                agent_id=manifest.agent_id,
                task_id=task.task_id,
                project_id=ctx.project_id,
                status=ExecutionStatus.FAILED,
                summary="Model resolution failed",
                errors=[_safe_exc(exc)],
                correlation_id=task.correlation_id,
            )

        try:
            ctx.raise_if_cancelled()
        except Exception as exc:
            from master.invocation import CancelledError

            if isinstance(exc, CancelledError):
                return AgentResult(
                    agent_id=manifest.agent_id,
                    task_id=task.task_id,
                    project_id=ctx.project_id,
                    status=ExecutionStatus.CANCELLED,
                    summary="Execution cancelled before model invoke",
                    errors=[str(exc)],
                    correlation_id=task.correlation_id,
                )
            raise

        agent = self._build_agent(model)
        deps = SpecialistDeps(task=task, ctx=ctx)
        prompt = self.build_user_prompt(task, ctx)
        model_settings = {"timeout": float(ctx.timeout_s)} if ctx.timeout_s else None

        try:
            result = agent.run_sync(prompt, deps=deps, model_settings=model_settings)
            output = result.output
            ctx.raise_if_cancelled()
        except BrokerAccessDenied as exc:
            return AgentResult(
                agent_id=manifest.agent_id,
                task_id=task.task_id,
                project_id=ctx.project_id,
                status=ExecutionStatus.BLOCKED,
                summary="Broker access denied during tool use",
                errors=[str(exc)],
                evidence=[{"broker_calls": list(ctx.broker.calls) if ctx.broker else []}],
                correlation_id=task.correlation_id,
            )
        except ValidationError as exc:
            return AgentResult(
                agent_id=manifest.agent_id,
                task_id=task.task_id,
                project_id=ctx.project_id,
                status=ExecutionStatus.FAILED,
                summary="Invalid structured model output",
                errors=[str(exc)[:800]],
                correlation_id=task.correlation_id,
            )
        except Exception as exc:
            from master.invocation import CancelledError

            if isinstance(exc, CancelledError) or "cancelled" in str(exc).lower():
                return AgentResult(
                    agent_id=manifest.agent_id,
                    task_id=task.task_id,
                    project_id=ctx.project_id,
                    status=ExecutionStatus.CANCELLED,
                    summary="Execution cancelled",
                    errors=[_safe_exc(exc)],
                    correlation_id=task.correlation_id,
                )
            log.exception("pydantic-ai agent %s failed", manifest.agent_id)
            return AgentResult(
                agent_id=manifest.agent_id,
                task_id=task.task_id,
                project_id=ctx.project_id,
                status=ExecutionStatus.FAILED,
                summary="Specialist execution failed",
                errors=[_safe_exc(exc)],
                evidence=[{"broker_calls": list(ctx.broker.calls) if ctx.broker else []}],
                correlation_id=task.correlation_id,
            )

        if not isinstance(output, BaseModel):
            return AgentResult(
                agent_id=manifest.agent_id,
                task_id=task.task_id,
                project_id=ctx.project_id,
                status=ExecutionStatus.FAILED,
                summary="Empty or non-structured model output",
                errors=["output was not a BaseModel instance"],
                correlation_id=task.correlation_id,
            )

        try:
            mapped = self.map_output(output, task=task, ctx=ctx)
        except Exception as exc:
            return AgentResult(
                agent_id=manifest.agent_id,
                task_id=task.task_id,
                project_id=ctx.project_id,
                status=ExecutionStatus.FAILED,
                summary="Failed to map specialist output",
                errors=[_safe_exc(exc)],
                correlation_id=task.correlation_id,
            )

        if mapped.project_id != ctx.project_id:
            mapped.status = ExecutionStatus.FAILED
            mapped.errors = list(mapped.errors) + ["project identity mismatch in mapped result"]
            mapped.project_id = ctx.project_id
        return mapped


def register_broker_tool(agent: Agent, tool_name: str, description: str) -> None:
    """Register a Broker-backed tool; arguments passed through as a dict."""

    @agent.tool
    def _tool(ctx: RunContext[SpecialistDeps], arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Broker-mediated tool (name patched below)."""
        broker = ctx.deps.ctx.broker
        if broker is None:
            raise BrokerAccessDenied("no broker session on execution context")
        if tool_name not in broker.allowed_tools:
            raise BrokerAccessDenied(f"tool {tool_name!r} not on allowlist")
        result = broker.call(tool_name, arguments or {})
        return result.to_dict()

    _tool.__name__ = tool_name
    _tool.__doc__ = description
    # pydantic-ai uses function name; re-register under desired name is tricky.
    # Prefer explicit named wrappers in ResearchAgent instead.
