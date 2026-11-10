"""Allowlisted command execution (no shell)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..permissions import PermissionLevel
from .registry import ToolRegistry, ToolSpec

if TYPE_CHECKING:
    from ..broker import DeviceBroker


def register(reg: ToolRegistry, broker: "DeviceBroker") -> None:
    reg.register(ToolSpec(
        name="run_allowed_command",
        description=(
            "Run an explicitly allowlisted command with argv validation "
            "(Level 1 unless the command is marked L0). No shell."
        ),
        level=PermissionLevel.L1,
        category="exec",
        handler=lambda **kw: run_allowed_command(broker, **kw),
        input_schema={
            "type": "object",
            "properties": {
                "argv": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Argument vector, e.g. [\"python3\", \"--version\"]",
                },
                "cwd": {
                    "type": "string",
                    "description": "Optional working directory inside approved roots",
                },
            },
            "required": ["argv"],
        },
    ))


def run_allowed_command(
    broker: "DeviceBroker",
    *,
    argv: list[str],
    cwd: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    if not isinstance(argv, list) or not all(isinstance(a, str) for a in argv):
        raise ValueError("argv must be a list of strings")
    return broker._run_command_impl(argv, cwd=cwd)  # noqa: SLF001
