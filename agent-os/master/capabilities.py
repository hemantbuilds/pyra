"""Capability registry — Master routes intents to named capabilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from .contracts import Intent, IntentKind, InteractRequest


@dataclass
class CapabilityResult:
    speech: str
    capability: str
    project_id: Optional[str] = None
    hud: Optional[dict[str, str]] = None
    evidence: dict = field(default_factory=dict)
    status: str = "ok"


CapabilityHandler = Callable[[InteractRequest, Intent], CapabilityResult]


@dataclass
class Capability:
    name: str
    description: str
    intents: set[IntentKind]
    handler: CapabilityHandler
    available: bool = True
    phase: str = "1"


_REGISTRY: dict[str, Capability] = {}
_BOOTSTRAPPED = False


def register(cap: Capability) -> None:
    _REGISTRY[cap.name] = cap


def reset_registry() -> None:
    global _BOOTSTRAPPED
    _REGISTRY.clear()
    _BOOTSTRAPPED = False


def list_capabilities() -> list[dict]:
    return [
        {
            "name": c.name,
            "description": c.description,
            "intents": sorted(i.value for i in c.intents),
            "available": c.available,
            "phase": c.phase,
        }
        for c in _REGISTRY.values()
    ]


def resolve(intent: Intent) -> Optional[Capability]:
    for cap in _REGISTRY.values():
        if intent.kind in cap.intents and cap.available:
            return cap
    return None


def _cap_status(req: InteractRequest, intent: Intent) -> CapabilityResult:
    from .project_service import get_project_os

    caps = list_capabilities()
    names = ", ".join(c["name"] for c in caps) or "none"
    active = None
    try:
        active = get_project_os().active_project()
    except Exception:
        active = None
    active_bit = f" Active project: {active['name']}." if active else " No active project."
    return CapabilityResult(
        speech=f"PYRA Master is online. Registered capabilities: {names}.{active_bit}",
        capability="system_status",
        project_id=active["id"] if active else None,
        evidence={"capabilities": caps, "active_project": active},
    )


def _cap_capabilities(req: InteractRequest, intent: Intent) -> CapabilityResult:
    caps = list_capabilities()
    lines = [f"- {c['name']}: {c['description']} (phase {c['phase']})" for c in caps]
    body = "\n".join(lines)
    return CapabilityResult(
        speech="I can manage projects, run Device Broker tools, and run Engineering OS "
               "hardware discovery (USB/serial/probes). Flashing and full bring-up are not enabled yet.",
        capability="capability_query",
        hud={"title": "PYRA capabilities", "body": body},
        evidence={"capabilities": caps},
    )


def _cap_greeting(req: InteractRequest, intent: Intent) -> CapabilityResult:
    return CapabilityResult(
        speech="PYRA Master ready. Create or switch projects, inspect the workspace, "
               "or ask me to discover connected hardware. I will not flash devices without later-phase approval.",
        capability="greeting",
    )


def _cap_general(req: InteractRequest, intent: Intent) -> CapabilityResult:
    return CapabilityResult(
        speech="Understood. I can manage projects, tasks, notes, checkpoints, "
               "Device Broker workspace/host tools, and report status. "
               "Say what you want to do next.",
        capability="general",
        evidence={"intent_notes": intent.notes},
    )


def bootstrap_builtin_capabilities() -> None:
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    _BOOTSTRAPPED = True

    from . import project_handlers

    register(Capability(
        name="system_status",
        description="Report Master health and registered capabilities",
        intents={IntentKind.STATUS},
        handler=_cap_status,
        phase="1",
    ))
    register(Capability(
        name="capability_query",
        description="Explain what PYRA can do right now",
        intents={IntentKind.CAPABILITY_QUERY},
        handler=_cap_capabilities,
        phase="1",
    ))
    register(Capability(
        name="greeting",
        description="Acknowledge wake / hello",
        intents={IntentKind.GREETING},
        handler=_cap_greeting,
        phase="1",
    ))
    register(Capability(
        name="project_os",
        description="Persistent multi-project management",
        intents={
            IntentKind.PROJECT_LIST,
            IntentKind.PROJECT_CREATE,
            IntentKind.PROJECT_SWITCH,
            IntentKind.PROJECT_CONTINUE,
            IntentKind.PROJECT_STATUS,
            IntentKind.PROJECT_NOTE,
            IntentKind.PROJECT_DECISION,
            IntentKind.PROJECT_ARCHIVE,
            IntentKind.TASK_CREATE,
            IntentKind.TASK_LIST,
            IntentKind.TASK_UPDATE,
            IntentKind.CHECKPOINT_CREATE,
            IntentKind.CHECKPOINT_RESTORE,
        },
        handler=project_handlers.handle_project,
        available=True,
        phase="2",
    ))
    from . import broker_handlers

    register(Capability(
        name="device_broker",
        description="Controlled host/workspace tools via Device Broker (L0/L1)",
        intents={
            IntentKind.DEVICE_LIST_DIR,
            IntentKind.DEVICE_READ_FILE,
            IntentKind.DEVICE_WRITE_FILE,
            IntentKind.DEVICE_CREATE_DIR,
            IntentKind.DEVICE_FILE_INFO,
            IntentKind.DEVICE_SYSTEM_INFO,
            IntentKind.DEVICE_TOOLCHAINS,
            IntentKind.DEVICE_RUN_COMMAND,
            IntentKind.DEVICE_LIST_TOOLS,
            IntentKind.DEVICE_AUDIT,
        },
        handler=broker_handlers.handle_device,
        available=True,
        phase="3",
    ))
    from . import engineering_handlers

    register(Capability(
        name="engineering_os",
        description="Engineering OS — hardware discovery and identification (Phase 4)",
        intents={
            IntentKind.HARDWARE_DISCOVERY,
            IntentKind.HARDWARE_BRINGUP,  # maps to discovery-only until later phases
        },
        handler=engineering_handlers.handle_engineering,
        available=True,
        phase="4",
    ))
    register(Capability(
        name="general",
        description="Fallback conversational routing",
        intents={IntentKind.GENERAL, IntentKind.UNKNOWN},
        handler=_cap_general,
        phase="1",
    ))
