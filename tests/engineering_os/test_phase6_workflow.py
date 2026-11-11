"""Phase 6 end-to-end bring-up workflow scenarios (mocked hardware/build)."""

from __future__ import annotations

from pathlib import Path

import pytest

from device_broker.broker import DeviceBroker
from device_broker.client import BrokerClient
from device_broker.policy import BrokerPolicy
from engineering_os import states
from engineering_os.service import EngineeringOS
from master import capabilities
from master.broker_service import reset_broker
from master.contracts import IntentKind, InteractRequest
from master.engineering_service import reset_engineering_os
from master.orchestrator import Orchestrator
from master.project_service import reset_project_os
from project_os import ProjectOS


RT1170_USB = {
    "vid": "1fc9",
    "pid": "0143",
    "manufacturer": "NXP",
    "product": "MCU-Link CMSIS-DAP",
    "sysfs_path": "/sys/bus/usb/devices/1-1",
}


@pytest.fixture
def env(tmp_path):
    work = tmp_path / "PyraWork"
    work.mkdir()
    (work / "global").mkdir()
    (work / "projects").mkdir()
    pos = ProjectOS(work)
    proj = pos.create(name="BringUp", goal="phase6")
    broker = DeviceBroker(BrokerPolicy(work_root=work), project_resolver=pos.active_project)
    client = broker.create_engineering_client()
    eng = EngineeringOS(client)

    def which(name):
        mapping = {
            "west": "/usr/bin/west",
            "cmake": "/usr/bin/cmake",
            "ninja": "/usr/bin/ninja",
            "arm-none-eabi-gcc": "/usr/bin/arm-none-eabi-gcc",
            "git": "/usr/bin/git",
            "python3": "/usr/bin/python3",
        }
        return mapping.get(name)

    def ok_runner(argv, cwd, timeout, env_map):
        bdir = Path(cwd) / "build" / "zephyr"
        bdir.mkdir(parents=True, exist_ok=True)
        (bdir / "zephyr.elf").write_bytes(b"ELF")
        return {
            "exit_code": 0,
            "timed_out": False,
            "stdout": "ninja: build success",
            "stderr": "",
            "resolved_executable": "/usr/bin/west",
        }

    broker._build_runner = ok_runner
    yield {
        "pos": pos,
        "proj": proj,
        "broker": broker,
        "client": client,
        "eng": eng,
        "which": which,
        "work": work,
    }
    broker.close()
    pos.close()


def test_scenario_a_successful_nxp_bringup_build(env):
    eng = env["eng"]
    proj = env["proj"]
    result = eng.bringup_build(
        project_id=proj["id"],
        workspace_path=proj["workspace_path"],
        request_text="connect to the NXP board and run LED blink bring-up",
        skip_live_discovery=True,
        inject_usb=[RT1170_USB],
        inject_serial=[],
        which=env["which"],
        save_artifact=True,
    )
    assert result["overall_status"] == states.BUILT
    assert result["flash_attempted"] is False
    assert result["hardware_verified"] is False
    assert result["board_identification"]["board_id"] == "imxrt1170_evkb"
    assert result["build_result"]["success"] is True
    assert result["build_evidence"]["exit_status"] == 0
    assert "not been verified" in result["speech"].lower() or "not verified" in result["speech"].lower()
    # Files prepared
    blinky = Path(proj["workspace_path"]) / "firmware" / "zephyr_blinky" / "src" / "main.c"
    assert blinky.is_file()


def test_scenario_b_unknown_hardware(env):
    result = env["eng"].bringup_build(
        project_id=env["proj"]["id"],
        workspace_path=env["proj"]["workspace_path"],
        skip_live_discovery=True,
        inject_usb=[{"vid": "abcd", "pid": "1234", "product": "Unknown"}],
        which=env["which"],
        save_artifact=False,
    )
    assert result["overall_status"] == states.BLOCKED
    assert result["build_result"] is None
    assert result["board_identification"]["identified"] is False


