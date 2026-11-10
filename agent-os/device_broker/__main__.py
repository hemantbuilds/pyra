"""Run Device Broker as an independent MCP stdio server.

Usage:
  cd agent-os && .venv/bin/python -m device_broker

Optional env:
  PYRA_WORK_ROOT   (default ~/PyraWork)
  PYRA_BROKER_MAX_LEVEL  (default L1)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from device_broker.broker import DeviceBroker
from device_broker.mcp.server import serve_stdio
from device_broker.policy import BrokerPolicy


def main() -> None:
    work = Path(os.environ.get("PYRA_WORK_ROOT", str(Path.home() / "PyraWork"))).expanduser()
    max_level = os.environ.get("PYRA_BROKER_MAX_LEVEL", "L1")
    policy = BrokerPolicy(work_root=work, default_max_level=max_level)
    # Optional Project OS binding when running standalone
    try:
        from master.project_service import get_project_os

        pos = get_project_os()

        def _resolve():
            return pos.active_project()

        broker = DeviceBroker(policy, project_resolver=_resolve)
    except Exception:
        broker = DeviceBroker(policy)

    # Log to stderr so stdout stays clean for MCP JSON-RPC
    print(f"pyra-device-broker MCP stdio ready work_root={work}", file=sys.stderr)
    serve_stdio(broker)


if __name__ == "__main__":
    main()
