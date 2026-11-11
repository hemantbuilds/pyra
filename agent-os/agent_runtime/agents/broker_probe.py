"""
Deterministic Broker probe agent.

Calls a safe L0 Device Broker tool through AgentBrokerSession → BrokerClient.
Not a production specialist — validates the internal tool path for Phase 5b.
"""

from __future__ import annotations

from agent_runtime.agent import SpecialistAgent
from agent_runtime.contracts import AgentManifest, AgentResult, AgentTask, ExecutionStatus
from agent_runtime.context import ExecutionContext
from agent_runtime.errors import BrokerAccessDenied


class BrokerProbeAgent(SpecialistAgent):
    def manifest(self) -> AgentManifest:
        return AgentManifest(
            agent_id="broker_probe",
            name="Broker Probe Agent",
            description="Calls get_system_info via BrokerClient (L0) to validate tool path",
            capabilities=["broker_probe", "runtime_broker_test"],
            allowed_tools=["get_system_info", "list_broker_tools"],
            max_level="L0",
            timeout_s=15.0,
            framework="native",
        )

    def run(self, task: AgentTask, ctx: ExecutionContext) -> AgentResult:
        ctx.assert_project_identity()
        if ctx.broker is None:
            return AgentResult(
                agent_id="broker_probe",
                task_id=task.task_id,
                project_id=ctx.project_id,
                status=ExecutionStatus.BLOCKED,
                summary="No broker session",
                errors=["ExecutionContext.broker is None"],
                correlation_id=task.correlation_id,
            )

        mode = str(task.inputs.get("mode") or "system_info")

        if mode == "disallowed_tool":
            # Attempt a tool not on allowlist — session must deny before Broker.
            try:
                ctx.broker.call("run_allowed_command", {"argv": ["uname", "-a"]})
            except BrokerAccessDenied as exc:
                return AgentResult(
                    agent_id="broker_probe",
                    task_id=task.task_id,
                    project_id=ctx.project_id,
                    status=ExecutionStatus.BLOCKED,
                    summary="Disallowed tool correctly rejected",
                    result={"denied": True},
                    errors=[str(exc)],
                    recommended_next_action="use_allowed_tool",
                    correlation_id=task.correlation_id,
                )
            return AgentResult(
                agent_id="broker_probe",
                task_id=task.task_id,
                project_id=ctx.project_id,
                status=ExecutionStatus.FAILED,
                summary="Expected allowlist denial did not occur",
                errors=["disallowed tool was not rejected"],
                correlation_id=task.correlation_id,
            )

        if mode == "unknown_broker_tool":
            # On allowlist for this test path only if we add it — use a name that
            # is allowlisted below via temporary call; instead call through session
            # after temporarily... Better: call a tool that IS allowlisted but
            # Broker will deny as unknown if we use a fake name not in allowlist.
            # Use get_system_info path for success; for Broker denial of permission,
            # request L3-ish via elevating — Broker caps Phase max.
            #
            # Call a tool not registered at Broker after adding to allowlist locally:
            try:
                # Not on agent allowlist → session denial
                ctx.broker.call("flash_firmware", {})
            except BrokerAccessDenied as exc:
                return AgentResult(
                    agent_id="broker_probe",
                    task_id=task.task_id,
                    project_id=ctx.project_id,
                    status=ExecutionStatus.BLOCKED,
                    summary="Unregistered/disallowed hardware tool rejected",
                    errors=[str(exc)],
                    correlation_id=task.correlation_id,
                )
            return AgentResult(
                agent_id="broker_probe",
                task_id=task.task_id,
                project_id=ctx.project_id,
                status=ExecutionStatus.FAILED,
                summary="Expected rejection missing",
                errors=["flash_firmware was not rejected"],
                correlation_id=task.correlation_id,
            )

        # Default: safe L0 call
        result = ctx.broker.call("get_system_info", {})
        if not result.ok:
            status = (
                ExecutionStatus.BLOCKED
                if result.status == "denied"
                else ExecutionStatus.FAILED
            )
            return AgentResult(
                agent_id="broker_probe",
                task_id=task.task_id,
                project_id=ctx.project_id,
                status=status,
                summary=f"Broker call {result.status}",
                errors=[result.error or "broker failure"],
                evidence=[
                    {
                        "operation_id": result.operation_id,
                        "tool": result.tool,
                        "status": result.status,
                    }
                ],
                correlation_id=task.correlation_id,
            )

        return AgentResult(
            agent_id="broker_probe",
            task_id=task.task_id,
            project_id=ctx.project_id,
            status=ExecutionStatus.COMPLETED,
            summary="Broker L0 get_system_info succeeded",
            result={"system_info": result.data},
            evidence=[
                {
                    "type": "broker_tool",
                    "tool": result.tool,
                    "operation_id": result.operation_id,
                    "level": result.level,
                }
            ],
            recommended_next_action="none",
            correlation_id=task.correlation_id,
        )
