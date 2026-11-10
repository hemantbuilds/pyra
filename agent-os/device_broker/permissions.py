"""Permission levels — enforced by Broker, never by the model."""

from __future__ import annotations

from enum import IntEnum


class PermissionLevel(IntEnum):
    L0 = 0  # read-only discovery
    L1 = 1  # controlled workspace ops / allowlisted commands
    L2 = 2  # reserved — human approve (not granted in Phase 3)
    L3 = 3  # reserved — destructive / hardware (not granted in Phase 3)

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


# Phase 3 hard ceiling — Broker refuses anything above this regardless of caller claims.
PHASE3_MAX_GRANTABLE = PermissionLevel.L1


def level_allowed(required: PermissionLevel, max_level: PermissionLevel) -> bool:
    if required > PHASE3_MAX_GRANTABLE:
        return False
    return int(max_level) >= int(required)
