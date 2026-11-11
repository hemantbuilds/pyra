"""Phase 3 Device Broker security and integration tests."""

from __future__ import annotations

import json
import os
import time
from io import StringIO
from pathlib import Path

import pytest

from device_broker.audit import AuditLog
from device_broker.broker import DeviceBroker
from device_broker.mcp.server import McpStdioServer
from device_broker.paths import PathJailError
from device_broker.permissions import PermissionLevel
from device_broker.policy import BrokerPolicy
from device_broker.redaction import redact_text, redact_value
from device_broker.types import CallContext
from master import capabilities
from master.broker_service import reset_broker
from master.contracts import IntentKind, InteractRequest
from master.model_gateway import deterministic_intent
from master.orchestrator import Orchestrator
from master.project_service import reset_project_os
from project_os import ProjectOS


@pytest.fixture
def work(tmp_path):
    root = tmp_path / "PyraWork"
    root.mkdir()
    (root / "global").mkdir()
    (root / "projects").mkdir()
    return root


@pytest.fixture
def pos(work):
    return ProjectOS(work)


@pytest.fixture
def broker(work, pos):
    # Reuse singleton (same audit DB as Master); do not close a second connection.
    policy_broker = reset_broker(work, project_resolver=pos.active_project)
    policy_broker.policy.command_timeout_s = 2.0
    policy_broker.policy.max_command_output_bytes = 1024
    return policy_broker


@pytest.fixture(autouse=True)
def _isolate(work, pos):
    capabilities.reset_registry()
    reset_project_os(work)
    reset_broker(work, project_resolver=pos.active_project)
    capabilities.bootstrap_builtin_capabilities()
    yield
    capabilities.reset_registry()


def _L0(broker, tool, **args):
    return broker.invoke(tool, args, ctx=CallContext(max_level="L0", principal="test"))


def _L1(broker, tool, **args):
    return broker.invoke(tool, args, ctx=CallContext(max_level="L1", principal="test"))


# ── 1. Level 0 read-only ─────────────────────────────────────────────────────

def test_l0_list_and_read(broker, pos, work):
    proj = pos.create("Alpha", goal="a", make_active=True)
    ws = Path(proj["workspace_path"])
    (ws / "notes.txt").write_text("hello-alpha", encoding="utf-8")
    r = _L0(broker, "list_directory", path=".")
    assert r.ok
    names = [e["name"] for e in r.data["entries"]]
    assert "notes.txt" in names
    r2 = _L0(broker, "read_text_file", path="notes.txt")
    assert r2.ok and "hello-alpha" in r2.data["content"]


def test_l0_system_info(broker):
    r = _L0(broker, "get_system_info")
    assert r.ok and r.data.get("system")
    r2 = _L0(broker, "get_platform_info")
    assert r2.ok and "python" in r2.data


# ── 2. Level 1 writes ────────────────────────────────────────────────────────

def test_l1_create_and_write(broker, pos):
    pos.create("Alpha", make_active=True)
    denied = _L0(broker, "create_directory", path="firmware")
    assert not denied.ok and denied.status == "denied"
    ok = _L1(broker, "create_directory", path="firmware")
    assert ok.ok
    w = _L1(broker, "write_text_file", path="firmware/readme.txt", content="fw", overwrite=True)
    assert w.ok
    r = _L0(broker, "read_text_file", path="firmware/readme.txt")
    assert r.data["content"] == "fw"


# ── 3. Unauthorized writes ───────────────────────────────────────────────────

def test_deny_write_at_l0(broker, pos):
    pos.create("Alpha", make_active=True)
    r = _L0(broker, "write_text_file", path="x.txt", content="nope")
    assert not r.ok and r.status == "denied"


# ── 4. Path traversal ────────────────────────────────────────────────────────

def test_path_traversal_denied(broker, pos, work):
    pos.create("Alpha", make_active=True)
    r = _L1(broker, "write_text_file", path="../../escape.txt", content="x")
    assert not r.ok
    assert not (work.parent / "escape.txt").exists()


# ── 5. Symlink escape ────────────────────────────────────────────────────────

def test_symlink_escape_denied(broker, pos, tmp_path, work):
    pos.create("Alpha", make_active=True)
    outside = tmp_path / "outside_secret.txt"
    outside.write_text("secret", encoding="utf-8")
    ws = Path(pos.active_project()["workspace_path"])
    link = ws / "leak"
    link.symlink_to(outside)
    r = _L0(broker, "read_text_file", path="leak")
    assert not r.ok
    assert "outside" in (r.error or "").lower() or "approved" in (r.error or "").lower()


