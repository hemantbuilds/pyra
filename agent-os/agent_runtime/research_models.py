"""Structured Research Agent output (Phase 5c)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


_MAX_ITEM = 500
_MAX_LIST = 12


def _trim_list(items: list[str], *, limit: int = _MAX_LIST) -> list[str]:
    out: list[str] = []
    for raw in items[:limit]:
        s = str(raw).strip()
        if not s:
            continue
        out.append(s[:_MAX_ITEM])
    return out


class ResearchReport(BaseModel):
    """Validated structured research deliverable."""

    summary: str = Field(..., min_length=1, max_length=2000)
    findings: list[str] = Field(default_factory=list, max_length=_MAX_LIST)
    assumptions: list[str] = Field(default_factory=list, max_length=_MAX_LIST)
    unknowns: list[str] = Field(default_factory=list, max_length=_MAX_LIST)
    recommendations: list[str] = Field(default_factory=list, max_length=_MAX_LIST)
    confidence: Literal["low", "medium", "high"] = "medium"
    requires_human_review: bool = False

    @field_validator("summary")
    @classmethod
    def _summary_nonblank(cls, v: str) -> str:
        s = (v or "").strip()
        if not s:
            raise ValueError("summary must be non-empty")
        return s[:2000]

    @field_validator("findings", "assumptions", "unknowns", "recommendations", mode="before")
    @classmethod
    def _normalize_lists(cls, v):
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError("must be a list of strings")
        return _trim_list([str(x) for x in v])
