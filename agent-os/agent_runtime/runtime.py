"""Agent Runtime — lifecycle, validation, BrokerClient integration."""

from __future__ import annotations

import concurrent.futures
import logging
import time
from typing import Any, Optional

from device_broker.client import BrokerClient
from pydantic import ValidationError

from .agent import SpecialistAgent
from .broker_session import AgentBrokerSession
from .contracts import AgentResult, AgentTask, ExecutionStatus
from .context import ExecutionContext
from .errors import (
    AgentTimeoutError,
    BrokerAccessDenied,
    InvalidResultError,
    InvalidTaskError,
    UnknownAgentError,
)
from .registry import AgentRegistry

log = logging.getLogger("pyra.agent_runtime")

_SUCCESS = {ExecutionStatus.COMPLETED}
_TERMINAL_FAIL = {
    ExecutionStatus.FAILED,
    ExecutionStatus.CANCELLED,
    ExecutionStatus.BLOCKED,
    ExecutionStatus.REJECTED,
}


def _cap_level(a: str, b: str) -> str:
    """Return the lower of two L0–L3 labels."""
    def _n(x: str) -> int:
        try:
            return int(str(x).upper().lstrip("L"))
        except ValueError:
            return 0

    return a if _n(a) <= _n(b) else b


class AgentRuntime:
    """
    Owns specialist execution lifecycle.

    Does not own Project OS state. Tools go through BrokerClient only.
    """

    PHASE_MAX_LEVEL = "L1"  # Phase 5b ceiling — no L2/L3

    def __init__(
        self,
        registry: AgentRegistry | None = None,
        broker_client: BrokerClient | None = None,
    ):
        self.registry = registry or AgentRegistry()
        self._broker_client = broker_client

    def set_broker_client(self, client: BrokerClient) -> None:
        self._broker_client = client

    def register(self, agent: SpecialistAgent):
        return self.registry.register(agent)

    def list_agents(self):
        return self.registry.list_agents()

    def list_capabilities(self):
        return self.registry.list_capabilities()

    def run(self, task: AgentTask | dict[str, Any]) -> AgentResult:
        lifecycle: list[str] = ["TASK_RECEIVED"]

        # --- validate task ---
        # Preserve non-serializable cancel tokens (must not round-trip via model_dump).
        cancel_token = None
        try:
            if isinstance(task, dict):
                inputs = dict(task.get("inputs") or {})
                cancel_token = inputs.pop("cancel_token", None)
                task = dict(task)
                task["inputs"] = inputs
                task = AgentTask.model_validate(task)
            elif isinstance(task, AgentTask):
                inputs = dict(task.inputs or {})
                cancel_token = inputs.pop("cancel_token", None)
                if cancel_token is not None:
                    task = task.model_copy(update={"inputs": inputs})
            else:
                raise InvalidTaskError("task must be AgentTask or dict")
        except (ValidationError, InvalidTaskError, ValueError) as exc:
            lifecycle.append("REJECTED")
            return AgentResult(
                agent_id=getattr(task, "agent_id", None) or "unknown",
                task_id=getattr(task, "task_id", None) or "unknown",
                project_id=getattr(task, "project_id", None) or "unknown",
                status=ExecutionStatus.REJECTED,
                summary="Invalid task",
                errors=[str(exc)],
                lifecycle=lifecycle,
            )

        if not task.agent_id and not task.capability:
            lifecycle.append("REJECTED")
            return AgentResult(
                agent_id="unknown",
                task_id=task.task_id,
                project_id=task.project_id,
                status=ExecutionStatus.REJECTED,
                summary="Invalid task: agent_id or capability required",
                errors=["agent_id or capability required"],
                lifecycle=lifecycle,
                correlation_id=task.correlation_id,
            )

        # Guard: agent-supplied project_context cannot override task.project_id
        ctx_pid = task.project_context.get("project_id") or task.project_context.get("id")
        if ctx_pid and str(ctx_pid) != task.project_id:
            lifecycle.append("REJECTED")
            return AgentResult(
                agent_id=task.agent_id or task.capability or "unknown",
                task_id=task.task_id,
                project_id=task.project_id,
                status=ExecutionStatus.REJECTED,
                summary="Project context identity mismatch",
                errors=[
                    f"project_context id {ctx_pid!r} does not match task.project_id "
                    f"{task.project_id!r}"
                ],
                lifecycle=lifecycle,
                correlation_id=task.correlation_id,
            )

        lifecycle.append("TASK_VALIDATED")

        # --- resolve agent ---
        try:
            agent = self.registry.resolve(agent_id=task.agent_id, capability=task.capability)
        except UnknownAgentError as exc:
            lifecycle.append("FAILED")
            return AgentResult(
                agent_id=task.agent_id or task.capability or "unknown",
                task_id=task.task_id,
                project_id=task.project_id,
                status=ExecutionStatus.FAILED,
                summary="Unknown agent",
                errors=[str(exc)],
                lifecycle=lifecycle,
                correlation_id=task.correlation_id,
            )

        manifest = agent.manifest()
        lifecycle.append("AGENT_RESOLVED")

        if self._broker_client is None:
            lifecycle.append("BLOCKED")
            return AgentResult(
                agent_id=manifest.agent_id,
                task_id=task.task_id,
                project_id=task.project_id,
                status=ExecutionStatus.BLOCKED,
                summary="BrokerClient not configured",
                errors=["Agent Runtime has no BrokerClient"],
                lifecycle=lifecycle,
                correlation_id=task.correlation_id,
            )

        # --- prepare context ---
        timeout_s = float(task.timeout_s if task.timeout_s is not None else manifest.timeout_s)
        max_level = _cap_level(
            _cap_level(manifest.max_level, task.max_level),
            self.PHASE_MAX_LEVEL,
        )
        allowed_tools = list(manifest.allowed_tools)
        if task.allowed_capabilities:
            # Optional further restriction from Master
            allowed_tools = [t for t in allowed_tools if t in task.allowed_capabilities]

        session = AgentBrokerSession(
            self._broker_client,
            agent_id=manifest.agent_id,
            project_id=task.project_id,
            allowed_tools=allowed_tools,
            max_level=max_level,
            call_timeout_s=min(timeout_s, 15.0),
        )
        # Bound context: only pass keys Master provided; never full Project OS dump.
        bounded = dict(task.project_context or {})
        bounded["project_id"] = task.project_id

        exec_ctx = ExecutionContext(
            project_id=task.project_id,
            task_id=task.task_id,
            agent_id=manifest.agent_id,
            project_context=bounded,
            allowed_tools=allowed_tools,
            max_level=max_level,
            timeout_s=timeout_s,
            correlation_id=task.correlation_id,
            broker=session,
            deadline_monotonic=time.monotonic() + timeout_s,
            cancel_token=cancel_token,
        )
        lifecycle.append("CONTEXT_PREPARED")
        lifecycle.append("EXECUTING")

        # --- execute with timeout ---
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(agent.run, task, exec_ctx)
                raw = fut.result(timeout=timeout_s)
        except concurrent.futures.TimeoutError:
            lifecycle.append("FAILED")
            return AgentResult(
                agent_id=manifest.agent_id,
                task_id=task.task_id,
                project_id=task.project_id,
                status=ExecutionStatus.FAILED,
                summary="Agent execution timed out",
                errors=[f"timeout after {timeout_s}s"],
                evidence=[{"broker_calls": list(session.calls)}],
                lifecycle=lifecycle,
                correlation_id=task.correlation_id,
            )
        except BrokerAccessDenied as exc:
            lifecycle.append("BLOCKED")
            return AgentResult(
                agent_id=manifest.agent_id,
                task_id=task.task_id,
                project_id=task.project_id,
                status=ExecutionStatus.BLOCKED,
                summary="Broker access denied",
                errors=[str(exc)],
                evidence=[{"broker_calls": list(session.calls)}],
                lifecycle=lifecycle,
                correlation_id=task.correlation_id,
            )
        except Exception as exc:
            log.exception("agent %s failed", manifest.agent_id)
            lifecycle.append("FAILED")
            return AgentResult(
                agent_id=manifest.agent_id,
                task_id=task.task_id,
                project_id=task.project_id,
                status=ExecutionStatus.FAILED,
                summary="Agent exception",
                errors=[f"{type(exc).__name__}: {exc}"],
                evidence=[{"broker_calls": list(session.calls)}],
                lifecycle=lifecycle,
                correlation_id=task.correlation_id,
            )

        # --- validate result ---
        try:
            result = self._validate_result(raw, task=task, agent_id=manifest.agent_id)
        except InvalidResultError as exc:
            lifecycle.append("FAILED")
            return AgentResult(
                agent_id=manifest.agent_id,
                task_id=task.task_id,
                project_id=task.project_id,
                status=ExecutionStatus.FAILED,
                summary="Invalid agent result",
                errors=[str(exc)],
                evidence=[{"broker_calls": list(session.calls)}],
                lifecycle=lifecycle,
                correlation_id=task.correlation_id,
            )

        # Attach broker evidence if agent omitted it
        if session.calls:
            result.evidence = list(result.evidence) + [{"broker_calls": list(session.calls)}]

        result.lifecycle = lifecycle + ["RESULT_VALIDATED", result.status.value]
        if result.correlation_id is None:
            result.correlation_id = task.correlation_id

        # Identity freeze check
        if result.project_id != task.project_id:
            result.status = ExecutionStatus.FAILED
            result.errors = list(result.errors) + [
                f"result project_id {result.project_id!r} != task {task.project_id!r}"
            ]
            result.summary = "Project identity mismatch in result"
            result.lifecycle = lifecycle + ["RESULT_VALIDATED", "FAILED"]

        return result

    def _validate_result(
        self,
        raw: Any,
        *,
        task: AgentTask,
        agent_id: str,
    ) -> AgentResult:
        if isinstance(raw, AgentResult):
            data = raw.model_dump()
        elif isinstance(raw, dict):
            data = raw
        else:
            raise InvalidResultError("agent must return AgentResult or dict")

        try:
            result = AgentResult.model_validate(data)
        except ValidationError as exc:
            raise InvalidResultError(str(exc)) from exc

        if result.agent_id != agent_id:
            raise InvalidResultError(
                f"result.agent_id {result.agent_id!r} != {agent_id!r}"
            )
        if result.task_id != task.task_id:
            raise InvalidResultError(
                f"result.task_id {result.task_id!r} != {task.task_id!r}"
            )
        if result.status == ExecutionStatus.PENDING or result.status == ExecutionStatus.RUNNING:
            raise InvalidResultError(
                f"terminal result cannot have status {result.status.value}"
            )
        return result
