# agent-os

PYRA core services (Alternative C / Architecture Baseline v1.0).

## Run Master + Dot + Project OS + Device Broker + Engineering OS + Agent Runtime

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
| `GET /v1/agents` | Agent Runtime registry |
| `POST /v1/agents/run` | Run a registered agent (Master/CLI) |
| `GET /broker/v1/tools` | Device Broker tool catalog |
| `POST /broker/v1/call` | Invoke a Broker tool (policy enforced) |

Hardware discovery (via Dot/Master): *"check the devices connected to this PC"* → Engineering OS.  
Agents: *"list agents"* · *"run echo agent"* · *"run broker probe agent"* · *"run research agent"* (Phase 5c PydanticAI).

Default bind: `127.0.0.1:8765`

## Standalone Device Broker (MCP stdio — external interop only)

```bash
python -m device_broker
```

Internal agents use **BrokerClient**, not MCP.

## Mark plugin

`integrations/mark_plugin/pyra_dot.py` is copied to `Mark-LIII/plugins/pyra_dot.py`.

## Tests

```bash
PYDANTIC_AI_NO_BANNER=1 /home/hem/pyra/agent-os/.venv/bin/python -m pytest \
  /home/hem/pyra/tests/agent_runtime \
  /home/hem/pyra/tests/master \
  /home/hem/pyra/tests/project_os \
  /home/hem/pyra/tests/device_broker \
  /home/hem/pyra/tests/engineering_os \
  /home/hem/pyra/tests/model_gateway \
  /home/hem/pyra/tests/research_agent -q
```