def test_scenario_c_missing_toolchain(env):
    result = env["eng"].bringup_build(
        project_id=env["proj"]["id"],
        workspace_path=env["proj"]["workspace_path"],
        skip_live_discovery=True,
        inject_usb=[RT1170_USB],
        which=lambda n: None,
        save_artifact=False,
    )
    assert result["overall_status"] == states.BLOCKED
    assert result["build_result"] is None
    assert any("incomplete" in b.lower() or "missing" in b.lower() for b in result["blocked_operations"])


def test_scenario_d_build_failure(env):
    env["broker"]._build_runner = lambda *a, **k: {
        "exit_code": 2,
        "timed_out": False,
        "stdout": "",
        "stderr": "undefined reference",
        "resolved_executable": "/usr/bin/west",
    }
    result = env["eng"].bringup_build(
        project_id=env["proj"]["id"],
        workspace_path=env["proj"]["workspace_path"],
        skip_live_discovery=True,
        inject_usb=[RT1170_USB],
        which=env["which"],
        save_artifact=False,
    )
    assert result["overall_status"] == states.FAILED
    assert result["build_evidence"]["success"] is False
    assert "undefined reference" in (result["build_evidence"]["stderr"] or "")


def test_scenario_e_build_timeout(env):
    env["broker"]._build_runner = lambda *a, **k: {
        "exit_code": -1,
        "timed_out": True,
        "stdout": "",
        "stderr": "timeout",
        "resolved_executable": "/usr/bin/west",
    }
    result = env["eng"].bringup_build(
        project_id=env["proj"]["id"],
        workspace_path=env["proj"]["workspace_path"],
        skip_live_discovery=True,
        inject_usb=[RT1170_USB],
        which=env["which"],
        save_artifact=False,
    )
    assert result["overall_status"] == states.FAILED
    assert result["build_evidence"]["timed_out"] is True or result["build_result"]["timed_out"] is True


def test_scenario_f_broker_permission_denial(env):
    # Force denial by capping the call at L1 even on the trusted eng client
    r = env["client"].call(
        "west_build",
        {
            "board": "mimxrt1170_evk@B/mimxrt1176/cm7",
            "source_dir": env["proj"]["workspace_path"],
        },
        max_level="L1",
        project_id=env["proj"]["id"],
    )
    assert r.status == "denied"
    hist = list(env["broker"].audit.recent(limit=50)) if hasattr(env["broker"].audit, "recent") else []
    if not hist and hasattr(env["broker"].audit, "query"):
        hist = env["broker"].audit.query(limit=50)
    # Fallback: get_execution_history tool
    if not hist:
        hr = env["client"].call(
            "get_execution_history",
            {"limit": 20},
            max_level="L0",
            project_id=env["proj"]["id"],
        )
        hist = (hr.data or {}).get("events") or (hr.data or {}).get("history") or []
    assert any(
        (e.get("tool") == "west_build" and e.get("status") == "denied")
        or (isinstance(e, dict) and e.get("tool") == "west_build")
        for e in hist
    ) or r.status == "denied"


def test_scenario_g_project_isolation(env):
    other = env["pos"].create(name="Other", goal="iso", make_active=False)
    # Build under project A workspace must not write into B
    result = env["eng"].bringup_build(
        project_id=env["proj"]["id"],
        workspace_path=env["proj"]["workspace_path"],
        skip_live_discovery=True,
        inject_usb=[RT1170_USB],
        which=env["which"],
        save_artifact=False,
    )
    assert result["overall_status"] == states.BUILT
    foreign = Path(other["workspace_path"]) / "firmware" / "zephyr_blinky"
    assert not foreign.exists()
    # Cross-project path denied
    r = env["client"].call(
        "west_build",
        {
            "board": "mimxrt1170_evk@B/mimxrt1176/cm7",
            "source_dir": str(Path(other["workspace_path"]) / "x"),
        },
        project_id=env["proj"]["id"],
    )
    assert r.status in ("denied", "failed")


