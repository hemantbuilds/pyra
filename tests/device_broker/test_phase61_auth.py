"""Phase 6.1 — L2 principal isolation (Broker-enforced)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_runtime.broker_session import AgentBrokerSession
from device_broker.broker import DeviceBroker
from device_broker.client import BrokerClient
from device_broker.permissions import ENGINEERING_OS_L2_TOOLS
from device_broker.policy import BrokerPolicy
from device_broker.types import CallContext
from project_os import ProjectOS


@pytest.fixture
def env(tmp_path):
    work = tmp_path / "PyraWork"
    work.mkdir()
    (work / "global").mkdir()
    (work / "projects").mkdir()
    pos = ProjectOS(work)
    proj = pos.create(name="P61", goal="auth")
    broker = DeviceBroker(BrokerPolicy(work_root=work), project_resolver=pos.active_project)
    executed = {"n": 0}

    def runner(*a, **k):
        executed["n"] += 1
        return {
            "exit_code": 0,
            "timed_out": False,
            "stdout": "ok",
            "stderr": "",
            "resolved_executable": "/usr/bin/west",
        }

    broker._build_runner = runner
    broker._serial_backend = lambda **kw: {"success": True, "data": b"x", "truncated": False}
    src = Path(proj["workspace_path"]) / "app"
    src.mkdir(parents=True)
    yield {
        "pos": pos,
        "proj": proj,
        "broker": broker,
        "untrusted": BrokerClient(broker),
        "eng": broker.create_engineering_client(),
        "src": src,
        "executed": executed,
    }
    broker.close()
    pos.close()


def _west_args(env):
    return {
        "board": "mimxrt1170_evk@B/mimxrt1176/cm7",
        "source_dir": str(env["src"]),
    }


def test_research_agent_l2_config_denied(env):
    session = AgentBrokerSession(
        env["untrusted"],
        agent_id="research",
        project_id=env["proj"]["id"],
        allowed_tools=["west_build", "get_system_info"],
        max_level="L2",
    )
    before = env["executed"]["n"]
    res = session.call("west_build", _west_args(env))
    assert res.status == "denied"
    assert env["executed"]["n"] == before


def test_generic_specialist_l2_denied(env):
    session = AgentBrokerSession(
        env["untrusted"],
        agent_id="echo",
        project_id=env["proj"]["id"],
        allowed_tools=["west_build"],
        max_level="L2",
    )
    before = env["executed"]["n"]
    res = session.call("west_build", _west_args(env))
    assert res.status == "denied"
    assert env["executed"]["n"] == before


def test_allowlist_alone_does_not_grant(env):
    # Untrusted client + allowlist via AgentBrokerSession still denied
    session = AgentBrokerSession(
        env["untrusted"],
        agent_id="generic",
        project_id=env["proj"]["id"],
        allowed_tools=list(ENGINEERING_OS_L2_TOOLS),
        max_level="L2",
    )
    before = env["executed"]["n"]
    assert session.call("west_build", _west_args(env)).status == "denied"
    assert env["executed"]["n"] == before


def test_principal_spoofing_denied(env):
    before = env["executed"]["n"]
    r = env["untrusted"].call(
        "west_build",
        _west_args(env),
        principal="engineering_os",
        max_level="L2",
        client="engineering_os",
        project_id=env["proj"]["id"],
    )
    assert r.status == "denied"
    assert "trusted L2 session" in (r.error or "").lower() or "session" in (r.error or "").lower()
    assert env["executed"]["n"] == before


def test_forged_session_id_denied(env):
    before = env["executed"]["n"]
    r = env["broker"].invoke(
        "west_build",
        _west_args(env),
        ctx=CallContext(
            principal="engineering_os",
            max_level="L2",
            client="engineering_os",
            project_id=env["proj"]["id"],
            session_id="deadbeef" * 4,
        ),
    )
    assert r.status == "denied"
    assert env["executed"]["n"] == before


def test_unknown_principal_untrusted_denied(env):
    before = env["executed"]["n"]
    r = env["untrusted"].call(
        "west_build",
        _west_args(env),
        principal="unknown",
        max_level="L2",
        project_id=env["proj"]["id"],
    )
    assert r.status == "denied"
    assert env["executed"]["n"] == before


def test_engineering_os_west_build_allowed(env):
    before = env["executed"]["n"]
    r = env["eng"].call("west_build", _west_args(env), project_id=env["proj"]["id"])
    assert r.ok
    assert r.data["success"] is True
    assert env["executed"]["n"] == before + 1


def test_engineering_os_serial_capture_allowed(env):
    r = env["eng"].call(
        "serial_capture_passive",
        {"device": "/dev/ttyACM0", "baudrate": 115200, "duration_s": 0.2},
        project_id=env["proj"]["id"],
    )
    assert r.ok
    assert r.data["tx_attempted"] is False


def test_engineering_os_unapproved_l2_tool_denied(env):
    # Create a hypothetical L2 tool grant gap: session only has ENGINEERING_OS_L2_TOOLS
    # Registering a new L2 tool name that isn't on the session allowlist
    from device_broker.permissions import PermissionLevel
    from device_broker.tools.registry import ToolSpec

    executed = {"n": 0}

    def handler(**kw):
        executed["n"] += 1
        return {"ok": True}

    env["broker"].registry.register(
        ToolSpec(
            name="future_l2_tool",
            description="not granted to eng OS",
            level=PermissionLevel.L2,
            category="test",
            handler=handler,
            input_schema={"type": "object", "properties": {}},
        )
    )
    r = env["eng"].call("future_l2_tool", {}, project_id=env["proj"]["id"])
    assert r.status == "denied"
    assert "allowlist" in (r.error or "").lower()
    assert executed["n"] == 0


def test_l3_still_denied(env):
    before = env["executed"]["n"]
    for tool in ("flash_firmware", "erase_flash", "mass_erase"):
        r = env["broker"].invoke(
            tool,
            {},
            ctx=CallContext(max_level="L3", principal="engineering_os", project_id=env["proj"]["id"]),
        )
        assert r.status == "denied"
    # Even trusted eng session cannot get L3 via claim
    r2 = env["eng"].call("flash_firmware", {}, project_id=env["proj"]["id"], max_level="L3")
    assert r2.status == "denied"
    assert env["executed"]["n"] == before


def test_l0_l1_still_work_on_untrusted(env):
    r = env["untrusted"].call(
        "get_system_info",
        {},
        max_level="L0",
        project_id=env["proj"]["id"],
    )
    assert r.ok
    r2 = env["untrusted"].call(
        "write_text_file",
        {"path": "note.txt", "content": "hi"},
        max_level="L1",
        project_id=env["proj"]["id"],
    )
    assert r2.ok
