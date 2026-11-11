"""Phase 6.1 — real subprocess process-group lifecycle tests."""

from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

import pytest

from device_broker.process_exec import run_process_group


CHILD_SCRIPT = r"""
import os, sys, time, signal

def main():
    mode = sys.argv[1]
    if mode == "ok":
        print("hello-ok", flush=True)
        sys.exit(0)
    if mode == "fail":
        print("hello-fail", file=sys.stderr, flush=True)
        sys.exit(7)
    if mode == "sleep":
        time.sleep(30)
        print("late", flush=True)
        sys.exit(0)
    if mode == "parent_child":
        # Spawn a child that ignores SIGTERM
        pid = os.fork()
        if pid == 0:
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            # Keep running until SIGKILL
            while True:
                time.sleep(0.2)
        else:
            # Parent writes pid then sleeps (west-like)
            print(f"child={pid}", flush=True)
            time.sleep(30)
            sys.exit(0)
    if mode == "big_out":
        chunk = b"x" * 1024
        for _ in range(200):
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
        sys.exit(0)
    sys.exit(2)

if __name__ == "__main__":
    main()
"""


@pytest.fixture
def script(tmp_path):
    p = tmp_path / "fixture_proc.py"
    p.write_text(CHILD_SCRIPT)
    return p


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def test_successful_build_fixture(script, tmp_path):
    r = run_process_group(
        [sys.executable, str(script), "ok"],
        cwd=tmp_path,
        env=os.environ.copy(),
        timeout_s=5,
        max_output_bytes=4096,
    )
    assert r["timed_out"] is False
    assert r["exit_code"] == 0
    assert "hello-ok" in r["stdout"]
    assert r["termination"]["reaped"] is True


def test_failed_build_fixture(script, tmp_path):
    r = run_process_group(
        [sys.executable, str(script), "fail"],
        cwd=tmp_path,
        env=os.environ.copy(),
        timeout_s=5,
        max_output_bytes=4096,
    )
    assert r["timed_out"] is False
    assert r["exit_code"] == 7
    assert "hello-fail" in r["stderr"]


def test_timeout_terminates_process_group(script, tmp_path):
    r = run_process_group(
        [sys.executable, str(script), "sleep"],
        cwd=tmp_path,
        env=os.environ.copy(),
        timeout_s=0.4,
        max_output_bytes=4096,
        kill_grace_s=0.5,
    )
    assert r["timed_out"] is True
    assert r["exit_code"] == -1
    assert r["termination"]["sigterm_sent"] is True
    assert r["termination"]["reaped"] is True
    # Main pid should be gone
    assert not _alive(r["pid"])


def test_timeout_kills_sigterm_ignoring_child(script, tmp_path):
    r = run_process_group(
        [sys.executable, str(script), "parent_child"],
        cwd=tmp_path,
        env=os.environ.copy(),
        timeout_s=0.5,
        max_output_bytes=4096,
        kill_grace_s=0.4,
    )
    assert r["timed_out"] is True
    assert r["termination"]["sigkill_sent"] is True or r["termination"]["sigterm_sent"] is True
    assert r["termination"]["reaped"] is True
    # Give kernel a moment; no members of pgid should remain
    time.sleep(0.3)
    pgid = r["pgid"]
    # Scan /proc for processes with same pgid (best-effort)
    survivors = []
    proc_root = Path("/proc")
    if proc_root.exists():
        for ent in proc_root.iterdir():
            if not ent.name.isdigit():
                continue
            try:
                stat = (ent / "stat").read_text()
                # field 5 is pgid in /proc/pid/stat
                parts = stat.split()
                if int(parts[4]) == pgid:
                    survivors.append(int(ent.name))
            except Exception:
                continue
    assert survivors == [], f"survivors in pgid {pgid}: {survivors}"