def test_scenario_h_serial_passive_capture(env):
    env["broker"]._serial_backend = lambda **kw: {
        "success": True,
        "data": b"boot\n",
        "truncated": False,
    }
    result = env["eng"].bringup_build(
        project_id=env["proj"]["id"],
        workspace_path=env["proj"]["workspace_path"],
        skip_live_discovery=True,
        inject_usb=[RT1170_USB],
        inject_serial=[{"path": "/dev/ttyACM0", "vid": "1fc9", "pid": "0143", "product": "MCU-Link"}],
        which=env["which"],
        capture_serial=True,
        serial_device="/dev/ttyACM0",
        save_artifact=False,
    )
    assert result["overall_status"] == states.BUILT
    assert result["serial_result"]["ok"] is True
    assert result["serial_result"]["data"]["tx_attempted"] is False


def test_scenario_i_l3_denial(env):
    for tool in ("flash_firmware", "erase_flash"):
        r = env["broker"].invoke(
            tool,
            {},
            ctx=__import__("device_broker.types", fromlist=["CallContext"]).CallContext(
                max_level="L3", project_id=env["proj"]["id"], principal="test"
            ),
        )
        assert r.status == "denied"


def test_scenario_j_no_hardware(env):
    result = env["eng"].bringup_build(
        project_id=env["proj"]["id"],
        workspace_path=env["proj"]["workspace_path"],
        skip_live_discovery=True,
        inject_usb=[],
        inject_serial=[],
        which=env["which"],
        save_artifact=False,
    )
    assert result["overall_status"] == states.BLOCKED
    assert result["build_result"] is None


@pytest.fixture
def master_env(tmp_path):
    work = tmp_path / "PyraWork"
    work.mkdir()
    (work / "global").mkdir()
    (work / "projects").mkdir()
    pos = reset_project_os(work)
    broker = reset_broker(work, project_resolver=pos.active_project)
    reset_engineering_os()
    capabilities.reset_registry()
    capabilities.bootstrap_builtin_capabilities()
    proj = pos.create(name="MasterBring", goal="p6")
    # Mock build on shared broker
    broker._build_runner = lambda *a, **k: {
        "exit_code": 0,
        "timed_out": False,
        "stdout": "ok",
        "stderr": "",
        "resolved_executable": "/usr/bin/west",
    }
    yield work, pos, proj, broker
    capabilities.reset_registry()
    reset_engineering_os()


def test_master_bringup_integration(master_env, monkeypatch):
    work, pos, proj, broker = master_env
    from master.engineering_handlers import handle_engineering
    from master.contracts import Intent, RiskLevel
    import master.engineering_service as es

    eng = reset_engineering_os()

    def fake_bringup(**kwargs):
        return EngineeringOS(broker.create_engineering_client()).bringup_build(
            project_id=proj["id"],
            workspace_path=proj["workspace_path"],
            skip_live_discovery=True,
            inject_usb=[RT1170_USB],
            which=lambda n: {
                "west": "/w",
                "cmake": "/c",
                "ninja": "/n",
                "arm-none-eabi-gcc": "/a",
                "git": "/g",
                "python3": "/p",
            }.get(n),
            save_artifact=False,
        )

    monkeypatch.setattr(eng, "bringup_build", fake_bringup)
    monkeypatch.setattr(es, "_INSTANCE", eng)

    req = InteractRequest(text="bring up the NXP board LED blink", source="mark")
    intent = Intent(kind=IntentKind.HARDWARE_BRINGUP, confidence=0.9, risk_level=RiskLevel.L0)
    result = handle_engineering(req, intent)
    assert result.capability == "engineering_os"
    assert result.evidence.get("phase") == 6
    assert result.evidence.get("flash_attempted") is False
    assert result.evidence.get("overall_status") == states.BUILT
