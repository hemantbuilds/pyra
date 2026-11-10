"""Master capability handlers backed by Project OS."""

from __future__ import annotations

from .contracts import Intent, IntentKind, InteractRequest
from .capabilities import CapabilityResult
from .project_service import get_project_os
from project_os.errors import ConflictError, NotFoundError, ProjectOSError, ValidationError
from project_os import textparse


def _err(speech: str, **evidence) -> CapabilityResult:
    return CapabilityResult(
        speech=speech,
        capability="project_os",
        status="error",
        evidence=evidence,
    )


def handle_project(req: InteractRequest, intent: Intent) -> CapabilityResult:
    pos = get_project_os()
    text = req.text.strip()

    try:
        if intent.kind == IntentKind.PROJECT_CREATE:
            return _create(pos, req, intent, text)
        if intent.kind == IntentKind.PROJECT_LIST:
            return _list(pos)
        if intent.kind == IntentKind.PROJECT_SWITCH:
            return _switch(pos, req, intent, text)
        if intent.kind == IntentKind.PROJECT_CONTINUE:
            return _continue(pos, req, intent, text)
        if intent.kind == IntentKind.PROJECT_STATUS:
            return _status(pos, req, intent, text)
        if intent.kind == IntentKind.PROJECT_NOTE:
            return _note(pos, req, intent, text, kind="note")
        if intent.kind == IntentKind.PROJECT_DECISION:
            return _note(pos, req, intent, text, kind="decision")
        if intent.kind == IntentKind.TASK_CREATE:
            return _task_create(pos, req, intent, text)
        if intent.kind == IntentKind.TASK_LIST:
            return _task_list(pos, req)
        if intent.kind == IntentKind.TASK_UPDATE:
            return _task_update(pos, req, intent, text)
        if intent.kind == IntentKind.CHECKPOINT_CREATE:
            return _checkpoint_create(pos, req)
        if intent.kind == IntentKind.CHECKPOINT_RESTORE:
            return _checkpoint_restore(pos, req, intent, text)
        if intent.kind == IntentKind.PROJECT_ARCHIVE:
            return _archive(pos, req, intent, text)
        return _err("Unsupported project operation.", intent=intent.kind.value)
    except NotFoundError as exc:
        return _err(str(exc), error="not_found")
    except ConflictError as exc:
        return _err(str(exc), error="conflict")
    except ValidationError as exc:
        return _err(str(exc), error="validation")
    except ProjectOSError as exc:
        return _err(f"Project OS error: {exc}", error="project_os")


def _create(pos, req, intent, text) -> CapabilityResult:
    name = intent.project_ref or textparse.extract_project_name_for_create(text)
    if not name:
        return _err(
            "Tell me the project name, for example: "
            "'Create a new drone development project.'"
        )
    goal = ""
    # Optional: "for X" already folded into name by parser
    row = pos.create(name, goal=goal or f"Goals for {name}", make_active=True)
    ctx = pos.context_pack(row["id"])
    return CapabilityResult(
        speech=f"Created project '{row['name']}' and set it active. id={row['id']}.",
        capability="project_os",
        project_id=row["id"],
        hud={"title": row["name"], "body": f"state={row['state']}\ngoal={row['goal']}"},
        evidence={"project": row, "context": ctx},
    )


def _list(pos) -> CapabilityResult:
    projects = pos.list_projects()
    active = pos.active_id()
    if not projects:
        return CapabilityResult(
            speech="No projects yet. Say 'create a new project for …' to start one.",
            capability="project_os",
            evidence={"projects": []},
        )
    lines = []
    for p in projects:
        mark = " (active)" if p["id"] == active else ""
        lines.append(f"- {p['name']} [{p['state']}]{mark} id={p['id']}")
    body = "\n".join(lines)
    return CapabilityResult(
        speech=f"You have {len(projects)} project(s). Active id={active or 'none'}.",
        capability="project_os",
        project_id=active,
        hud={"title": "Projects", "body": body},
        evidence={"projects": projects, "active_project_id": active},
    )


def _switch(pos, req, intent, text) -> CapabilityResult:
    ref = intent.project_ref or textparse.extract_project_ref_for_switch(text) or req.project_id
    if not ref:
        return _err("Which project should I switch to?")
    result = pos.switch(ref)
    proj = result["project"]
    ctx = result["context"]
    open_n = len(ctx.get("open_tasks") or [])
    return CapabilityResult(
        speech=f"Switched to '{proj['name']}'. {open_n} open task(s).",
        capability="project_os",
        project_id=proj["id"],
        hud={"title": proj["name"], "body": _ctx_summary(ctx)},
        evidence=result,
    )


def _continue(pos, req, intent, text) -> CapabilityResult:
    ref = intent.project_ref or textparse.extract_project_ref_for_switch(text) or req.project_id
    result = pos.continue_active(ref)
    proj = result["project"]
    ctx = result["context"]
    mem = ctx.get("recent_memory") or []
    tasks = ctx.get("open_tasks") or []
    bits = [f"Continuing '{proj['name']}' ({proj['state']})."]
    if tasks:
        bits.append("Open tasks: " + "; ".join(t["title"] for t in tasks[:5]))
    if mem:
        bits.append("Recent notes: " + "; ".join(m["text"][:80] for m in mem[:3]))
    return CapabilityResult(
        speech=" ".join(bits),
        capability="project_os",
        project_id=proj["id"],
        hud={"title": proj["name"], "body": _ctx_summary(ctx)},
        evidence=result,
    )


