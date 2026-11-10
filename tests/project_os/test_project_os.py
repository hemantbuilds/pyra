"""Phase 2 Project OS unit + Master integration tests."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from master import api as api_mod
from master import capabilities
from master.contracts import IntentKind, InteractRequest
from master.model_gateway import deterministic_intent
from master.orchestrator import Orchestrator
from master.project_service import reset_project_os
from project_os import ProjectOS
from project_os.errors import NotFoundError, ValidationError
from project_os.textparse import extract_project_name_for_create


@pytest.fixture
def work(tmp_path):
    root = tmp_path / "PyraWork"
    capabilities.reset_registry()
    pos = reset_project_os(root)
    yield pos
    pos.close()
    capabilities.reset_registry()


@pytest.fixture
def orch(work, monkeypatch):
    o = Orchestrator()
    monkeypatch.setattr(o.gateway, "ollama_reachable", lambda: False)
    return o


def test_extract_create_name():
    assert extract_project_name_for_create(
        "Create a new drone development project."
    ) == "drone development"
    assert extract_project_name_for_create(
        "create a new project for hardware bring-up"
    ) == "hardware bring-up"


def test_create_unique_ids(work: ProjectOS):
    a = work.create("Drone Development")
    b = work.create("Hardware Bring-up")
    assert a["id"] != b["id"]
    assert a["slug"] != b["slug"]
    assert (work.work_root / "projects" / a["id"] / "PROJECT.md").exists()
    assert (work.work_root / "pyra.db").exists()


def test_list_and_get(work: ProjectOS):
    work.create("Alpha")
    work.create("Beta")
    listed = work.list_projects()
    assert len(listed) == 2
    got = work.get(listed[0]["id"])
    assert got["name"] in ("Alpha", "Beta")


def test_switch_and_isolation(work: ProjectOS):
    drone = work.create("Drone Development", make_active=True)
    work.add_task(drone["id"], "Design airframe")
    work.add_memory(drone["id"], "Use 4S battery", kind="decision")

    hw = work.create("Hardware Bring-up", make_active=True)
    work.add_task(hw["id"], "Enumerate USB devices")
    work.add_memory(hw["id"], "Do not assume Arduino", kind="note")

    # Active should be hardware
    assert work.active_id() == hw["id"]
    assert len(work.list_tasks(hw["id"])) == 1
    assert work.list_tasks(hw["id"])[0]["title"] == "Enumerate USB devices"
    assert work.list_memory(drone["id"])[0]["text"] == "Use 4S battery"
    assert work.list_memory(hw["id"])[0]["text"] == "Do not assume Arduino"

    switched = work.switch("drone development")
    assert switched["project"]["id"] == drone["id"]
    ctx = switched["context"]
    assert ctx["project"]["name"] == "Drone Development"
    assert ctx["open_tasks"][0]["title"] == "Design airframe"
    assert all("USB" not in t["title"] for t in ctx["open_tasks"])
    assert all("Arduino" not in m["text"] for m in ctx["recent_memory"])


def test_task_update(work: ProjectOS):
    p = work.create("Tasky")
    t = work.add_task(p["id"], "Investigate SPI driver")
    updated = work.update_task(t["id"], state="done")
    assert updated["state"] == "done"


def test_checkpoint_and_restore(work: ProjectOS):
    p = work.create("Checkpoint Lab")
    work.add_task(p["id"], "Task A")
    work.add_memory(p["id"], "Decision A", kind="decision")
    cp = work.checkpoint(p["id"], label="before-change")
    assert (work.work_root / "projects" / p["id"] / "checkpoints" / cp["id"] / "snapshot.json").exists()

    work.add_task(p["id"], "Task B")
    work.update_task(work.list_tasks(p["id"])[0]["id"], state="done")
    assert len(work.list_tasks(p["id"])) == 2

    restored = work.restore_checkpoint(cp["id"])
    tasks = work.list_tasks(p["id"])
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Task A"
    assert tasks[0]["state"] == "pending"
    mem = work.list_memory(p["id"])
    assert len(mem) == 1
    assert mem[0]["text"] == "Decision A"
    assert restored["project"]["id"] == p["id"]


def test_active_persists_across_reopen(work: ProjectOS, tmp_path):
    root = work.work_root
    p = work.create("Persist Me")
    work.add_task(p["id"], "Stay here")
    work.close()

    again = ProjectOS(root)
    assert again.active_id() == p["id"]
    assert again.list_tasks(p["id"])[0]["title"] == "Stay here"
    cont = again.continue_active()
    assert cont["project"]["id"] == p["id"]
    again.close()


def test_invalid_ops(work: ProjectOS):
    with pytest.raises(ValidationError):
        work.create("")
    with pytest.raises(NotFoundError):
        work.get("does-not-exist")
    with pytest.raises(NotFoundError):
        work.switch("missing project")


def test_interrupted_create_consistency(work: ProjectOS):
    """DB row and filesystem tree stay paired for successful creates."""
    p = work.create("Consistent")
    root = work.work_root / "projects" / p["id"]
    assert root.exists()
    state = json.loads((root / "state.json").read_text())
    assert state["id"] == p["id"]


def test_deterministic_project_intents():
    assert deterministic_intent("Create a new drone development project.").kind == IntentKind.PROJECT_CREATE
    assert deterministic_intent("Show my active projects").kind == IntentKind.PROJECT_LIST
    assert deterministic_intent("Switch to the hardware bring-up project").kind == IntentKind.PROJECT_SWITCH
    assert deterministic_intent("Add a task to investigate the SPI driver").kind == IntentKind.TASK_CREATE
    assert deterministic_intent("Mark the SPI investigation as completed").kind == IntentKind.TASK_UPDATE
    assert deterministic_intent("Save this engineering decision: use SPI mode 0").kind == IntentKind.PROJECT_DECISION
    assert deterministic_intent("Create a checkpoint before making changes").kind == IntentKind.CHECKPOINT_CREATE


def test_master_integration_workflow(orch, work: ProjectOS):
    r1 = orch.handle(InteractRequest(text="Create a new drone development project.", source="cli"))
    assert r1.status == "ok"
    assert r1.capability == "project_os"
    assert r1.project_id
    drone_id = r1.project_id

    r2 = orch.handle(InteractRequest(text="Add a task to investigate the SPI driver", source="cli"))
    assert r2.status == "ok"
    assert work.list_tasks(drone_id)[0]["title"].lower().find("spi") >= 0

    r3 = orch.handle(InteractRequest(
        text="Save this engineering decision: prefer hardware SPI over bit-bang",
        source="cli",
    ))
    assert r3.status == "ok"

    r4 = orch.handle(InteractRequest(text="Create a new hardware bring-up project", source="cli"))
    assert r4.status == "ok"
    hw_id = r4.project_id
    assert hw_id != drone_id

    orch.handle(InteractRequest(text="Add a task to enumerate USB devices", source="cli"))
    orch.handle(InteractRequest(text="Save a note: discovery must not assume Arduino", source="cli"))

    listed = orch.handle(InteractRequest(text="Show my active projects", source="cli"))
    assert listed.status == "ok"
    assert len(listed.evidence["projects"]) == 2

    sw = orch.handle(InteractRequest(text="Switch to the drone development project", source="cli"))
    assert sw.project_id == drone_id
    ctx = sw.evidence["context"]
    assert any("SPI" in t["title"] for t in ctx["open_tasks"])
    assert not any("USB" in t["title"] for t in ctx["open_tasks"])

    orch.handle(InteractRequest(text="Create a checkpoint before making changes", source="cli"))
    orch.handle(InteractRequest(text="Switch to the hardware bring-up project", source="cli"))
    orch.handle(InteractRequest(text="Create a checkpoint before making changes", source="cli"))

    # Restart simulation
    root = work.work_root
    work.close()
    capabilities.reset_registry()
    reset_project_os(root)
    orch2 = Orchestrator()
    # force deterministic
    orch2.gateway.ollama_reachable = lambda: False  # type: ignore

    listed2 = orch2.handle(InteractRequest(text="list my projects", source="cli"))
    assert len(listed2.evidence["projects"]) == 2
    cont = orch2.handle(InteractRequest(text="Continue my drone development project", source="cli"))
    assert cont.status == "ok"
    assert "drone" in cont.speech.lower()


def test_fastapi_project_via_dot(work, monkeypatch):
    capabilities.reset_registry()
    reset_project_os(work.work_root)
    monkeypatch.setattr(api_mod.gateway, "ollama_reachable", lambda: False)
    # Recreate orchestrator bindings used by API module
    from master.orchestrator import Orchestrator
    from integrations.dot.gateway import DotGateway

    api_mod.orchestrator = Orchestrator()
    api_mod.dot = DotGateway(api_mod.orchestrator)
    monkeypatch.setattr(api_mod.orchestrator.gateway, "ollama_reachable", lambda: False)

    client = TestClient(api_mod.app)
    r = client.post(
        "/dot/v1/interact",
        json={"text": "Create a new drone development project.", "source": "mark",
              "metadata": {"from_mark": True}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["capability"] == "project_os"
    assert body["project_id"]