# ── 6. Outside approved workspace ────────────────────────────────────────────

def test_outside_workspace_denied(broker, pos, tmp_path):
    pos.create("Alpha", make_active=True)
    foreign = tmp_path / "foreign.txt"
    foreign.write_text("no", encoding="utf-8")
    r = _L0(broker, "read_text_file", path=str(foreign))
    assert not r.ok


# ── 7. Cross-project access ──────────────────────────────────────────────────

def test_cross_project_isolation(broker, pos):
    a = pos.create("ProjectA", make_active=True)
    _L1(broker, "write_text_file", path="a_only.txt", content="A", overwrite=True)
    b = pos.create("ProjectB", make_active=True)
    _L1(broker, "write_text_file", path="b_only.txt", content="B", overwrite=True)
    # Active is B — cannot read A's workspace file by absolute path outside roots
    a_file = Path(a["workspace_path"]) / "a_only.txt"
    r = _L0(broker, "read_text_file", path=str(a_file))
    assert not r.ok
    # B file works
    r2 = _L0(broker, "read_text_file", path="b_only.txt")
    assert r2.ok and r2.data["content"] == "B"


# ── 8–9. Unauthorized commands / argv validation ─────────────────────────────

def test_unauthorized_command_denied(broker, pos):
    pos.create("Alpha", make_active=True)
    r = _L1(broker, "run_allowed_command", argv=["rm", "-rf", "/"])
    assert not r.ok
    assert "allowlist" in (r.error or "").lower() or "not permitted" in (r.error or "").lower()
    r2 = _L1(broker, "run_allowed_command", argv=["sudo", "id"])
    assert not r2.ok
    r3 = _L1(broker, "run_allowed_command", argv=["python3", "--version", ";", "id"])
    assert not r3.ok


def test_allowed_version_command(broker, pos):
    pos.create("Alpha", make_active=True)
    r = _L1(broker, "run_allowed_command", argv=["python3", "--version"])
    assert r.ok
    assert r.data["exit_code"] == 0
    assert "Python" in r.data["stdout"] or "python" in r.data["stdout"].lower()


# ── 10. Timeout ──────────────────────────────────────────────────────────────

def test_command_timeout(broker, pos, work):
    # Inject a slow allowlisted command for this test only
    from device_broker.policy import CommandSpec

    broker.policy.commands.append(
        CommandSpec("sleep_test", ("sleep",), "test sleep", level="L1", max_args=2)
    )
    broker.policy.command_timeout_s = 0.3
    pos.create("Alpha", make_active=True)
    r = _L1(broker, "run_allowed_command", argv=["sleep", "2"])
    assert not r.ok
    assert "timed out" in (r.error or "").lower()


# ── 11. Output size limit ────────────────────────────────────────────────────

def test_output_size_limit(broker, pos):
    from device_broker.policy import CommandSpec

    broker.policy.max_command_output_bytes = 32
    # python3 -c is NOT allowlisted — use uname which is small, or add a yes-like probe.
    # Instead write a tiny custom allowlisted echo via python3 --version (small) and
    # verify truncation fields exist; for forced truncation, allow python3 -c carefully? No.
    # Add printf allowlist for test:
    broker.policy.commands.append(
        CommandSpec("python_c", ("python3", "-c"), "test", level="L1", max_args=3)
    )
    pos.create("Alpha", make_active=True)
    r = _L1(broker, "run_allowed_command", argv=["python3", "-c", "print('X'*200)"])
    assert r.ok
    assert r.data["stdout_truncated"] is True
    assert len(r.data["stdout"].encode()) <= 32


# ── 12–13. Audit success and denial ──────────────────────────────────────────

def test_audit_success_and_denial(broker, pos):
    pos.create("Alpha", make_active=True)
    ok = _L0(broker, "get_system_info")
    assert ok.ok and ok.operation_id
    bad = _L1(broker, "run_allowed_command", argv=["bash", "-c", "id"])
    assert not bad.ok
    hist = _L0(broker, "get_execution_history", limit=50)
    assert hist.ok
    statuses = {e["status"] for e in hist.data["events"]}
    assert "completed" in statuses
    assert "denied" in statuses


