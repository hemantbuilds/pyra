"""Master handlers that delegate to Agent Runtime (Phase 5b)."""

from __future__ import annotations

import re
import uuid
from typing import Any, Optional

from agent_runtime.contracts import AgentResult, AgentTask, ExecutionStatus
from agent_runtime.service import get_agent_runtime

from .capabilities import CapabilityResult
from .contracts import Intent, IntentKind, InteractRequest


def _active_project() -> Optional[dict[str, Any]]:
    from .project_service import get_project_os

    return get_project_os().active_project()


def _bounded_context(proj: dict[str, Any]) -> dict[str, Any]:
    """Minimal Project OS slice — not full memory dump."""
    return {
        "project_id": proj["id"],
        "name": proj.get("name"),
        "slug": proj.get("slug"),
        "status": proj.get("status"),
        "workspace_path": proj.get("workspace_path"),
        "description": (proj.get("description") or "")[:500],
    }


def _parse_agent_id(text: str) -> Optional[str]:
    t = text.strip()
    # "run echo agent" / "run the broker_probe agent" / "run agent echo"
    m = re.search(
        r"(?i)\brun\s+(?:the\s+)?(?:agent\s+)?([a-z][a-z0-9_]*)\s+agent\b",
        t,
    )
    if m:
        return m.group(1).lower()
    m = re.search(r"(?i)\brun\s+agent\s+([a-z][a-z0-9_]*)\b", t)
    if m:
        return m.group(1).lower()
    m = re.search(r"(?i)\b(?:invoke|execute)\s+agent\s+([a-z][a-z0-9_]*)\b", t)
    if m:
        return m.group(1).lower()
    # "run broker probe" / "run broker_probe"
    if re.search(r"(?i)\bbroker[_\s-]?probe\b", t):
        return "broker_probe"
    if re.search(r"(?i)\becho\s+agent\b|\brun\s+echo\b", t):
        return "echo"
    if re.search(r"(?i)\bresearch(\s+agent)?\b|\bask research\b", t):
        return "research"
    return None


def handle_agent(req: InteractRequest, intent: Intent) -> CapabilityResult:
    runtime = get_agent_runtime()

    if intent.kind == IntentKind.AGENT_LIST:
        agents = runtime.list_agents()
        if not agents:
            return CapabilityResult(
                speech="No agents are registered in the Agent Runtime yet.",
                capability="agent_runtime",
                evidence={"agents": []},
            )
        lines = [
            f"- {m.agent_id}: {m.name} — {m.description} "
            f"(tools={m.allowed_tools or 'none'}, max={m.max_level})"
            for m in agents
        ]
        body = "\n".join(lines)
        names = ", ".join(m.agent_id for m in agents)
        return CapabilityResult(
            speech=f"Registered agents: {names}.",
            capability="agent_runtime",
            hud={"title": "Agent Runtime", "body": body},
            evidence={
                "agents": [m.model_dump() for m in agents],
                "capabilities": runtime.list_capabilities(),
            },
        )

    # AGENT_RUN
    proj = _active_project()
    if proj is None:
        return CapabilityResult(
            speech="No active project. Create or switch to a project before running an agent.",
            capability="agent_runtime",
            status="error",
            evidence={"blocked": "no_active_project"},
        )

    agent_id = _parse_agent_id(req.text) or (
        intent.agent_hints[0] if intent.agent_hints else None
    )
    if not agent_id:
        return CapabilityResult(
            speech="Say which agent to run, for example: run echo agent, run broker probe agent, or run research agent.",
            capability="agent_runtime",
            status="error",
            evidence={"blocked": "missing_agent_id"},
        )

    task = AgentTask(
        task_id=f"task_{uuid.uuid4().hex[:12]}",
        project_id=proj["id"],
        requesting_component="master",
        agent_id=agent_id,
        description=req.text.strip(),
        inputs={},
        project_context=_bounded_context(proj),
        correlation_id=req.session_id,
        max_level="L1",
    )
    result: AgentResult = runtime.run(task)
    return _result_to_capability(result)


def _result_to_capability(result: AgentResult) -> CapabilityResult:
    status_map = {
        ExecutionStatus.COMPLETED: "ok",
        ExecutionStatus.FAILED: "error",
        ExecutionStatus.BLOCKED: "error",
        ExecutionStatus.CANCELLED: "error",
        ExecutionStatus.REJECTED: "error",
        ExecutionStatus.PENDING: "degraded",
        ExecutionStatus.RUNNING: "degraded",
    }
    speech = result.summary or f"Agent {result.agent_id} finished with {result.status.value}"
    if result.errors:
        speech = f"{speech} ({'; '.join(result.errors[:2])})"
    return CapabilityResult(
        speech=speech,
        capability="agent_runtime",
        project_id=result.project_id,
        status=status_map.get(result.status, "error"),
        evidence={
            "agent_result": result.model_dump(mode="json"),
            "agent_id": result.agent_id,
            "task_id": result.task_id,
            "execution_status": result.status.value,
            "lifecycle": result.lifecycle,
        },
    )
