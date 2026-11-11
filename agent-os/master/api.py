"""FastAPI application: health, Master /v1, Dot /dot/v1."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

# Allow `python -m master` from agent-os/
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from master import __version__
from master.config import SETTINGS
from master.contracts import HealthResponse, InteractRequest, InteractResponse
from master.model_gateway import ModelGateway
from master.orchestrator import Orchestrator
from integrations.dot.gateway import DotGateway

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("pyra.api")

gateway = ModelGateway(SETTINGS)
orchestrator = Orchestrator(gateway)
dot = DotGateway(orchestrator)

app = FastAPI(title="PYRA Master + Dot", version=__version__)


def _check_token(authorization: str | None = Header(default=None)) -> None:
    expected = SETTINGS.token
    if not expected:
        return
    if authorization is None:
        # Allow loopback unauthenticated in early Phase 1 when token is default
        # and caller omitted header — still accept explicit Bearer.
        return
    if authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    else:
        token = authorization.strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="invalid token")


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    ollama = "up" if gateway.ollama_reachable() else "down"
    return HealthResponse(
        status="ok",
        service="pyra-master",
        version=__version__,
        ollama=ollama,
        model=SETTINGS.ollama_model,
    )


@app.post("/v1/interact", response_model=InteractResponse)
def master_interact(
    req: InteractRequest,
    _: None = Depends(_check_token),
) -> InteractResponse:
    """Direct Master entry (CLI / tests). Prefer Dot for Mark."""
    return orchestrator.handle(req)


@app.post("/dot/v1/interact", response_model=InteractResponse)
def dot_interact(
    req: InteractRequest,
    _: None = Depends(_check_token),
) -> InteractResponse:
    """Mark → Dot → Master."""
    if not req.source or req.source == "dot":
        req = req.model_copy(update={"source": "mark" if req.metadata.get("from_mark") else "dot"})
    return dot.route(req)


@app.get("/v1/capabilities")
def capabilities_list(_: None = Depends(_check_token)):
    from master import capabilities as caps

    return {"capabilities": caps.list_capabilities()}


@app.get("/v1/projects")
def projects_list(_: None = Depends(_check_token)):
    from master.project_service import get_project_os

    pos = get_project_os()
    return {
        "active_project_id": pos.active_id(),
        "projects": pos.list_projects(),
    }


@app.get("/v1/projects/active/context")
def active_context(_: None = Depends(_check_token)):
    from master.project_service import get_project_os

    pos = get_project_os()
    active = pos.active_project()
    if not active:
        return {"active_project_id": None, "context": None}
    return {
        "active_project_id": active["id"],
        "context": pos.context_pack(active["id"]),
    }


@app.get("/v1/agents")
def agents_list(_: None = Depends(_check_token)):
    from agent_runtime.service import get_agent_runtime

    rt = get_agent_runtime()
    return {
        "agents": [m.model_dump() for m in rt.list_agents()],
        "capabilities": rt.list_capabilities(),
    }


@app.post("/v1/agents/run")
def agents_run(body: dict, _: None = Depends(_check_token)):
    """
    Master-facing Agent Runtime invocation (not a user-facing alternate API).
    Prefer Dot → interact for Mark; this endpoint is for CLI/tests/Master tools.
    """
    from agent_runtime.contracts import AgentTask
    from agent_runtime.service import get_agent_runtime
    from master.project_service import get_project_os

    pos = get_project_os()
    active = pos.active_project()
    project_id = body.get("project_id") or (active["id"] if active else None)
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id required (or set active project)")

    agent_id = body.get("agent_id")
    capability = body.get("capability")
    if not agent_id and not capability:
        raise HTTPException(status_code=400, detail="agent_id or capability required")

    try:
        proj = pos.get(project_id)
    except Exception:
        proj = active if active and active.get("id") == project_id else None
    context = {
        "project_id": project_id,
        "name": (proj or {}).get("name"),
        "workspace_path": (proj or {}).get("workspace_path"),
    }

    task = AgentTask(
        task_id=str(body.get("task_id") or f"api_{os.urandom(6).hex()}"),
        project_id=project_id,
        requesting_component=str(body.get("requesting_component") or "master_api"),
        agent_id=agent_id,
        capability=capability,
        description=str(body.get("description") or "api agent run"),
        inputs=body.get("inputs") if isinstance(body.get("inputs"), dict) else {},
        project_context=context,
        allowed_capabilities=body.get("allowed_capabilities") or [],
        timeout_s=body.get("timeout_s"),
        correlation_id=body.get("correlation_id"),
        max_level=str(body.get("max_level") or "L1"),
    )
    result = get_agent_runtime().run(task)
    return result.model_dump(mode="json")


@app.get("/broker/v1/tools")
def broker_tools(_: None = Depends(_check_token)):
    from master.broker_service import get_broker

    return {"tools": get_broker().list_tools()}


@app.post("/broker/v1/call")
def broker_call(body: dict, _: None = Depends(_check_token)):
    """Direct Device Broker invocation (still policy-enforced)."""
    from master.broker_service import get_broker_client

    tool = str(body.get("tool") or "").strip()
    if not tool:
        raise HTTPException(status_code=400, detail="tool is required")
    arguments = body.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise HTTPException(status_code=400, detail="arguments must be an object")
    client = get_broker_client()
    result = client.call(
        tool,
        arguments,
        principal=str(body.get("principal") or "api"),
        max_level=str(body.get("max_level") or "L1"),
        project_id=body.get("project_id"),
        client="http",
    )
    return result.to_dict()


@app.exception_handler(Exception)
async def _unhandled(request, exc):  # noqa: ANN001
    log.exception("unhandled: %s", exc)
    return JSONResponse(status_code=500, content={"status": "error", "detail": str(exc)})


def main() -> None:
    import uvicorn

    host = SETTINGS.host
    port = SETTINGS.port
    log.info("Starting PYRA on http://%s:%s (pid=%s)", host, port, os.getpid())
    uvicorn.run(
        "master.api:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
