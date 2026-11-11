"""Shared Research Agent test helpers."""

from __future__ import annotations

from pydantic_ai.models.test import TestModel

from agent_runtime.research_models import ResearchReport


def sample_report(**overrides) -> dict:
    base = {
        "summary": "Polling checks the UART periodically; interrupts react to RX events.",
        "findings": [
            "Polling is simpler to implement",
            "Interrupts reduce latency and CPU waste when idle",
        ],
        "assumptions": ["A UART peripheral is available"],
        "unknowns": [],
        "recommendations": ["Prefer interrupts for low-power designs"],
        "confidence": "high",
        "requires_human_review": False,
    }
    base.update(overrides)
    ResearchReport.model_validate(base)
    return base


def make_test_model(report: dict | None = None, *, call_tools: list | str | None = None) -> TestModel:
    args = report if report is not None else sample_report()
    ct = [] if call_tools is None else call_tools
    return TestModel(call_tools=ct, custom_output_args=args)
