"""Permission levels — enforced by Broker, never by the model."""

from __future__ import annotations

from enum import IntEnum
from typing import FrozenSet


class PermissionLevel(IntEnum):
    L0 = 0  # read-only discovery
    L1 = 1  # controlled workspace ops / allowlisted commands
    L2 = 2  # controlled build / passive serial (Phase 6)
    L3 = 3  # reserved — flash / erase / persistent config (Phase 7+)

    @classmethod
    def parse(cls, value: str | int | "PermissionLevel") -> "PermissionLevel":
        if isinstance(value, PermissionLevel):
            return value
        if isinstance(value, int):
            return cls(value)
        text = str(value).strip().upper()
        if text.startswith("L") and text[1:].isdigit():
            return cls(int(text[1:]))
        if text.isdigit():
            return cls(int(text))
        raise ValueError(f"invalid permission level: {value!r}")

    def label(self) -> str:
        return f"L{int(self)}"


# Phase 7 ceiling — L3 tools exist but require session grant + Broker-minted approval.
MAX_GRANTABLE = PermissionLevel.L3

# Backward-compatible alias used by Phase 3–5 code/tests.
PHASE3_MAX_GRANTABLE = MAX_GRANTABLE

# Phase 6.1 — explicit Engineering OS L2 tool allowlist (not all future L2 tools).
ENGINEERING_OS_L2_TOOLS: FrozenSet[str] = frozenset(
    {
        "west_build",
        "serial_capture_passive",
    }
)

# Phase 7 — Engineering OS L3 tools (still require operation-bound approval).
ENGINEERING_OS_L3_TOOLS: FrozenSet[str] = frozenset(
    {
        "program_firmware",
        "erase_flash",
    }
)

# Trusted Engineering OS principal name (informational; trust is session-based).
ENGINEERING_OS_PRINCIPAL = "engineering_os"


def level_allowed(required: PermissionLevel, max_level: PermissionLevel) -> bool:
    if required > MAX_GRANTABLE:
        return False
    return int(max_level) >= int(required)