def _status(pos, req, intent, text) -> CapabilityResult:
    ref = intent.project_ref or req.project_id
    if ref:
        proj = pos.find_by_ref(ref)
    else:
        proj = pos.active_project()
        if not proj:
            return _err("No active project. Create or switch to one first.")
    ctx = pos.context_pack(proj["id"])
    return CapabilityResult(
        speech=f"Project '{proj['name']}' is {proj['state']}. "
               f"{len(ctx['open_tasks'])} open task(s), "
               f"{len(ctx['recent_memory'])} recent memory entries.",
        capability="project_os",
        project_id=proj["id"],
        hud={"title": proj["name"], "body": _ctx_summary(ctx)},
        evidence={"project": proj, "context": ctx},
    )


def _note(pos, req, intent, text, *, kind: str) -> CapabilityResult:
    proj = _require_active(pos, req)
    body = intent.notes if intent.notes and intent.notes not in ("deterministic", "ollama") else None
    body = body or textparse.extract_note_text(text)
    if not body:
        # Fall back to stripping the command prefix loosely
        body = text
    entry = pos.add_memory(proj["id"], body, kind=kind)
    return CapabilityResult(
        speech=f"Saved {kind} on '{proj['name']}'.",
        capability="project_os",
        project_id=proj["id"],
        evidence={"memory": entry},
    )


def _task_create(pos, req, intent, text) -> CapabilityResult:
    proj = _require_active(pos, req)
    title = textparse.extract_task_title(text)
    if not title:
        return _err("What task should I add? Example: 'Add a task to investigate the SPI driver.'")
    task = pos.add_task(proj["id"], title)
    return CapabilityResult(
        speech=f"Added task '{task['title']}' to '{proj['name']}'.",
        capability="project_os",
        project_id=proj["id"],
        evidence={"task": task},
    )


def _task_list(pos, req) -> CapabilityResult:
    proj = _require_active(pos, req)
    tasks = pos.list_tasks(proj["id"])
    if not tasks:
        return CapabilityResult(
            speech=f"No tasks in '{proj['name']}' yet.",
            capability="project_os",
            project_id=proj["id"],
            evidence={"tasks": []},
        )
    lines = [f"- [{t['state']}] {t['title']}" for t in tasks]
    return CapabilityResult(
        speech=f"{len(tasks)} task(s) in '{proj['name']}'.",
        capability="project_os",
        project_id=proj["id"],
        hud={"title": f"Tasks — {proj['name']}", "body": "\n".join(lines)},
        evidence={"tasks": tasks},
    )


def _task_update(pos, req, intent, text) -> CapabilityResult:
    proj = _require_active(pos, req)
    ref = textparse.extract_completed_task_ref(text)
    if not ref:
        return _err("Which task should I update?")
    task = pos.find_task_in_project(proj["id"], ref)
    # Default NL completion phrases → done
    new_state = "done"
    if "block" in text.lower():
        new_state = "blocked"
    elif "progress" in text.lower() or "start" in text.lower():
        new_state = "in_progress"
    updated = pos.update_task(task["id"], state=new_state)
    return CapabilityResult(
        speech=f"Task '{updated['title']}' is now {updated['state']}.",
        capability="project_os",
        project_id=proj["id"],
        evidence={"task": updated},
    )


def _checkpoint_create(pos, req) -> CapabilityResult:
    proj = _require_active(pos, req)
    cp = pos.checkpoint(proj["id"], label="manual")
    return CapabilityResult(
        speech=f"Checkpoint {cp['id']} created for '{proj['name']}'.",
        capability="project_os",
        project_id=proj["id"],
        evidence={"checkpoint": cp},
    )


def _checkpoint_restore(pos, req, intent, text) -> CapabilityResult:
    proj = _require_active(pos, req)
    cps = pos.list_checkpoints(proj["id"])
    if not cps:
        return _err(f"No checkpoints for '{proj['name']}'.")
    # Prefer explicit id in text; else latest
    cid = None
    for c in cps:
        if c["id"] in text:
            cid = c["id"]
            break
    cid = cid or cps[0]["id"]
    result = pos.restore_checkpoint(cid)
    return CapabilityResult(
        speech=f"Restored checkpoint {cid} for '{proj['name']}'.",
        capability="project_os",
        project_id=proj["id"],
        evidence=result,
    )


def _archive(pos, req, intent, text) -> CapabilityResult:
    ref = intent.project_ref or textparse.extract_project_ref_for_switch(text) or req.project_id
    if not ref:
        proj = pos.active_project()
        if not proj:
            return _err("Which project should I archive?")
        ref = proj["id"]
    proj = pos.find_by_ref(ref)
    row = pos.archive(proj["id"])
    return CapabilityResult(
        speech=f"Archived project '{row['name']}'.",
        capability="project_os",
        project_id=row["id"],
        evidence={"project": row},
    )


def _require_active(pos, req):
    if req.project_id:
        return pos.get(req.project_id)
    proj = pos.active_project()
    if not proj:
        raise NotFoundError("No active project. Create or switch to one first.")
    return proj


def _ctx_summary(ctx: dict) -> str:
    p = ctx.get("project") or {}
    lines = [
        f"state: {p.get('state')}",
        f"goal: {p.get('goal') or '(none)'}",
        "open tasks:",
    ]
    for t in ctx.get("open_tasks") or []:
        lines.append(f"  - [{t['state']}] {t['title']}")
    if not ctx.get("open_tasks"):
        lines.append("  (none)")
    lines.append("recent memory:")
    for m in ctx.get("recent_memory") or []:
        lines.append(f"  - ({m['kind']}) {m['text'][:120]}")
    if not ctx.get("recent_memory"):
        lines.append("  (none)")
    return "\n".join(lines)
