#!/usr/bin/env python3
"""Phase 5d.1 repeated ModelGateway qualification benchmarks (no model downloads)."""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# Ensure agent-os on path
ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "agent-os"))

from master.config import Settings
from master.invocation import CancellationToken, FailureKind, QualificationStatus
from master.model_gateway import ModelGateway
from master.model_profiles import ModelCapabilityProfile, upsert_profile

OUT = ROOT / "docs" / "implementation" / "phase5d1_benchmark_raw.json"

TEXT_PROMPT = "In one short sentence, explain what SPI is used for in embedded systems."
JSON_SYSTEM = (
    "Reply with ONLY a JSON object. No markdown. Schema: "
    '{"summary": string, "confidence": "low"|"medium"|"high", "score": integer}'
)
JSON_PROMPT = "Summarise SPI in the required JSON schema."
JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "score": {"type": "integer"},
    },
    "required": ["summary", "confidence", "score"],
}


class StrictQualOut(BaseModel):
    summary: str = Field(..., min_length=1)
    confidence: Literal["low", "medium", "high"]
    score: int


def _rss_kb(pid: int) -> Optional[int]:
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except Exception:
        return None
    return None


def _ollama_pid() -> Optional[int]:
    try:
        out = subprocess.check_output(["pgrep", "-x", "ollama"], text=True).strip()
        return int(out.splitlines()[0])
    except Exception:
        return None


def _self_rss() -> Optional[int]:
    return _rss_kb(os.getpid())


def _summarize(latencies: list[float], oks: int, fails: int, errors: list[str]) -> dict[str, Any]:
    return {
        "n": oks + fails,
        "success": oks,
        "failed": fails,
        "median_latency_s": round(statistics.median(latencies), 3) if latencies else None,
        "min_latency_s": round(min(latencies), 3) if latencies else None,
        "max_latency_s": round(max(latencies), 3) if latencies else None,
        "ttft_s": None,  # non-stream chat — not measured
        "tokens_per_s_samples": [],
        "error_categories": errors,
    }


def run_text_trials(gw: ModelGateway, model: str, n: int = 5, timeout_s: float = 60.0) -> dict[str, Any]:
    oks = 0
    fails = 0
    lats: list[float] = []
    errs: list[str] = []
    tps: list[float] = []
    lengths: list[int] = []
    timeouts = 0
    retries = 0
    trials = []
    for i in range(n):
        res = gw.complete_text(TEXT_PROMPT, model=model, timeout_s=timeout_s)
        trials.append(
            {
                "i": i,
                "ok": res.ok,
                "latency_s": res.latency_s,
                "attempts": res.attempts,
                "failure_kind": res.failure_kind.value,
                "error": res.error,
                "out_len": len(res.text or ""),
                "tokens_per_s": (res.metadata or {}).get("tokens_per_s"),
                "eval_count": (res.metadata or {}).get("eval_count"),
            }
        )
        retries += max(0, res.attempts - 1)
        if res.failure_kind == FailureKind.TIMEOUT:
            timeouts += 1
        if res.ok:
            oks += 1
            lats.append(res.latency_s)
            lengths.append(len(res.text or ""))
            if (res.metadata or {}).get("tokens_per_s") is not None:
                tps.append(float(res.metadata["tokens_per_s"]))
        else:
            fails += 1
            errs.append(res.failure_kind.value)
    summary = _summarize(lats, oks, fails, errs)
    summary["tokens_per_s_samples"] = tps
    summary["output_lengths"] = lengths
    summary["timeout_count"] = timeouts
    summary["retry_count"] = retries
    summary["trials"] = trials
    return summary


def run_structured_trials(
    gw: ModelGateway,
    model: str,
    *,
    mode: str,
    n: int = 10,
    timeout_s: float = 60.0,
) -> dict[str, Any]:
    oks = 0
    fails = 0
    lats: list[float] = []
    errs: list[str] = []
    timeouts = 0
    retries = 0
    trials = []
    for i in range(n):
        kwargs: dict[str, Any] = {
            "model": model,
            "timeout_s": timeout_s,
            "system": JSON_SYSTEM,
        }
        if mode == "native_json":
            kwargs["json_schema"] = None
        elif mode == "json_schema":
            kwargs["json_schema"] = JSON_SCHEMA
        elif mode == "json_schema_pydantic":
            kwargs["json_schema"] = JSON_SCHEMA
            kwargs["pydantic_model"] = StrictQualOut
        else:
            raise ValueError(mode)
        res = gw.complete_json(JSON_PROMPT, **kwargs)
        trials.append(
            {
                "i": i,
                "ok": res.ok,
                "latency_s": res.latency_s,
                "attempts": res.attempts,
                "failure_kind": res.failure_kind.value,
                "error": (res.error or "")[:200],
                "data": res.data,
            }
        )
        retries += max(0, res.attempts - 1)
        if res.failure_kind == FailureKind.TIMEOUT:
            timeouts += 1
        if res.ok:
            oks += 1
            lats.append(res.latency_s)
        else:
            fails += 1
            errs.append(res.failure_kind.value)
    summary = _summarize(lats, oks, fails, errs)
    summary["timeout_count"] = timeouts
    summary["retry_count"] = retries
    summary["mode"] = mode
    summary["trials"] = trials
    return summary


