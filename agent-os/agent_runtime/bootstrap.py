"""Register built-in Phase 5b–7 specialist agents."""

from __future__ import annotations

from .agents import (
    ArchitectureAgent,
    BrokerProbeAgent,
    DocumentationAgent,
    EchoAgent,
    FirmwareEngAgent,
    HardwareEngAgent,
    PlanningAgent,
    RequirementsAgent,
    ResearchAgent,
    VerificationAgent,
)
from .runtime import AgentRuntime

_BOOTSTRAPPED = False

_PHASE7_AGENTS = (
    ("planning", PlanningAgent),
    ("requirements", RequirementsAgent),
    ("architecture", ArchitectureAgent),
    ("hardware_eng", HardwareEngAgent),
    ("firmware_eng", FirmwareEngAgent),
    ("verification", VerificationAgent),
    ("documentation", DocumentationAgent),
)


def bootstrap_builtin_agents(runtime: AgentRuntime) -> None:
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    # Idempotent even if registry was cleared then re-bootstrapped via reset
    existing = {m.agent_id for m in runtime.list_agents()}
    if "echo" not in existing:
        runtime.register(EchoAgent())
    if "broker_probe" not in existing:
        runtime.register(BrokerProbeAgent())
    from .service import get_specialist_gateway

    gw = get_specialist_gateway()
    if "research" not in existing:
        runtime.register(ResearchAgent(gateway=gw))
    for agent_id, cls in _PHASE7_AGENTS:
        if agent_id not in existing:
            runtime.register(cls(gateway=gw))
    _BOOTSTRAPPED = True


def reset_bootstrap_flag() -> None:
    global _BOOTSTRAPPED
    _BOOTSTRAPPED = False
