# agent-os

PYRA core services (Alternative C).

## Run Master + Dot + Project OS + Device Broker + Engineering OS

```bash
cd /home/hem/pyra/agent-os
source .venv/bin/activate   # or use .venv/bin/python
python -m master
```

Endpoints:

| Path | Role |
|---|---|
| `GET /healthz` | Health + Ollama status |
| `POST /dot/v1/interact` | Mark → Dot → Master |
| `POST /v1/interact` | Direct Master (CLI/tests) |
| `GET /v1/capabilities` | Capability registry |
| `GET /v1/projects` | Project list + active id |
| `GET /broker/v1/tools` | Device Broker tool catalog |
| `POST /broker/v1/call` | Invoke a Broker tool (policy enforced) |

Hardware discovery (via Dot/Master): *"check the devices connected to this PC"* → Engineering OS.

Default bind: `127.0.0.1:8765`

## Standalone Device Broker (MCP stdio)

```bash
python -m device_broker
```

## Mark plugin

`integrations/mark_plugin/pyra_dot.py` is copied to `Mark-LIII/plugins/pyra_dot.py`.

## Tests

```bash
/home/hem/pyra/agent-os/.venv/bin/python -m pytest \
  /home/hem/pyra/tests/master \
  /home/hem/pyra/tests/project_os \
  /home/hem/pyra/tests/device_broker \
  /home/hem/pyra/tests/engineering_os -q
```