# ── 14. Secret redaction ─────────────────────────────────────────────────────

def test_secret_redaction():
    assert "***" in redact_text("Authorization: Bearer abcdef.secret.token")
    assert redact_value({"token": "sekrit", "path": "/tmp"})["token"] == "***"
    assert "password=***" in redact_text("password=hunter2") or "***" in redact_text("password=hunter2")


# ── 15. MCP registration / invocation ────────────────────────────────────────

def test_mcp_tools_list_and_call(broker, pos):
    pos.create("Alpha", make_active=True)
    infile = StringIO()
    outfile = StringIO()
    server = McpStdioServer(broker, infile=infile, outfile=outfile)

    server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    server.handle_message({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "get_system_info",
            "arguments": {},
            "_meta": {"max_level": "L0", "principal": "mcp-test"},
        },
    })
    lines = [json.loads(l) for l in outfile.getvalue().strip().splitlines()]
    assert lines[0]["result"]["serverInfo"]["name"] == "pyra-device-broker"
    names = [t["name"] for t in lines[1]["result"]["tools"]]
    assert "list_directory" in names
    assert "run_allowed_command" in names
    assert lines[2]["result"]["isError"] is False
    payload = lines[2]["result"]["structuredContent"]
    assert payload["ok"] is True


# ── 16. Master integration ───────────────────────────────────────────────────

def test_master_device_intents(monkeypatch, pos):
    pos.create("Drone", make_active=True)
    orch = Orchestrator()
    monkeypatch.setattr(orch.gateway, "ollama_reachable", lambda: False)

    r = orch.handle(InteractRequest(text="What operating system is PYRA running on?", source="cli"))
    assert r.capability == "device_broker"
    assert r.status == "ok"

    r2 = orch.handle(InteractRequest(text="Create a directory called firmware inside this project.", source="cli"))
    assert r2.capability == "device_broker"
    assert r2.status == "ok"

    r3 = orch.handle(InteractRequest(text="Show the files in my active project workspace.", source="cli"))
    assert r3.capability == "device_broker"
    assert r3.status == "ok"
    names = [e["name"] for e in r3.evidence["data"]["entries"]]
    assert "firmware" in names

    r4 = orch.handle(InteractRequest(text="Run the approved version-check command.", source="cli"))
    assert r4.capability == "device_broker"
    assert r4.status == "ok"


def test_deterministic_device_phrases():
    assert deterministic_intent("Show the files in my active project workspace.").kind == IntentKind.DEVICE_LIST_DIR
    assert deterministic_intent("Which embedded toolchains are installed?").kind == IntentKind.DEVICE_TOOLCHAINS
    assert deterministic_intent("What operating system is PYRA running on?").kind == IntentKind.DEVICE_SYSTEM_INFO


def test_fastapi_broker_and_dot(monkeypatch, pos):
    from fastapi.testclient import TestClient
    from master import api as api_mod

    pos.create("Alpha", make_active=True)
    monkeypatch.setattr(api_mod.gateway, "ollama_reachable", lambda: False)
    client = TestClient(api_mod.app)

    r = client.get("/broker/v1/tools")
    assert r.status_code == 200
    assert any(t["name"] == "list_directory" for t in r.json()["tools"])

    r = client.post(
        "/broker/v1/call",
        json={"tool": "get_system_info", "arguments": {}, "max_level": "L0"},
    )
    assert r.status_code == 200 and r.json()["ok"] is True

    r = client.post(
        "/dot/v1/interact",
        json={"text": "list broker tools", "source": "mark", "metadata": {"from_mark": True}},
    )
    assert r.status_code == 200
    assert r.json()["capability"] == "device_broker"


def test_l2_l3_not_granted(broker, pos):
    pos.create("Alpha", make_active=True)
    # Claiming L3 still cannot call unregistered flash tool
    r = broker.invoke(
        "flash_firmware",
        {},
        ctx=CallContext(max_level="L3", principal="evil"),
    )
    assert not r.ok and r.status == "denied"
    # Claiming L3 is capped at Phase 6 MAX_GRANTABLE (L2); L1 write still allowed
    r2 = broker.invoke(
        "write_text_file",
        {"path": "ok.txt", "content": "x"},
        ctx=CallContext(max_level="L3", principal="test"),
    )
    assert r2.ok  # L1 tool allowed under capped L2 ceiling
