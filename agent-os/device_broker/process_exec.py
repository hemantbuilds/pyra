"""Process-group execution with bounded timeout and tree cleanup (Phase 6.1)."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Optional


# Default grace between SIGTERM and SIGKILL of the process group.
DEFAULT_KILL_GRACE_S = 2.0


def run_process_group(
    argv: list[str],
    *,
    cwd: Path | str,
    env: dict[str, str],
    timeout_s: float,
    max_output_bytes: int,
    kill_grace_s: float = DEFAULT_KILL_GRACE_S,
) -> dict[str, Any]:
    """
    Run argv in a new session/process group (shell=False).

    On timeout: SIGTERM the process group, wait kill_grace_s, then SIGKILL.
    Always attempts to reap the main process.
    """
    if not argv:
        raise ValueError("empty argv")
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")

    started = time.monotonic()
    proc = subprocess.Popen(
        argv,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        start_new_session=True,  # new process group (pgid == pid)
    )
    pgid = proc.pid
    stdout_buf = bytearray()
    stderr_buf = bytearray()
    trunc_out = {"stdout": False, "stderr": False}
    lock = threading.Lock()

    def _reader(stream, buf: bytearray, key: str) -> None:
        try:
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    break
                with lock:
                    room = max_output_bytes - len(buf)
                    if room <= 0:
                        trunc_out[key] = True
                        # Drain remaining to avoid blocking writers
                        continue
                    if len(chunk) > room:
                        buf.extend(chunk[:room])
                        trunc_out[key] = True
                    else:
                        buf.extend(chunk)
        except Exception:
            pass

    t_out = threading.Thread(target=_reader, args=(proc.stdout, stdout_buf, "stdout"), daemon=True)
    t_err = threading.Thread(target=_reader, args=(proc.stderr, stderr_buf, "stderr"), daemon=True)
    t_out.start()
    t_err.start()

    timed_out = False
    termination = {
        "signaled": False,
        "sigterm_sent": False,
        "sigkill_sent": False,
        "reaped": False,
        "pgid": pgid,
    }

    try:
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            termination["signaled"] = True
            _terminate_group(pgid, proc, grace_s=kill_grace_s, termination=termination)
    finally:
        # Ensure process is reaped
        try:
            if proc.poll() is None:
                _terminate_group(pgid, proc, grace_s=kill_grace_s, termination=termination)
            proc.wait(timeout=max(0.5, kill_grace_s + 1.0))
            termination["reaped"] = True
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                proc.wait(timeout=1.0)
                termination["reaped"] = True
            except Exception:
                termination["reaped"] = False

        t_out.join(timeout=1.0)
        t_err.join(timeout=1.0)
        try:
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()
        except Exception:
            pass

    duration_s = round(time.monotonic() - started, 3)
    exit_code = proc.returncode if proc.returncode is not None else -1
    if timed_out:
        exit_code = -1

    return {
        "exit_code": exit_code,
        "timed_out": timed_out,
        "stdout": bytes(stdout_buf).decode("utf-8", errors="replace"),
        "stderr": bytes(stderr_buf).decode("utf-8", errors="replace"),
        "stdout_truncated": trunc_out["stdout"],
        "stderr_truncated": trunc_out["stderr"],
        "duration_s": duration_s,
        "termination": termination,
        "pgid": pgid,
        "pid": proc.pid,
    }


def _terminate_group(
    pgid: int,
    proc: subprocess.Popen,
    *,
    grace_s: float,
    termination: dict[str, Any],
) -> None:
    """
    SIGTERM the process group, wait a bounded grace period, then always SIGKILL
    the group. Do not return early when only the main process exits — children
    may ignore SIGTERM and must still be force-killed.
    """
    try:
        os.killpg(pgid, signal.SIGTERM)
        termination["sigterm_sent"] = True
    except ProcessLookupError:
        pass
    except PermissionError:
        try:
            proc.terminate()
            termination["sigterm_sent"] = True
        except Exception:
            pass

    deadline = time.monotonic() + max(0.05, grace_s)
    while time.monotonic() < deadline:
        time.sleep(0.05)

    try:
        os.killpg(pgid, signal.SIGKILL)
        termination["sigkill_sent"] = True
    except ProcessLookupError:
        # Group already gone — still try main process
        pass
    except PermissionError:
        try:
            proc.kill()
            termination["sigkill_sent"] = True
        except Exception:
            pass
    try:
        if proc.poll() is None:
            proc.kill()
    except Exception:
        pass