def test_output_size_limit(script, tmp_path):
    r = run_process_group(
        [sys.executable, str(script), "big_out"],
        cwd=tmp_path,
        env=os.environ.copy(),
        timeout_s=10,
        max_output_bytes=8192,
    )
    assert r["exit_code"] == 0
    assert r["stdout_truncated"] is True
    assert len(r["stdout"].encode()) <= 8192 + 16  # decode may expand slightly; bound near limit


def test_partial_output_on_timeout(script, tmp_path):
    # parent_child prints child= before sleeping
    r = run_process_group(
        [sys.executable, str(script), "parent_child"],
        cwd=tmp_path,
        env=os.environ.copy(),
        timeout_s=0.5,
        max_output_bytes=4096,
        kill_grace_s=0.3,
    )
    assert r["timed_out"] is True
    assert "child=" in r["stdout"]


def test_west_build_uses_process_group_on_timeout(tmp_path):
    """Integration: DeviceBroker west_build timeout path records termination."""
    from device_broker.broker import DeviceBroker
    from device_broker.policy import BrokerPolicy
    from project_os import ProjectOS

    work = tmp_path / "PyraWork"
    work.mkdir()
    (work / "global").mkdir()
    (work / "projects").mkdir()
    pos = ProjectOS(work)
    proj = pos.create(name="Proc", goal="p")
    broker = DeviceBroker(BrokerPolicy(work_root=work, build_timeout_s=1.0), project_resolver=pos.active_project)
    eng = broker.create_engineering_client()
    src = Path(proj["workspace_path"]) / "app"
    src.mkdir(parents=True)

    # Use real process_exec via a runner that still goes through process group API
    from device_broker.process_exec import run_process_group as rpg

    script = tmp_path / "s.py"
    script.write_text(CHILD_SCRIPT)

    def runner(argv, cwd, timeout, env_map):
        # Ignore argv; run sleep fixture to force timeout cleanup
        return rpg(
            [sys.executable, str(script), "sleep"],
            cwd=cwd,
            env=env_map,
            timeout_s=min(0.4, timeout),
            max_output_bytes=4096,
            kill_grace_s=0.3,
        )

    broker._build_runner = runner
    r = eng.call(
        "west_build",
        {"board": "mimxrt1170_evk@B/mimxrt1176/cm7", "source_dir": str(src)},
        project_id=proj["id"],
    )
    assert r.ok  # tool returned
    assert r.data["success"] is False
    assert r.data["timed_out"] is True
    assert r.data.get("termination", {}).get("reaped") is True
    broker.close()
    pos.close()


def test_concurrent_builds_serialized_per_workspace(tmp_path):
    import threading

    from device_broker.broker import DeviceBroker
    from device_broker.policy import BrokerPolicy
    from project_os import ProjectOS

    work = tmp_path / "PyraWork"
    work.mkdir()
    (work / "global").mkdir()
    (work / "projects").mkdir()
    pos = ProjectOS(work)
    proj = pos.create(name="Conc", goal="p")
    broker = DeviceBroker(BrokerPolicy(work_root=work), project_resolver=pos.active_project)
    eng = broker.create_engineering_client()
    src = Path(proj["workspace_path"]) / "app"
    src.mkdir(parents=True)

    active = {"n": 0, "max": 0}
    lock = threading.Lock()

    def runner(argv, cwd, timeout, env_map):
        with lock:
            active["n"] += 1
            active["max"] = max(active["max"], active["n"])
        time.sleep(0.3)
        with lock:
            active["n"] -= 1
        return {
            "exit_code": 0,
            "timed_out": False,
            "stdout": "ok",
            "stderr": "",
            "resolved_executable": "/w",
        }

    broker._build_runner = runner
    results = []

    def go():
        results.append(
            eng.call(
                "west_build",
                {"board": "mimxrt1170_evk@B/mimxrt1176/cm7", "source_dir": str(src)},
                project_id=proj["id"],
            )
        )

    t1 = threading.Thread(target=go)
    t2 = threading.Thread(target=go)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert all(r.ok and r.data["success"] for r in results)
    assert active["max"] == 1  # serialized by workspace lock
    broker.close()
    pos.close()
