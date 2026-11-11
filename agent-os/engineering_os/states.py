"""Engineering operation states (Phase 6)."""

from __future__ import annotations

# Workflow / operation outcomes — never imply hardware verification from build alone.
PLANNED = "planned"
RUNNING = "running"
BLOCKED = "blocked"
FAILED = "failed"
BUILT = "built"
WAITING_APPROVAL = "waiting_approval"
# verified: only when actual verification evidence exists (not used for compile-only).
VERIFIED = "verified"

ALLOWED_STATUSES = {
    PLANNED,
    RUNNING,
    BLOCKED,
    FAILED,
    BUILT,
    WAITING_APPROVAL,
    VERIFIED,
}
