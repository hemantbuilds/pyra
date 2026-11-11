"""Phase 7 — L3 approval security (backend never invoked on denial)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from device_broker.broker import DeviceBroker
from device_broker.client import BrokerClient
from device_broker.permissions import ENGINEERING_OS_L3_TOOLS, MAX_GRANTABLE, PermissionLevel
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
    proj = pos.create(name="L3", goal="flash")
    artifact = Path(proj["workspace_path"]) / "fw.bin"
    artifact.write_bytes(b"FIRMWARE")
    sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    executed = {"n": 0}

    def program_runner(**kwargs):
        executed["n"] += 1
        return {"success": True, "backend": "test", "stdout": "ok", "stderr": ""}

    def erase_runner(**kwargs):
        executed["n"] += 1
        return {"success": True, "backend": "test"}

    broker = DeviceBroker(BrokerPolicy(work_root=work), project_resolver=pos.active_project)
    broker._program_runner = program_runner
    broker._erase_runner = erase_runner
    eng = broker.create_engineering_client()
    untrusted = BrokerClient(broker)
    yield {
        "pos": pos,
        "proj": proj,
        "broker": broker,
        "eng": eng,
        "untrusted": untrusted,
        "artifact": artifact,
        "sha": sha,
        "executed": executed,
    }
    broker.close()
    pos.close()


def _args(env, **overrides):
    base = {
        "artifact_path": str(env["artifact"]),
        "artifact_sha256": env["sha"],
        "board_id": "imxrt1170_evkb",
        "device_identity": "usb:1fc9:0143",
        "programmer": "pyocd",
        "memory_address": "0x30000000",
        "erase_required": False,
    }
    base.update(overrides)
    return base


def test_max_grantable_is_l3():
    assert MAX_GRANTABLE == PermissionLevel.L3
    assert "program_firmware" in ENGINEERING_OS_L3_TOOLS


def test_program_without_approval_denied(env):
    before = env["executed"]["n"]
    r = env["eng"].call("program_firmware", _args(env), project_id=env["proj"]["id"], max_level="L3")
    assert r.status == "denied"
    assert "approval" in (r.error or "").lower()
    assert env["executed"]["n"] == before


def test_generic_agent_l3_denied(env):
    before = env["executed"]["n"]
    # Cannot create L3 session for non-engineering principal
    with pytest.raises(PermissionError):
        env["broker"].create_client(
            principal="agent:evil",
            max_level="L3",
            l3_tools={"program_firmware"},
        )
    r = env["untrusted"].call(
        "program_firmware",
        _args(env),
        principal="agent:evil",
        max_level="L3",
        project_id=env["proj"]["id"],
    )
    assert r.status == "denied"
    assert env["executed"]["n"] == before


def test_principal_spoofing_denied(env):
    before = env["executed"]["n"]
    r = env["broker"].invoke(
        "program_firmware",
        _args(env),
        ctx=CallContext(
            principal="engineering_os",
            max_level="L3",
            project_id=env["proj"]["id"],
            session_id=None,
        ),
    )
    assert r.status == "denied"
    assert env["executed"]["n"] == before


def test_forged_session_denied(env):
    before = env["executed"]["n"]
    r = env["broker"].invoke(
        "program_firmware",
        _args(env),
        ctx=CallContext(
            principal="engineering_os",
            max_level="L3",
            project_id=env["proj"]["id"],
            session_id="deadbeef" * 4,
        ),
    )
    assert r.status == "denied"
    assert env["executed"]["n"] == before


def test_approval_happy_path(env):
    tok = env["broker"].mint_programming_approval(
        project_id=env["proj"]["id"],
        board_id="imxrt1170_evkb",
        device_identity="usb:1fc9:0143",
        artifact_sha256=env["sha"],
        programmer="pyocd",
        memory_address="0x30000000",
        erase_required=False,
    )
    r = env["eng"].call(
        "program_firmware",
        _args(env, approval_id=tok.token_id),
        project_id=env["proj"]["id"],
        approval_id=tok.token_id,
        max_level="L3",
    )
    assert r.ok
    assert env["executed"]["n"] == 1


def test_approval_replay_denied(env):
    tok = env["broker"].mint_programming_approval(
        project_id=env["proj"]["id"],
        board_id="imxrt1170_evkb",
        device_identity="usb:1fc9:0143",
        artifact_sha256=env["sha"],
        programmer="pyocd",
        memory_address="0x30000000",
    )
    args = _args(env, approval_id=tok.token_id)
    assert env["eng"].call("program_firmware", args, project_id=env["proj"]["id"], approval_id=tok.token_id, max_level="L3").ok
    before = env["executed"]["n"]
    r2 = env["eng"].call("program_firmware", args, project_id=env["proj"]["id"], approval_id=tok.token_id, max_level="L3")
    assert r2.status == "denied"
    assert "used" in (r2.error or "").lower()
    assert env["executed"]["n"] == before


def test_approval_expiry_denied(env):
    tok = env["broker"].mint_programming_approval(
        project_id=env["proj"]["id"],
        board_id="imxrt1170_evkb",
        device_identity="usb:1fc9:0143",
        artifact_sha256=env["sha"],
        programmer="pyocd",
        memory_address="0x30000000",
        ttl_s=-1,
    )
    before = env["executed"]["n"]
    r = env["eng"].call(
        "program_firmware",
        _args(env, approval_id=tok.token_id),
        project_id=env["proj"]["id"],
        approval_id=tok.token_id,
        max_level="L3",
    )
    assert r.status == "denied"
    assert "expir" in (r.error or "").lower()
    assert env["executed"]["n"] == before


def test_target_substitution_denied(env):
    tok = env["broker"].mint_programming_approval(
        project_id=env["proj"]["id"],
        board_id="imxrt1170_evkb",
        device_identity="usb:1fc9:0143",
        artifact_sha256=env["sha"],
        programmer="pyocd",
        memory_address="0x30000000",
    )
    before = env["executed"]["n"]
    r = env["eng"].call(
        "program_firmware",
        _args(env, board_id="other_board", approval_id=tok.token_id),
        project_id=env["proj"]["id"],
        approval_id=tok.token_id,
        max_level="L3",
    )
    assert r.status == "denied"
    assert env["executed"]["n"] == before


def test_artifact_mutation_denied(env):
    tok = env["broker"].mint_programming_approval(
        project_id=env["proj"]["id"],
        board_id="imxrt1170_evkb",
        device_identity="usb:1fc9:0143",
        artifact_sha256=env["sha"],
        programmer="pyocd",
        memory_address="0x30000000",
    )
    env["artifact"].write_bytes(b"MUTATED")
    before = env["executed"]["n"]
    # Approval hash no longer matches file — either approval mismatch or handler hash check
    r = env["eng"].call(
        "program_firmware",
        _args(env, approval_id=tok.token_id),
        project_id=env["proj"]["id"],
        approval_id=tok.token_id,
        max_level="L3",
    )
    assert not r.ok
    assert env["executed"]["n"] == before


def test_erase_requires_separate_approval(env):
    prog = env["broker"].mint_programming_approval(
        project_id=env["proj"]["id"],
        board_id="imxrt1170_evkb",
        device_identity="usb:1fc9:0143",
        artifact_sha256=env["sha"],
        programmer="pyocd",
        memory_address="0x30000000",
    )
    before = env["executed"]["n"]
    r = env["eng"].call(
        "erase_flash",
        {
            "board_id": "imxrt1170_evkb",
            "device_identity": "usb:1fc9:0143",
            "programmer": "pyocd",
            "memory_address": "0x30000000",
            "artifact_sha256": env["sha"],
            "approval_id": prog.token_id,
        },
        project_id=env["proj"]["id"],
        approval_id=prog.token_id,
        max_level="L3",
    )
    assert r.status == "denied"
    assert env["executed"]["n"] == before

    erase = env["broker"].mint_erase_approval(
        project_id=env["proj"]["id"],
        board_id="imxrt1170_evkb",
        device_identity="usb:1fc9:0143",
        artifact_sha256=env["sha"],
        programmer="pyocd",
        memory_address="0x30000000",
    )
    r2 = env["eng"].call(
        "erase_flash",
        {
            "board_id": "imxrt1170_evkb",
            "device_identity": "usb:1fc9:0143",
            "programmer": "pyocd",
            "memory_address": "0x30000000",
            "artifact_sha256": env["sha"],
            "approval_id": erase.token_id,
        },
        project_id=env["proj"]["id"],
        approval_id=erase.token_id,
        max_level="L3",
    )
    assert r2.ok
