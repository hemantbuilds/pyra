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

        # Phase 7 — resume pending L3 programming approval before reclassification
        from .engineering_workflow import handle_approval_utterance

        approval_result = handle_approval_utterance(text, project_id=req.project_id)
        if approval_result is not None:
            intent = Intent(kind=IntentKind.ENGINEERING_WORKFLOW, confidence=1.0, notes="approval_resume")
            return InteractResponse(
                speech=approval_result.speech,
                intent=intent,
                project_id=approval_result.project_id or req.project_id,
                capability=approval_result.capability,
                hud=approval_result.hud,
                needs_confirm=approval_result.needs_confirm,
                status=approval_result.status,
                evidence={
                    **approval_result.evidence,
                    "intent_backend": "approval_resume",
                    "source": req.source,
                    "via": "dot" if req.source in ("mark", "dot") else req.source,
                },
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
            needs_confirm=result.needs_confirm,
            status=result.status,
            evidence={
                **result.evidence,
                "intent_backend": backend,
                "source": req.source,
                "via": "dot" if req.source in ("mark", "dot") else req.source,
            },
        )