def qualify_rate(success: int, n: int, *, pass_ratio: float = 0.8) -> QualificationStatus:
    if n <= 0:
        return QualificationStatus.NOT_TESTED
    if success == n:
        return QualificationStatus.QUALIFIED
    if success / n >= pass_ratio:
        return QualificationStatus.QUALIFIED_WITH_RESTRICTIONS
    if success == 0:
        return QualificationStatus.NOT_QUALIFIED
    return QualificationStatus.NOT_QUALIFIED


def cancel_probe(gw: ModelGateway, model: str) -> dict[str, Any]:
    """Cancel mid-flight; observe client abort. Provider-side may continue."""
    token = CancellationToken()

    def cancel_soon():
        time.sleep(0.3)
        token.cancel()

    import threading

    threading.Thread(target=cancel_soon, daemon=True).start()
    # Long prompt / generation to keep request in flight
    t0 = time.monotonic()
    res = gw.complete_text(
        "Write a long detailed essay about embedded SPI, I2C, UART, and CAN.",
        model=model,
        timeout_s=45.0,
        cancel_token=token,
    )
    elapsed = time.monotonic() - t0
    return {
        "ok": res.ok,
        "failure_kind": res.failure_kind.value,
        "elapsed_s": round(elapsed, 3),
        "attempts": res.attempts,
        "metadata": res.metadata,
        "client_aborted": res.failure_kind == FailureKind.CANCELLED and elapsed < 40,
        "provider_side_stopped": None,  # not claimed without evidence
        "note": "Ollama may continue generation after client disconnect",
    }


def tool_broker_probe(model: str, n: int = 5) -> dict[str, Any]:
    """Full Broker-mediated ResearchAgent get_system_info path (live Ollama)."""
    from agent_runtime.agents.research import ResearchAgent
    from agent_runtime.contracts import AgentTask, ExecutionStatus
    from agent_runtime.registry import AgentRegistry
    from agent_runtime.runtime import AgentRuntime
    from device_broker.broker import DeviceBroker
    from device_broker.client import BrokerClient
    from device_broker.policy import BrokerPolicy
    from master.provider_config import ProviderSettings, ProviderSpec
    from project_os import ProjectOS
    import tempfile
    from pathlib import Path as P

    work = P(tempfile.mkdtemp(prefix="pyra5d1_"))
    (work / "global").mkdir()
    (work / "projects").mkdir()
    pos = ProjectOS(work)
    broker = DeviceBroker(BrokerPolicy(work_root=work), project_resolver=pos.active_project)
    client = BrokerClient(broker)
    proj = pos.create(name="BenchTools", goal="5d.1")
    providers = ProviderSettings(
        default_provider="ollama",
        providers={
            "ollama": ProviderSpec(
                name="ollama",
                enabled=True,
                default_model=model,
                base_url="http://127.0.0.1:11434/v1",
            ),
        },
    )
    gw = ModelGateway(provider_settings=providers)
    # Use live model — no TestModel override
    rt = AgentRuntime(registry=AgentRegistry(), broker_client=client)
    rt.register(ResearchAgent(gateway=gw))
    results = []
    try:
        for i in range(n):
            t0 = time.monotonic()
            result = rt.run(
                AgentTask(
                    task_id=f"bench-tool-{i}",
                    project_id=proj["id"],
                    agent_id="research",
                    description=(
                        "Call get_system_info via your tools, then summarise the host "
                        "in a ResearchReport. Do not invent hardware."
                    ),
                    project_context={"project_id": proj["id"]},
                    timeout_s=90.0,
                )
            )
            blob = str(result.evidence)
            broker_mediated = "get_system_info" in blob or "broker_calls" in blob
            results.append(
                {
                    "i": i,
                    "status": result.status.value if hasattr(result.status, "value") else str(result.status),
                    "latency_s": round(time.monotonic() - t0, 3),
                    "broker_mediated": broker_mediated,
                    "completed": result.status == ExecutionStatus.COMPLETED,
                    "summary": (result.summary or "")[:120],
                }
            )
    finally:
        broker.close()
        pos.close()
    ok = sum(1 for r in results if r["completed"] and r["broker_mediated"])
    return {
        "model": model,
        "n": n,
        "broker_mediated_successes": ok,
        "trials": results,
        "qualification": qualify_rate(ok, n, pass_ratio=0.6).value,
    }


