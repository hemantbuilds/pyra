"""Deterministic echo agent — validates runtime contracts without models or tools."""

from __future__ import annotations

from agent_runtime.agent import SpecialistAgent
from agent_runtime.contracts import AgentManifest, AgentResult, AgentTask, ExecutionStatus
from agent_runtime.context import ExecutionContext


class EchoAgent(SpecialistAgent):
    def manifest(self) -> AgentManifest:
        return AgentManifest(
            agent_id="echo",
            name="Echo Agent",
            description="Deterministic test agent that echoes the task (no tools)",
            capabilities=["echo", "runtime_self_test"],
            allowed_tools=[],
            max_level="L0",
            timeout_s=5.0,
            framework="native",
        )

    def run(self, task: AgentTask, ctx: ExecutionContext) -> AgentResult:
        ctx.assert_project_identity()
        if task.inputs.get("force_fail"):
            return AgentResult(
                agent_id="echo",
                task_id=task.task_id,
                project_id=ctx.project_id,
                status=ExecutionStatus.FAILED,
                summary="Forced failure",
                errors=["force_fail requested"],
                correlation_id=task.correlation_id,
            )
        if task.inputs.get("force_invalid_result"):
            # Intentionally return a non-structured payload; Runtime must reject.
            return {"speech": "not a structured result"}  # type: ignore[return-value]

        return AgentResult(
            agent_id="echo",
            task_id=task.task_id,
            project_id=ctx.project_id,
            status=ExecutionStatus.COMPLETED,
            summary=f"Echo: {task.description}",
            result={
                "echo": task.description,
                "inputs": dict(task.inputs),
                "context_keys": sorted(ctx.project_context.keys()),
            },
            evidence=[{"type": "echo", "observed": True}],
            recommended_next_action="none",
            correlation_id=task.correlation_id,
        )
