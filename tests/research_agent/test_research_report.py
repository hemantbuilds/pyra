"""ResearchReport schema validation tests."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from agent_runtime.research_models import ResearchReport


def test_valid_report_accepted():
    r = ResearchReport(
        summary="A solid summary.",
        findings=["a"],
        assumptions=["b"],
        unknowns=["c"],
        recommendations=["d"],
        confidence="medium",
        requires_human_review=False,
    )
    assert r.summary.startswith("A solid")


def test_missing_summary_rejected():
    with pytest.raises(ValidationError):
        ResearchReport(findings=["x"])


def test_empty_summary_rejected():
    with pytest.raises(ValidationError):
        ResearchReport(summary="   ")


def test_invalid_confidence_rejected():
    with pytest.raises(ValidationError):
        ResearchReport(summary="ok", confidence="extreme")


def test_oversized_summary_rejected():
    with pytest.raises(ValidationError):
        ResearchReport(summary="x" * 2001)


def test_list_items_trimmed():
    r = ResearchReport(summary="ok", findings=["  a  ", "", "b" * 600])
    assert r.findings[0] == "a"
    assert len(r.findings[1]) == 500


def test_invalid_type_rejected():
    with pytest.raises(ValidationError):
        ResearchReport(summary="ok", findings="not-a-list")


def test_json_round_trip():
    r = ResearchReport(
        summary="round trip",
        findings=["one"],
        confidence="low",
        requires_human_review=True,
    )
    data = json.loads(r.model_dump_json())
    r2 = ResearchReport.model_validate(data)
    assert r2 == r


def test_extra_fields_ignored_by_default():
    # Pydantic v2 default ignore
    r = ResearchReport.model_validate(
        {"summary": "ok", "confidence": "high", "secret_key": "should-not-appear"}
    )
    dumped = r.model_dump()
    assert "secret_key" not in dumped
