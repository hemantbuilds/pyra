"""Phase 6 security regression — L2 boundaries, jail, injection, agent caps."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_runtime.broker_session import AgentBrokerSession
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
    a = pos.create(name="SecA", goal="a")
    b = pos.create(name="SecB", goal="b", make_active=False)
    broker = DeviceBroker(BrokerPolicy(work_root=work), project_resolver=pos.active_project)
    broker._build_runner = lambda *args, **kwargs: {
        "exit_code": 0,
        "timed_out": False,
        "stdout": "ok",
        "stderr": "",
        "resolved_executable": "/usr/bin/west",
    }
    broker._serial_backend = lambda **kw: {"success": True, "data": b"x", "truncated": False}
    untrusted = BrokerClient(broker)
    eng = broker.create_engineering_client()
    yield pos, a, b, broker, untrusted, eng
    broker.close()
    pos.close()


def test_path_traversal_source_dir(env):
    pos, a, b, broker, untrusted, eng = env
    r = eng.call(
        "west_build",
        {"board": "mimxrt1170_evk@B/mimxrt1176/cm7", "source_dir": f"{a['workspace_path']}/../../../../etc"},
        project_id=a["id"],
    )
    assert r.status == "denied"


def test_cross_project_workspace_denied(env):
    pos, a, b, broker, untrusted, eng = env
    Path(b["workspace_path"], "app").mkdir(parents=True)
    r = eng.call(
        "west_build",
        {"board": "mimxrt1170_evk@B/mimxrt1176/cm7", "source_dir": f"{b['workspace_path']}/app"},
        project_id=a["id"],
    )
    assert r.status in ("denied", "failed")


def test_shell_metachar_extra_args(env):
    pos, a, b, broker, untrusted, eng = env
    src = Path(a["workspace_path"]) / "app"
    src.mkdir(parents=True)
    r = eng.call(
        "west_build",
        {
            "board": "mimxrt1170_evk@B/mimxrt1176/cm7",
            "source_dir": str(src),
            "extra_args": ["$(reboot)"],
        },
        project_id=a["id"],
    )
    assert not r.ok


def test_executable_allowlist_bypass_not_via_west_tool(env):
    pos, a, b, broker, untrusted, eng = env
    seen = {}

    def runner(argv, cwd, timeout, env_map):
        seen["argv"] = list(argv)
        return {
            "exit_code": 0,
            "timed_out": False,
            "stdout": "",
            "stderr": "",
            "resolved_executable": argv[0],
        }

    broker._build_runner = runner
    src = Path(a["workspace_path"]) / "app"
    src.mkdir(parents=True)
    r = eng.call(
        "west_build",
        {"board": "mimxrt1170_evk@B/mimxrt1176/cm7", "source_dir": str(src)},
        project_id=a["id"],
    )
    assert r.ok
    assert seen["argv"][0] == "west"


def test_env_injection_limited_keys(env):
    pos, a, b, broker, untrusted, eng = env
    seen = {}

    def runner(argv, cwd, timeout, env_map):
        seen["env"] = dict(env_map)
        return {
            "exit_code": 0,
            "timed_out": False,
            "stdout": "",
            "stderr": "",
            "resolved_executable": "/w",
        }

    broker._build_runner = runner
    src = Path(a["workspace_path"]) / "app"
    src.mkdir(parents=True)
    eng.call(
        "west_build",
        {"board": "mimxrt1170_evk@B/mimxrt1176/cm7", "source_dir": str(src)},
        project_id=a["id"],
    )
    assert "LD_PRELOAD" not in seen.get("env", {})
    assert "PATH" in seen.get("env", {}) or seen.get("env") is not None


def test_excessive_timeout_rejected(env):
    pos, a, b, broker, untrusted, eng = env
    src = Path(a["workspace_path"]) / "app"
    src.mkdir(parents=True)
    r = eng.call(
        "west_build",
        {
            "board": "mimxrt1170_evk@B/mimxrt1176/cm7",
            "source_dir": str(src),
            "timeout_s": 99999,
        },
        project_id=a["id"],
    )
    assert not r.ok


def test_unauthorized_l2_from_l0_principal(env):
    pos, a, b, broker, untrusted, eng = env
    src = Path(a["workspace_path"]) / "app"
    src.mkdir(parents=True)
    r = untrusted.call(
        "west_build",
        {"board": "mimxrt1170_evk@B/mimxrt1176/cm7", "source_dir": str(src)},
        max_level="L0",
        project_id=a["id"],
        principal="agent:research",
    )
    assert r.status == "denied"


def test_research_session_l1_cannot_escalate(env):
    pos, a, b, broker, untrusted, eng = env
    session = AgentBrokerSession(
        untrusted,
        agent_id="research",
        project_id=a["id"],
        allowed_tools=["west_build", "serial_capture_passive", "get_system_info"],
        max_level="L2",
    )
    src = Path(a["workspace_path"]) / "app"
    src.mkdir(parents=True)
    res = session.call("west_build", {"board": "mimxrt1170_evk@B/mimxrt1176/cm7", "source_dir": str(src)})
    assert res.status == "denied"


def test_agent_l3_tool_denied(env):
    pos, a, b, broker, untrusted, eng = env
    r = broker.invoke(
        "flash_firmware",
        {"image": "x.bin"},
        ctx=CallContext(max_level="L3", principal="agent:evil", project_id=a["id"]),
    )
    assert r.status == "denied"
    assert r.ok is False


def test_serial_device_injection(env):
    pos, a, b, broker, untrusted, eng = env
    r = eng.call(
        "serial_capture_passive",
        {"device": "/dev/ttyACM0;cat /etc/passwd", "baudrate": 115200},
        project_id=a["id"],
    )
    assert r.status == "denied"


def test_uart_tx_tool_not_registered(env):
    pos, a, b, broker, untrusted, eng = env
    r = broker.invoke(
        "serial_transmit",
        {"device": "/dev/ttyACM0", "payload": "AT"},
        ctx=CallContext(max_level="L2", project_id=a["id"]),
    )
    assert r.status == "denied"


def test_no_secret_in_build_result(env):
    pos, a, b, broker, untrusted, eng = env
    src = Path(a["workspace_path"]) / "app"
    src.mkdir(parents=True)
    r = eng.call(
        "west_build",
        {"board": "mimxrt1170_evk@B/mimxrt1176/cm7", "source_dir": str(src)},
        project_id=a["id"],
    )
    blob = str(r.to_dict())
    assert "api_key" not in blob.lower()
    assert "sk-" not in blob
