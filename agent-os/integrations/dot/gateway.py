"""
Dot gateway.

Mark (or CLI) → Dot → Master Orchestrator.

Phase 1: in-process router (same FastAPI app) to conserve Pi RAM.
The module boundary stays clear so Dot can become a separate process later.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from master.contracts import InteractRequest, InteractResponse

if TYPE_CHECKING:
    from master.orchestrator import Orchestrator


class DotGateway:
    def __init__(self, orchestrator: Orchestrator):
        self.orchestrator = orchestrator

    def route(self, req: InteractRequest) -> InteractResponse:
        # Normalize: anything entering via Dot is tagged for audit.
        data = req.model_dump()
        meta = dict(data.get("metadata") or {})
        meta["routed_by"] = "dot"
        data["metadata"] = meta
        if data.get("source") == "mark":
            pass
        elif data.get("source") in (None, "", "dot"):
            data["source"] = "dot"
        forwarded = InteractRequest(**data)
        return self.orchestrator.handle(forwarded)
