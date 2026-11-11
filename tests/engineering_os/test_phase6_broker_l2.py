"""Phase 6 — Device Broker L2 build/serial tools + L3 denial."""

from __future__ import annotations

from pathlib import Path

import pytest

from device_broker.broker import DeviceBroker
from device_broker.client import BrokerClient
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
    proj = pos.create(name="L2Proj", goal="phase6")
    broker = DeviceBroker(BrokerPolicy(work_root=work), project_resolver=pos.active_project)
    client = BrokerClient(broker)  # untrusted
    eng = broker.create_engineering_client()
    yield pos, proj, broker, client, eng
    broker.close()
    pos.close()


def test_west_build_requires_l2(env):
    pos, proj, broker, client, eng = env
    ws = proj["workspace_path"]
    Path(ws, "app").mkdir(parents=True)
    (Path(ws) / "app" / "CMakeLists.txt").write_text("x")

    r = eng.call(
        "west_build",
        {"board": "mimxrt1170_evk@B/mimxrt1176/cm7", "source_dir": f"{ws}/app"},
        max_level="L1",
        project_id=proj["id"],
    )
    assert r.status == "denied"
    assert r.ok is False


def test_west_build_success_mocked(env):
    pos, proj, broker, client, eng = env
    ws = proj["workspace_path"]
    src = Path(ws) / "app"
    src.mkdir(parents=True)
    (src / "CMakeLists.txt").write_text("x")
    calls = {"n": 0}

    def runner(argv, cwd, timeout, env_map):
        calls["n"] += 1
        assert argv[0] == "west"
        assert argv[1] == "build"
        assert "-b" in argv
        assert str(src) in argv
        build = src / "build" / "zephyr"
        build.mkdir(parents=True)
        (build / "zephyr.elf").write_text("elf")
        return {
            "exit_code": 0,
            "timed_out": False,
            "stdout": "Built target",
            "stderr": "",
            "resolved_executable": "/usr/bin/west",
        }

    broker._build_runner = runner
    r = eng.call(
        "west_build",
        {"board": "mimxrt1170_evk@B/mimxrt1176/cm7", "source_dir": str(src)},
        project_id=proj["id"],
    )
    assert r.ok and r.data["success"] is True
    assert r.data["flash_attempted"] is False
    assert r.data["exit_code"] == 0
    assert calls["n"] == 1
    assert any(str(p).endswith("zephyr.elf") for p in r.data["artifacts"])
    # Audit trail
    hist = broker.audit.recent(limit=20)
    assert any(e.get("tool") == "west_build" and e.get("status") == "completed" for e in hist)


def test_west_build_failure_and_timeout(env):
    pos, proj, broker, client, eng = env
    ws = proj["workspace_path"]
    src = Path(ws) / "app"
    src.mkdir(parents=True)

    broker._build_runner = lambda *a, **k: {
        "exit_code": 1, "timed_out": False, "stdout": "", "stderr": "error: fail",
        "resolved_executable": "/usr/bin/west",
    }
    r = eng.call(
        "west_build",
        {"board": "mimxrt1170_evk@B/mimxrt1176/cm7", "source_dir": str(src)},
        project_id=proj["id"],
    )
    assert r.ok  # tool completed; success flag false
    assert r.data["success"] is False

    broker._build_runner = lambda *a, **k: {
        "exit_code": -1, "timed_out": True, "stdout": "", "stderr": "timeout",
        "resolved_executable": "/usr/bin/west",
    }
    r2 = eng.call(
        "west_build",
        {"board": "mimxrt1170_evk@B/mimxrt1176/cm7", "source_dir": str(src)},
        project_id=proj["id"],
    )
    assert r2.data["timed_out"] is True
    assert r2.data["success"] is False


def test_west_build_rejects_bad_board_and_metachar(env):
    pos, proj, broker, client, eng = env
    ws = proj["workspace_path"]
    src = Path(ws) / "app"
    src.mkdir(parents=True)
    broker._build_runner = lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not run"))

    r = eng.call(
        "west_build",
        {"board": "evil;rm", "source_dir": str(src)},
        project_id=proj["id"],
    )
    assert r.status in ("denied", "failed")

    r2 = eng.call(
        "west_build",
        {"board": "../escape", "source_dir": str(src)},
        project_id=proj["id"],
    )
    assert not r2.ok


def test_west_build_path_jail(env):
    pos, proj, broker, client, eng = env
    broker._build_runner = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no"))
    r = eng.call(
        "west_build",
        {"board": "mimxrt1170_evk@B/mimxrt1176/cm7", "source_dir": "/etc"},
        project_id=proj["id"],
    )
    assert r.status == "denied"


def test_serial_capture_mocked(env):
    pos, proj, broker, client, eng = env

    def backend(**kw):
        assert kw["device"].startswith("/dev/ttyACM")
        assert kw["baudrate"] == 115200
        return {"success": True, "data": b"hello-uart", "truncated": False}

    broker._serial_backend = backend
    r = eng.call(
        "serial_capture_passive",
        {"device": "/dev/ttyACM0", "baudrate": 115200, "duration_s": 0.5},
        project_id=proj["id"],
    )
    assert r.ok
    assert r.data["bytes_captured"] == 10
    assert r.data["tx_attempted"] is False


def test_serial_invalid_baud_and_device(env):
    pos, proj, broker, client, eng = env
    broker._serial_backend = lambda **kw: {"success": True, "data": b""}
    r = eng.call(
        "serial_capture_passive",
        {"device": "/dev/ttyACM0", "baudrate": 123},
        project_id=proj["id"],
    )
    assert not r.ok

    r2 = eng.call(
        "serial_capture_passive",
        {"device": "/etc/passwd", "baudrate": 115200},
        project_id=proj["id"],
    )
    assert r2.status == "denied"


def test_l3_flash_erase_denied_no_side_effect(env):
    pos, proj, broker, client, eng = env
    executed = {"n": 0}
    broker._build_runner = lambda *a, **k: executed.__setitem__("n", executed["n"] + 1) or {
        "exit_code": 0, "stdout": "", "stderr": "", "timed_out": False,
    }
    for name in ("flash_firmware", "erase_flash", "mass_erase", "program_otp", "write_fuse"):
        r = broker.invoke(name, {}, ctx=CallContext(max_level="L3", principal="evil", project_id=proj["id"]))
        assert r.status == "denied"
    assert executed["n"] == 0


def test_research_agent_cannot_use_l2_via_session(env):
    from agent_runtime.broker_session import AgentBrokerSession

    pos, proj, broker, client, eng = env
    session = AgentBrokerSession(
        client,
        agent_id="research",
        project_id=proj["id"],
        allowed_tools=["get_system_info", "west_build"],
        max_level="L2",  # config claims L2 — Broker session still untrusted
    )
    res = session.call("west_build", {"board": "x", "source_dir": proj["workspace_path"]})
    assert res.ok is False
    assert res.status == "denied"
