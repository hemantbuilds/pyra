"""Local Ollama client + structured intent extraction (pukky lineage)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

import httpx

from .config import SETTINGS
from .contracts import Intent, IntentKind, RiskLevel
from project_os import textparse

log = logging.getLogger("pyra.master.model")

_INTENT_KINDS = ", ".join(k.value for k in IntentKind)

_INTENT_SYSTEM = f"""You are PYRA Master intent classifier on a Raspberry Pi.
Reply with ONLY one JSON object, no markdown, no commentary.
Schema:
{{
  "kind": one of [{_INTENT_KINDS}],
  "project_ref": string or null,
  "needs_cloud": boolean,
  "agent_hints": string array,
  "risk_level": one of [L0,L1,L2,L3],
  "confidence": number 0..1,
  "notes": short string
}}
Rules:
- hardware_discovery: enumerate/identify connected USB/serial/debug hardware (no flash).
- hardware_bringup: user asked to bring up a board — Phase 4 still runs discovery only (no flash).
- project_*/task_*/checkpoint_*: project management operations.
- device_*: Device Broker ops (list/read/write workspace files, system info, toolchains, allowlisted commands).
- agent_list: list Agent Runtime registered agents.
- agent_run: run a named Agent Runtime agent (echo, broker_probe, …).
- Keep needs_cloud false unless deep engineering reasoning is required.
- Never assume Arduino or any specific MCU without evidence.
"""


def _strip_fences(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"(?is)<think(?:ing)?>.*?</think(?:ing)?>", "", text).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_json(text: str) -> Optional[dict[str, Any]]:
    cleaned = _strip_fences(text)
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


def deterministic_intent(text: str) -> Intent:
    """Rule-based router for clear project/system phrases."""
    t = text.lower().strip()

    # Wake-word greeting only when there is no substantive command after it.
    if any(w in t for w in ("hello", "hi ", "hey pyra", "hey dot", "good morning")):
        remainder = t
        for w in ("hey pyra", "hey dot", "good morning", "hello", "hi"):
            remainder = remainder.replace(w, " ")
        remainder = remainder.strip(" ,!.?:;-")
        if len(remainder) < 4:
            return Intent(kind=IntentKind.GREETING, confidence=0.9, notes="deterministic")

    if any(p in t for p in ("list project", "show project", "my projects", "all projects", "show my active project")):
        return Intent(kind=IntentKind.PROJECT_LIST, confidence=0.9, notes="deterministic")

    if any(p in t for p in ("list task", "show task", "my tasks", "project tasks")):
        return Intent(kind=IntentKind.TASK_LIST, confidence=0.9, notes="deterministic")

    if re.search(r"(?i)\b(add|create|new)\s+(a\s+)?task\b", text):
        return Intent(kind=IntentKind.TASK_CREATE, confidence=0.9, notes="deterministic")

    if re.search(r"(?i)mark .+ as completed|mark .+ complete|\bcomplete\s+(the\s+)?task|\bfinish\s+(the\s+)?task", text):
        return Intent(kind=IntentKind.TASK_UPDATE, confidence=0.9, notes="deterministic")

    if re.search(r"(?i)restore\s+(a\s+|the\s+)?checkpoint", text):
        return Intent(kind=IntentKind.CHECKPOINT_RESTORE, confidence=0.9, notes="deterministic")

    if re.search(r"(?i)(create|save|take)\s+(a\s+)?checkpoint", text):
        return Intent(kind=IntentKind.CHECKPOINT_CREATE, confidence=0.9, notes="deterministic")

    if re.search(r"(?i)save\s+(this\s+)?(engineering\s+)?decision|\bdecision\b", text) and (
        "save" in t or "record" in t or "add" in t
    ):
        return Intent(kind=IntentKind.PROJECT_DECISION, confidence=0.85, notes="deterministic")

    if re.search(r"(?i)(save|add|record)\s+(a\s+|this\s+)?note\b|^\s*note\s*:", text):
        return Intent(kind=IntentKind.PROJECT_NOTE, confidence=0.85, notes="deterministic")

    if re.search(r"(?i)\barchive\s+(the\s+)?project\b", text):
        ref = textparse.extract_project_ref_for_switch(text)
        return Intent(kind=IntentKind.PROJECT_ARCHIVE, project_ref=ref, confidence=0.85, notes="deterministic")

    # Directory creation must win over "… project" substring matches.
    if re.search(r"(?i)create\s+(a\s+)?(directory|dir|folder)\b", text):
        return Intent(kind=IntentKind.DEVICE_CREATE_DIR, risk_level=RiskLevel.L1, confidence=0.9, notes="deterministic")

    if any(p in t for p in ("create project", "new project", "start a project", "start project")) or re.search(
        r"(?i)create\s+(a\s+)?(new\s+)?(?!directory|dir|folder)(.+\s+)?project\b", text
    ):
        name = textparse.extract_project_name_for_create(text)
        return Intent(
            kind=IntentKind.PROJECT_CREATE,
            project_ref=name,
            confidence=0.9,
            notes="deterministic",
        )

    if "switch" in t and "project" in t:
        ref = textparse.extract_project_ref_for_switch(text)
        return Intent(kind=IntentKind.PROJECT_SWITCH, project_ref=ref, confidence=0.9, notes="deterministic")

    if any(p in t for p in ("continue", "resume", "where did we stop", "where were we", "what were we working")):
        ref = textparse.extract_project_ref_for_switch(text)
        # "what were we working on in this project" → continue/status
        if "what were we" in t or "where did we" in t or "where were we" in t:
            return Intent(kind=IntentKind.PROJECT_CONTINUE, project_ref=ref, confidence=0.85, notes="deterministic")
        return Intent(kind=IntentKind.PROJECT_CONTINUE, project_ref=ref, confidence=0.85, notes="deterministic")

    if re.search(r"(?i)project\s+status|status\s+of\s+(the\s+)?project|show\s+(the\s+)?project", text):
        ref = textparse.extract_project_ref_for_switch(text)
        return Intent(kind=IntentKind.PROJECT_STATUS, project_ref=ref, confidence=0.85, notes="deterministic")

    # Device Broker intents (before generic bring-up / status)
    if any(p in t for p in (
        "list broker tools", "device broker tools", "available broker tools",
        "what tools can the device broker",
    )):
        return Intent(kind=IntentKind.DEVICE_LIST_TOOLS, risk_level=RiskLevel.L0, confidence=0.9, notes="deterministic")

    if any(p in t for p in ("execution history", "audit log", "broker audit", "device audit")):
        return Intent(kind=IntentKind.DEVICE_AUDIT, risk_level=RiskLevel.L0, confidence=0.85, notes="deterministic")

    if any(p in t for p in (
        "operating system", "what os", "system info", "platform info",
        "what operating system",
    )):
        return Intent(kind=IntentKind.DEVICE_SYSTEM_INFO, risk_level=RiskLevel.L0, confidence=0.9, notes="deterministic")

    if any(p in t for p in (
        "toolchain", "toolchains", "embedded toolchain", "installed tool",
        "which embedded", "tool versions",
    )):
        return Intent(kind=IntentKind.DEVICE_TOOLCHAINS, risk_level=RiskLevel.L0, confidence=0.9, notes="deterministic")

    if re.search(r"(?i)run (the )?(approved )?version[- ]?check|run (python|git|gcc|cmake|uname).*(version|check)", text):
        return Intent(kind=IntentKind.DEVICE_RUN_COMMAND, risk_level=RiskLevel.L1, confidence=0.9, notes="deterministic")

    if re.search(r"(?i)\bwrite\b.+\bto\b|\bwrite (a )?file\b", text) and "decision" not in t and "note" not in t:
        return Intent(kind=IntentKind.DEVICE_WRITE_FILE, risk_level=RiskLevel.L1, confidence=0.85, notes="deterministic")

    if re.search(r"(?i)\bread (the )?(project )?configuration|\bread (the )?file\b|\bread [\"'\w./~-]+", text):
        return Intent(kind=IntentKind.DEVICE_READ_FILE, risk_level=RiskLevel.L0, confidence=0.85, notes="deterministic")

    if any(p in t for p in (
        "show the files", "list the files", "list files", "files in my",
        "files in the", "workspace files", "list directory", "list the directory",
        "show files in",
    )):
        return Intent(kind=IntentKind.DEVICE_LIST_DIR, risk_level=RiskLevel.L0, confidence=0.9, notes="deterministic")

    if re.search(r"(?i)\bfile info\b|\bstat\b .+", text):
        return Intent(kind=IntentKind.DEVICE_FILE_INFO, risk_level=RiskLevel.L0, confidence=0.85, notes="deterministic")

    discovery_keys = (
        "check the devices", "devices connected", "connected devices",
        "hardware discovery", "discover hardware", "enumerate hardware",
        "what boards are connected", "what devices are connected",
        "scan usb", "list connected hardware", "inspect connected hardware",
        "check devices connected", "devices connected to this",
    )
    if any(p in t for p in discovery_keys):
        return Intent(
            kind=IntentKind.HARDWARE_DISCOVERY,
            needs_cloud=False,
            agent_hints=["hardware", "lab", "discovery"],
            risk_level=RiskLevel.L0,
            confidence=0.92,
            notes="deterministic",
        )

    # Phase 7 full engineering workflow (before narrower bring-up)
    eng_workflow_keys = (
        "engineering report",
        "project plan",
        "system requirements",
        "system architecture",
        "hardware engineering",
        "firmware design",
        "approve before programming",
        "complete engineering",
        "embedded project",
        "plan the project",
        "analyze the system requirements",
        "prepare a complete engineering report",
    )
    eng_hits = sum(1 for p in eng_workflow_keys if p in t)
    if eng_hits >= 2 or "complete engineering report" in t or (
        "embedded project" in t and ("plan" in t or "requirements" in t or "report" in t)
    ):
        return Intent(
            kind=IntentKind.ENGINEERING_WORKFLOW,
            needs_cloud=False,
            agent_hints=["planning", "requirements", "architecture", "hardware_eng", "firmware_eng"],
            risk_level=RiskLevel.L2,
            confidence=0.93,
            notes="deterministic",
        )

    bringup_keys = (
        "bring up", "bring-up", "bringup", "connected board",
        "development board", "flash the board", "probe the board", "identify the board",
        "connected hardware", "discover the connected", "discover connected",
    )
    if any(p in t for p in bringup_keys):
        return Intent(
            kind=IntentKind.HARDWARE_BRINGUP,
            needs_cloud=False,
            agent_hints=["hardware", "lab", "firmware"],
            risk_level=RiskLevel.L0,
            confidence=0.85,
            notes="deterministic",
        )

    # Agent Runtime (Phase 5b) — before generic capability/status
    if any(p in t for p in (
        "list agents", "list registered agents", "show agents",
        "available agents", "what agents", "agent runtime agents",
    )):
        return Intent(
            kind=IntentKind.AGENT_LIST,
            agent_hints=[],
            risk_level=RiskLevel.L0,
            confidence=0.9,
            notes="deterministic",
        )

    # Research agent natural phrases (before generic agent-run)
    if re.search(
        r"(?i)\b(ask\s+)?research(\s+agent)?\b"
        r"|\bresearch\s+this\b"
        r"|\banalyse\s+this\s+project\b"
        r"|\banalyze\s+this\s+project\b",
        text,
    ) and not re.search(r"(?i)\blist\s+agents\b", text):
        return Intent(
            kind=IntentKind.AGENT_RUN,
            agent_hints=["research"],
            risk_level=RiskLevel.L0,
            confidence=0.9,
            notes="deterministic",
        )

    if re.search(
        r"(?i)\b(run|invoke|execute)\s+(the\s+)?(agent\s+)?[a-z][a-z0-9_]*(\s+agent)?\b"
        r"|\brun\s+(echo|broker[_\s-]?probe|research)\b",
        text,
    ):
        hints: list[str] = []
        if re.search(r"(?i)broker[_\s-]?probe", text):
            hints.append("broker_probe")
        elif re.search(r"(?i)\bresearch\b", text):
            hints.append("research")
        elif re.search(r"(?i)\becho\b", text):
            hints.append("echo")
        return Intent(
            kind=IntentKind.AGENT_RUN,
            agent_hints=hints,
            risk_level=RiskLevel.L0,
            confidence=0.9,
            notes="deterministic",
        )

    if any(p in t for p in ("what can you", "capabilities", "what do you do")):
        return Intent(kind=IntentKind.CAPABILITY_QUERY, confidence=0.8, notes="deterministic")

    if t == "status" or t.endswith(" status") or t.startswith("status "):
        return Intent(kind=IntentKind.STATUS, confidence=0.8, notes="deterministic")

    return Intent(kind=IntentKind.GENERAL, confidence=0.4, notes="deterministic-fallback")


def _intent_from_dict(data: dict[str, Any]) -> Intent:
    kind_raw = str(data.get("kind", "unknown")).strip().lower()
    try:
        kind = IntentKind(kind_raw)
    except ValueError:
        kind = IntentKind.UNKNOWN

    risk_raw = str(data.get("risk_level", "L0")).strip().upper()
    try:
        risk = RiskLevel(risk_raw)
    except ValueError:
        risk = RiskLevel.L0

    hints = data.get("agent_hints") or []
    if not isinstance(hints, list):
        hints = []

    conf = data.get("confidence", 0.5)
    try:
        conf_f = float(conf)
    except (TypeError, ValueError):
        conf_f = 0.5

    return Intent(
        kind=kind,
        project_ref=data.get("project_ref"),
        needs_cloud=bool(data.get("needs_cloud", False)),
        agent_hints=[str(h) for h in hints],
        risk_level=risk,
        confidence=max(0.0, min(1.0, conf_f)),
        notes=str(data.get("notes") or "ollama"),
    )


class ProviderError(Exception):
    """Controlled provider/model resolution failure (no secrets)."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class ModelGateway:
    """
    PYRA-owned model interface.

    Phase 1–5b: Ollama intent classification.
    Phase 5c: resolve PydanticAI model adapters for specialists.
    Phase 5d: invoke helpers with timeout/retry/cancel + model inventory.
    """

    def __init__(self, settings=SETTINGS, provider_settings=None, retry_policy=None):
        self.settings = settings
        from .provider_config import ProviderSettings
        from .invocation import RetryPolicy

        self.provider_settings = provider_settings or ProviderSettings.load()
        self._override_model = None  # test injection
        self.retry_policy = retry_policy or RetryPolicy(
            max_retries=int(getattr(settings, "gateway_max_retries", 1)),
            backoff_s=float(getattr(settings, "gateway_retry_backoff_s", 0.25)),
        )
        # Optional injectable transport for tests (signature like httpx post).
        self._http_post = None

    def set_override_model(self, model) -> None:
        """Tests: force a deterministic PydanticAI model for specialists."""
        self._override_model = model

    def clear_override_model(self) -> None:
        self._override_model = None

    def ollama_reachable(self) -> bool:
        try:
            with httpx.Client(timeout=2.0) as client:
                r = client.get(f"{self.settings.ollama_host.rstrip('/')}/api/tags")
                return r.status_code == 200
        except Exception:
            return False

    def list_ollama_models(self) -> list[dict[str, Any]]:
        """Return installed Ollama model metadata (name, size, digest)."""
        try:
            with httpx.Client(timeout=3.0) as client:
                r = client.get(f"{self.settings.ollama_host.rstrip('/')}/api/tags")
                r.raise_for_status()
                models = (r.json() or {}).get("models") or []
            out = []
            for m in models:
                out.append(
                    {
                        "name": m.get("name"),
                        "model": m.get("model") or m.get("name"),
                        "size": m.get("size"),
                        "digest": (m.get("digest") or "")[:16],
                        "modified_at": m.get("modified_at"),
                    }
                )
            return out
        except Exception:
            return []

    def model_available(self, model_name: str, *, provider: str = "ollama") -> bool:
        if provider != "ollama":
            return False
        names = {m.get("name") for m in self.list_ollama_models()}
        return model_name in names

    def provider_status(self) -> dict[str, Any]:
        status = self.provider_settings.public_status()
        status["ollama_reachable"] = self.ollama_reachable()
        status["override_active"] = self._override_model is not None
        status["gateway_timeout_s"] = getattr(self.settings, "gateway_timeout_s", 45.0)
        status["gateway_max_retries"] = self.retry_policy.max_retries
        status["max_request_duration_s"] = self.max_request_duration_s()
        status["ollama_models"] = [m.get("name") for m in self.list_ollama_models()]
        try:
            from .model_profiles import profiles_public

            status["model_capability_profiles"] = profiles_public()
        except Exception:
            status["model_capability_profiles"] = []
        return status

    def resolve_agent_model(
        self,
        *,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        """
        Return a PydanticAI Model instance for specialist agents.

        Never embeds API keys into AgentTask/AgentResult — keys stay in provider client.
        """
        if self._override_model is not None:
            return self._override_model

        from .provider_config import read_api_key

        pname = (provider or self.provider_settings.default_provider or "ollama").lower()
        try:
            spec = self.provider_settings.get(pname)
        except KeyError as exc:
            raise ProviderError("unknown_provider", str(exc)) from exc

        if not spec.enabled:
            raise ProviderError("provider_disabled", f"provider {pname!r} is disabled")

        name = model_name or spec.default_model
        if not name:
            raise ProviderError("missing_model", f"no model configured for {pname}")

        if pname == "test":
            from pydantic_ai.models.test import TestModel

            return TestModel(call_tools=[])

        if pname == "ollama":
            if not self.ollama_reachable():
                raise ProviderError(
                    "provider_unavailable",
                    f"ollama not reachable at {self.settings.ollama_host}",
                )
            from pydantic_ai.models.ollama import OllamaModel
            from pydantic_ai.providers.ollama import OllamaProvider

            return OllamaModel(name, provider=OllamaProvider(base_url=spec.base_url))

        if pname == "openai":
            key = read_api_key(spec.api_key_env)
            if not key:
                raise ProviderError(
                    "missing_credentials",
                    f"set {spec.api_key_env} to enable openai provider",
                )
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider

            return OpenAIChatModel(
                name,
                provider=OpenAIProvider(api_key=key, base_url=spec.base_url or None),
            )

        raise ProviderError("unsupported_provider", f"provider {pname!r} not supported in Phase 5c")

    def complete_text(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        timeout_s: Optional[float] = None,
        cancel_token=None,
        system: Optional[str] = None,
    ):
        """Direct Ollama chat completion with bounded retries (Phase 5d)."""
        return self._ollama_chat(
            prompt,
            model=model,
            timeout_s=timeout_s,
            cancel_token=cancel_token,
            system=system,
            response_format=None,
        )

    def complete_json(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        timeout_s: Optional[float] = None,
        cancel_token=None,
        system: Optional[str] = None,
        json_schema: Optional[dict[str, Any]] = None,
        pydantic_model: Any = None,
    ):
        """
        Ollama JSON completion with optional Pydantic validation.

        Prefer json_schema (dict) when structured fields are required.
        `timeout_s` is the **total wall-clock budget** including retries (5d.1).
        Pydantic validation is authoritative when `pydantic_model` is provided —
        no fabricated defaults are injected on missing fields.
        """
        fmt: Any = json_schema if json_schema is not None else "json"
        return self._ollama_chat(
            prompt,
            model=model,
            timeout_s=timeout_s,
            cancel_token=cancel_token,
            system=system,
            response_format=fmt,
            expect_json=True,
            pydantic_model=pydantic_model,
        )

    def max_request_duration_s(self, timeout_s: Optional[float] = None) -> float:
        """Configured maximum wall-clock duration for one gateway invoke."""
        return float(
            timeout_s
            if timeout_s is not None
            else getattr(self.settings, "gateway_timeout_s", 45.0)
        )

    def _ollama_chat(
        self,
        prompt: str,
        *,
        model: Optional[str],
        timeout_s: Optional[float],
        cancel_token,
        system: Optional[str],
        response_format: Any,
        expect_json: bool = False,
        pydantic_model: Any = None,
    ):
        import time

        from .invocation import (
            CancelledError,
            FailureKind,
            InvocationResult,
            classify_http_error,
            redact_error_text,
            remaining_timeout,
        )

        model_name = model or self.settings.ollama_model
        # Total wall-clock budget for all attempts (does not reset per retry).
        total_budget = self.max_request_duration_s(timeout_s)
        provider = "ollama"
        deadline = time.monotonic() + total_budget

        if not self.ollama_reachable():
            return InvocationResult(
                ok=False,
                provider=provider,
                model=model_name,
                failure_kind=FailureKind.PROVIDER_UNAVAILABLE,
                error=f"ollama not reachable at {self.settings.ollama_host}",
                metadata={"total_budget_s": total_budget},
            )

        if not self.model_available(model_name):
            return InvocationResult(
                ok=False,
                provider=provider,
                model=model_name,
                failure_kind=FailureKind.MODEL_UNAVAILABLE,
                error=f"model not installed: {model_name}",
                metadata={"total_budget_s": total_budget},
            )

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": model_name,
            "stream": False,
            "messages": messages,
            "options": {
                "temperature": 0.1,
                "num_predict": int(getattr(self.settings, "gateway_num_predict", 256)),
            },
        }
        if response_format is not None:
            payload["format"] = response_format

        url = f"{self.settings.ollama_host.rstrip('/')}/api/chat"
        attempts = 0
        last_kind = FailureKind.UNKNOWN
        last_error = None
        t_start = time.monotonic()
        clients_closed = 0

        while True:
            attempts += 1
            remaining = remaining_timeout(deadline)
            if remaining <= 0.05:
                return InvocationResult(
                    ok=False,
                    provider=provider,
                    model=model_name,
                    latency_s=round(time.monotonic() - t_start, 3),
                    attempts=attempts,
                    failure_kind=FailureKind.TIMEOUT,
                    error="total timeout budget exhausted",
                    metadata={
                        "total_budget_s": total_budget,
                        "clients_closed": clients_closed,
                    },
                )

            if cancel_token is not None:
                try:
                    cancel_token.raise_if_cancelled()
                except CancelledError as exc:
                    return InvocationResult(
                        ok=False,
                        provider=provider,
                        model=model_name,
                        latency_s=round(time.monotonic() - t_start, 3),
                        attempts=attempts,
                        failure_kind=FailureKind.CANCELLED,
                        error=str(exc),
                        metadata={
                            "total_budget_s": total_budget,
                            "clients_closed": clients_closed,
                            "provider_side_note": (
                                "client cancelled; Ollama may still finish generation server-side"
                            ),
                        },
                    )
            try:
                if self._http_post is not None:
                    body = self._http_post(url, payload, remaining)
                else:
                    body, clients_closed = self._http_post_cancellable(
                        url,
                        payload,
                        remaining,
                        cancel_token=cancel_token,
                        clients_closed=clients_closed,
                    )
                content = ((body.get("message") or {}).get("content") or "")
                data = None
                if expect_json:
                    if not content.strip():
                        kind = FailureKind.VALIDATION
                        last_kind, last_error = kind, "empty structured output"
                        if self.retry_policy.allow(kind, attempts - 1) and remaining_timeout(deadline) > 0.1:
                            time.sleep(min(self.retry_policy.backoff_s, remaining_timeout(deadline)))
                            continue
                        return InvocationResult(
                            ok=False,
                            text=content,
                            provider=provider,
                            model=model_name,
                            latency_s=round(time.monotonic() - t_start, 3),
                            attempts=attempts,
                            failure_kind=kind,
                            error=last_error,
                            metadata={"total_budget_s": total_budget},
                        )
                    try:
                        parsed = json.loads(content)
                        if not isinstance(parsed, dict):
                            raise ValueError("JSON root must be an object")
                        if pydantic_model is not None:
                            # Authoritative validation — do not fill missing fields.
                            validated = pydantic_model.model_validate(parsed)
                            data = validated.model_dump()
                        else:
                            data = parsed
                    except Exception as exc:
                        kind = FailureKind.VALIDATION
                        last_kind, last_error = kind, f"invalid structured output: {exc}"
                        if self.retry_policy.allow(kind, attempts - 1) and remaining_timeout(deadline) > 0.1:
                            time.sleep(min(self.retry_policy.backoff_s, remaining_timeout(deadline)))
                            continue
                        return InvocationResult(
                            ok=False,
                            text=content,
                            provider=provider,
                            model=model_name,
                            latency_s=round(time.monotonic() - t_start, 3),
                            attempts=attempts,
                            failure_kind=kind,
                            error=last_error,
                            metadata={
                                "eval_count": body.get("eval_count"),
                                "total_budget_s": total_budget,
                            },
                        )
                meta = {
                    "eval_count": body.get("eval_count"),
                    "eval_duration": body.get("eval_duration"),
                    "prompt_eval_count": body.get("prompt_eval_count"),
                    "total_budget_s": total_budget,
                    "clients_closed": clients_closed,
                }
                if meta.get("eval_count") and meta.get("eval_duration"):
                    try:
                        meta["tokens_per_s"] = round(
                            float(meta["eval_count"]) / (float(meta["eval_duration"]) / 1e9),
                            2,
                        )
                    except Exception:
                        pass
                return InvocationResult(
                    ok=True,
                    text=content,
                    data=data,
                    provider=provider,
                    model=model_name,
                    latency_s=round(time.monotonic() - t_start, 3),
                    attempts=attempts,
                    metadata=meta,
                )
            except Exception as exc:
                if getattr(exc, "clients_closed", None) is not None:
                    clients_closed = int(exc.clients_closed)
                kind = classify_http_error(exc)
                last_kind = kind
                last_error = redact_error_text(f"{type(exc).__name__}: {exc}")
                if self.retry_policy.allow(kind, attempts - 1) and remaining_timeout(deadline) > 0.1:
                    time.sleep(min(self.retry_policy.backoff_s, remaining_timeout(deadline)))
                    continue
                return InvocationResult(
                    ok=False,
                    provider=provider,
                    model=model_name,
                    latency_s=round(time.monotonic() - t_start, 3),
                    attempts=attempts,
                    failure_kind=last_kind,
                    error=last_error,
                    metadata={
                        "total_budget_s": total_budget,
                        "clients_closed": clients_closed,
                        "provider_side_note": (
                            "if cancelled mid-flight, Ollama may continue server-side"
                            if kind == FailureKind.CANCELLED
                            else None
                        ),
                    },
                )

    def _http_post_cancellable(
        self,
        url: str,
        payload: dict[str, Any],
        timeout: float,
        *,
        cancel_token,
        clients_closed: int,
    ) -> tuple[dict[str, Any], int]:
        """
        POST on a worker thread; cancel closes the httpx client from the caller.

        Client-side abort is best-effort. Ollama may still continue generation
        server-side — documented as a provider limitation (Phase 5d.1).
        """
        import threading

        from .invocation import CancelledError

        if cancel_token is not None:
            cancel_token.raise_if_cancelled()

        # Fast path when no cancel token: simple blocking client.
        if cancel_token is None:
            with httpx.Client(timeout=timeout) as client:
                r = client.post(url, json=payload)
                r.raise_for_status()
                return r.json(), clients_closed

        client = httpx.Client(timeout=timeout)
        box: dict[str, Any] = {"body": None, "exc": None}
        closed_n = clients_closed

        def worker() -> None:
            try:
                r = client.post(url, json=payload)
                r.raise_for_status()
                box["body"] = r.json()
            except Exception as exc:  # noqa: BLE001 — marshalled to caller
                box["exc"] = exc
            finally:
                try:
                    client.close()
                except Exception:
                    pass

        thr = threading.Thread(target=worker, name="pyra-gw-http", daemon=True)
        thr.start()
        while thr.is_alive():
            if cancel_token.cancelled:
                try:
                    client.close()
                    closed_n += 1
                except Exception:
                    pass
                thr.join(timeout=1.0)
                err = CancelledError("request cancelled; HTTP client closed")
                err.clients_closed = closed_n  # type: ignore[attr-defined]
                raise err
            thr.join(timeout=0.05)

        if box["exc"] is not None:
            if cancel_token.cancelled:
                err = CancelledError("request cancelled; HTTP client closed")
                err.clients_closed = closed_n  # type: ignore[attr-defined]
                raise err from box["exc"]
            raise box["exc"]
        if box["body"] is None:
            raise RuntimeError("empty HTTP response")
        return box["body"], closed_n
    def classify_intent(self, text: str) -> tuple[Intent, str]:
        quick = deterministic_intent(text)
        if quick.kind not in (IntentKind.GENERAL, IntentKind.UNKNOWN) and quick.confidence >= 0.75:
            return quick, "deterministic"

        if not self.ollama_reachable():
            return quick, "deterministic"

        payload = {
            "model": self.settings.ollama_model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1, "num_ctx": 2048},
            "messages": [
                {"role": "system", "content": _INTENT_SYSTEM},
                {"role": "user", "content": text},
            ],
        }
        try:
            with httpx.Client(timeout=self.settings.request_timeout_s) as client:
                r = client.post(
                    f"{self.settings.ollama_host.rstrip('/')}/api/chat",
                    json=payload,
                )
                r.raise_for_status()
                body = r.json()
            content = (body.get("message") or {}).get("content") or ""
            data = _extract_json(content)
            if not data:
                log.warning("Ollama intent JSON parse failed; using deterministic")
                return quick, "deterministic"
            return _intent_from_dict(data), "ollama"
        except Exception as exc:
            log.warning("Ollama intent failed: %s", exc)
            return quick, "deterministic"