def main() -> None:
    settings = Settings(
        ollama_host=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
        ollama_model="qwen2.5:3b",
        gateway_timeout_s=60.0,
        gateway_max_retries=1,
        gateway_retry_backoff_s=0.25,
        gateway_num_predict=128,
    )
    gw = ModelGateway(settings=settings)
    models = [m.get("name") for m in gw.list_ollama_models() if m.get("name")]
    print("Installed models:", models)
    ollama_pid = _ollama_pid()
    report: dict[str, Any] = {
        "phase": "5d.1",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "host": settings.ollama_host,
        "env": {
            "gateway_timeout_s": settings.gateway_timeout_s,
            "gateway_max_retries": settings.gateway_max_retries,
            "gateway_num_predict": settings.gateway_num_predict,
            "platform": os.uname().machine if hasattr(os, "uname") else "unknown",
        },
        "rss_before_kb": {
            "benchmark_process": _self_rss(),
            "ollama": _rss_kb(ollama_pid) if ollama_pid else None,
            "ollama_pid": ollama_pid,
        },
        "models": models,
        "results": {},
    }

    for model in models:
        print(f"\n=== {model}: basic inference (n=5) ===")
        text = run_text_trials(gw, model, n=5, timeout_s=60.0)
        print(f"  success={text['success']}/{text['n']} median={text['median_latency_s']}s")

        print(f"=== {model}: structured native_json (n=10) ===")
        native = run_structured_trials(gw, model, mode="native_json", n=10, timeout_s=60.0)
        print(f"  success={native['success']}/{native['n']}")

        print(f"=== {model}: structured json_schema (n=10) ===")
        schema = run_structured_trials(gw, model, mode="json_schema", n=10, timeout_s=60.0)
        print(f"  success={schema['success']}/{schema['n']}")

        print(f"=== {model}: json_schema + pydantic (n=10) ===")
        pyd = run_structured_trials(gw, model, mode="json_schema_pydantic", n=10, timeout_s=60.0)
        print(f"  success={pyd['success']}/{pyd['n']}")

        print(f"=== {model}: cancel probe ===")
        cancel = cancel_probe(gw, model)
        print(f"  kind={cancel['failure_kind']} elapsed={cancel['elapsed_s']}s")

        profile = ModelCapabilityProfile(
            provider="ollama",
            model_id=model,
            basic_inference=qualify_rate(text["success"], text["n"]),
            structured_json=qualify_rate(native["success"], native["n"], pass_ratio=0.7),
            json_schema_output=qualify_rate(schema["success"], schema["n"], pass_ratio=0.7),
            pydantic_schema_reliability=qualify_rate(pyd["success"], pyd["n"], pass_ratio=0.7),
            tool_calling=QualificationStatus.NOT_TESTED,
            multimodal=QualificationStatus.NOT_TESTED,
            measured_latency={
                "basic_median_s": text["median_latency_s"],
                "basic_min_s": text["min_latency_s"],
                "basic_max_s": text["max_latency_s"],
                "tokens_per_s_samples": text.get("tokens_per_s_samples") or [],
            },
            sample_counts={
                "basic": text["n"],
                "native_json": native["n"],
                "json_schema": schema["n"],
                "pydantic": pyd["n"],
            },
            known_restrictions=[],
            notes="Phase 5d.1 repeated qualification; small-n exploratory.",
        )
        if text["success"] < text["n"]:
            profile.known_restrictions.append("Basic inference not 100% reliable under load/timeout.")
        if native["success"] < native["n"]:
            profile.known_restrictions.append("Native format=json not fully reliable.")
        if schema["success"] < schema["n"]:
            profile.known_restrictions.append("JSON Schema mode not fully reliable.")
        if pyd["success"] < pyd["n"]:
            profile.known_restrictions.append("Pydantic-authoritative validation often rejects model output.")
        upsert_profile(profile)

        report["results"][model] = {
            "basic_inference": text,
            "structured_native_json": native,
            "structured_json_schema": schema,
            "structured_json_schema_pydantic": pyd,
            "cancel_probe": cancel,
            "profile": profile.to_dict(),
        }

    # Tool calling on qwen if present (expensive)
    if "qwen2.5:3b" in models:
        print("\n=== tool-calling Broker path qwen2.5:3b (n=5) ===")
        try:
            tools = tool_broker_probe("qwen2.5:3b", n=5)
            report["tool_calling_qwen"] = tools
            p = report["results"]["qwen2.5:3b"]["profile"]
            p["tool_calling"] = tools["qualification"]
            # sync upsert
            from master.model_profiles import get_profile

            gp = get_profile("ollama", "qwen2.5:3b")
            if gp:
                gp.tool_calling = QualificationStatus(tools["qualification"])
                upsert_profile(gp)
            print(f"  broker successes={tools['broker_mediated_successes']}/{tools['n']}")
        except Exception as exc:
            report["tool_calling_qwen"] = {"error": f"{type(exc).__name__}: {exc}"}
            print("  tool probe failed:", exc)

    if "gemma3:1b" in models:
        report["results"]["gemma3:1b"]["profile"]["tool_calling"] = (
            QualificationStatus.NOT_TESTED.value
        )

    ollama_pid = _ollama_pid()
    report["rss_after_kb"] = {
        "benchmark_process": _self_rss(),
        "ollama": _rss_kb(ollama_pid) if ollama_pid else None,
    }
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))
    print("\nWrote", OUT)


if __name__ == "__main__":
    main()
