"""Model capability profiles — verified behaviour only (Phase 5d.1)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from .invocation import QualificationStatus


@dataclass
class ModelCapabilityProfile:
    """Capability-specific qualification record for one model/provider."""

    provider: str
    model_id: str
    basic_inference: QualificationStatus = QualificationStatus.NOT_TESTED
    structured_json: QualificationStatus = QualificationStatus.NOT_TESTED
    json_schema_output: QualificationStatus = QualificationStatus.NOT_TESTED
    pydantic_schema_reliability: QualificationStatus = QualificationStatus.NOT_TESTED
    tool_calling: QualificationStatus = QualificationStatus.NOT_TESTED
    multimodal: QualificationStatus = QualificationStatus.NOT_TESTED
    context_limit_notes: str = ""
    measured_latency: dict[str, Any] = field(default_factory=dict)
    known_restrictions: list[str] = field(default_factory=list)
    sample_counts: dict[str, int] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k, v in list(d.items()):
            if isinstance(v, QualificationStatus):
                d[k] = v.value
        return d


# Seeded from Phase 5d + updated by 5d.1 qualification runs.
# Values below are placeholders until benchmarks rewrite them; loaders may overwrite.
# Profiles below reflect Phase 5d.1 measured behaviour (see phase5d1_benchmark_raw.json).
# Structured qualification applies to the simple StrictQualOut schema used in 5d.1,
# not to complex ResearchReport + tool-use workflows.
_PROFILES: dict[str, ModelCapabilityProfile] = {
    "ollama:qwen2.5:3b": ModelCapabilityProfile(
        provider="ollama",
        model_id="qwen2.5:3b",
        basic_inference=QualificationStatus.QUALIFIED,
        structured_json=QualificationStatus.QUALIFIED_WITH_RESTRICTIONS,
        json_schema_output=QualificationStatus.QUALIFIED_WITH_RESTRICTIONS,
        pydantic_schema_reliability=QualificationStatus.QUALIFIED_WITH_RESTRICTIONS,
        tool_calling=QualificationStatus.NOT_QUALIFIED,
        multimodal=QualificationStatus.NOT_TESTED,
        context_limit_notes="Small local model; keep prompts short on Pi.",
        measured_latency={
            "basic_median_s": 5.815,
            "basic_min_s": 5.256,
            "basic_max_s": 6.015,
            "tokens_per_s_samples": [3.09, 3.25, 3.68, 3.66, 3.42],
        },
        sample_counts={"basic": 5, "native_json": 10, "json_schema": 10, "pydantic": 10, "tool": 5},
        known_restrictions=[
            "Simple 3-field schema qualified (n=10); ResearchReport+tools not qualified live.",
            "Live tool-calling: model often skips Broker tools and may claim tool results.",
            "Cold-start / load can raise latency substantially vs warm median.",
        ],
        notes="Phase 5d.1; exploratory sample sizes — not a production SLA.",
    ),
    "ollama:gemma3:1b": ModelCapabilityProfile(
        provider="ollama",
        model_id="gemma3:1b",
        basic_inference=QualificationStatus.QUALIFIED_WITH_RESTRICTIONS,
        structured_json=QualificationStatus.QUALIFIED_WITH_RESTRICTIONS,
        json_schema_output=QualificationStatus.QUALIFIED_WITH_RESTRICTIONS,
        pydantic_schema_reliability=QualificationStatus.QUALIFIED_WITH_RESTRICTIONS,
        tool_calling=QualificationStatus.NOT_TESTED,
        multimodal=QualificationStatus.NOT_TESTED,
        context_limit_notes="Very small model; keep prompts and schemas minimal.",
        measured_latency={
            "basic_median_s": 3.283,
            "basic_min_s": 3.214,
            "basic_max_s": 47.887,
            "tokens_per_s_samples": [8.65, 8.52, 8.52, 8.38, 8.29],
        },
        sample_counts={"basic": 5, "native_json": 10, "json_schema": 10, "pydantic": 10},
        known_restrictions=[
            "Warm simple-schema structured output passed n=10; complex schemas historically fail (5d).",
            "Basic latency max≃48s observed (cold/load); median ~3.3s warm.",
            "Tool calling not live-tested for gemma in 5d.1.",
        ],
        notes="Phase 5d.1; exploratory sample sizes — not a production SLA.",
    ),
}


def profile_key(provider: str, model_id: str) -> str:
    return f"{provider}:{model_id}"


def get_profile(provider: str, model_id: str) -> Optional[ModelCapabilityProfile]:
    return _PROFILES.get(profile_key(provider, model_id))


def upsert_profile(profile: ModelCapabilityProfile) -> ModelCapabilityProfile:
    _PROFILES[profile_key(profile.provider, profile.model_id)] = profile
    return profile


def all_profiles() -> list[ModelCapabilityProfile]:
    return list(_PROFILES.values())


def profiles_public() -> list[dict[str, Any]]:
    return [p.to_dict() for p in all_profiles()]
