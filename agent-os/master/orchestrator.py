"""Minimal orchestration: classify → resolve capability → execute → respond."""

from __future__ import annotations

import logging

from . import capabilities
from .contracts import Intent, IntentKind, InteractRequest, InteractResponse
from .model_gateway import ModelGateway

log = logging.getLogger("pyra.master.orch")


class Orchestrator:
    def __init__(self, gateway: ModelGateway | None = None):
        self.gateway = gateway or ModelGateway()
        capabilities.bootstrap_builtin_capabilities()

    def handle(self, req: InteractRequest) -> InteractResponse:
        capabilities.bootstrap_builtin_capabilities()
        text = (req.text or "").strip()
        if not text:
            return InteractResponse(
                speech="I did not receive a command.",
                intent=Intent(kind=IntentKind.UNKNOWN),
                status="error",
            )

        intent, backend = self.gateway.classify_intent(text)
        log.info(
            "intent=%s backend=%s conf=%.2f text=%r",
            intent.kind.value,
            backend,
            intent.confidence,
            text[:120],
        )

        cap = capabilities.resolve(intent)
        if cap is None:
            result = capabilities._cap_general(req, intent)
        else:
            result = cap.handler(req, intent)

        return InteractResponse(
            speech=result.speech,
            intent=intent,
            project_id=result.project_id or req.project_id,
            capability=result.capability,
            hud=result.hud,
            needs_confirm=None,
            status=result.status,
            evidence={
                **result.evidence,
                "intent_backend": backend,
                "source": req.source,
                "via": "dot" if req.source in ("mark", "dot") else req.source,
            },
        )
