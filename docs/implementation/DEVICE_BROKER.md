# Device Broker — Phase 3

**Status:** Complete  
**Package:** `agent-os/device_broker/`  
**Master wiring:** `master/broker_service.py`, `master/broker_handlers.py`  
**Audit DB:** `~/PyraWork/broker_audit.db`

---

## Architecture

```text
Mark-LIII → Dot → Master capability (device_broker)
                      ↓
                 BrokerClient
                      ↓
                 DeviceBroker.invoke()
                      ├── PermissionLevel check (Phase 3 ceiling = L1)
                      ├── Tool registry
                      ├── Path jail / command allowlist
                      ├── Execution
                      └── AuditLog (SQLite)
```

Independent MCP stdio process (same core):

```bash
cd /home/hem/pyra/agent-os && .venv/bin/python -m device_broker
```

Master never executes host operations itself — only through Device Broker.

---

## MCP transport

Minimal JSON-RPC 2.0 over **stdio** (no heavy MCP SDK dependency):

| Method | Role |
|---|---|
| `initialize` | Handshake |
| `tools/list` | Discover tools + schemas + permission annotations |
| `tools/call` | Invoke tool with `_meta.principal` / `max_level` / `project_id` |
| `ping` | Liveness |

HTTP helpers on Master (same policy):

- `GET /broker/v1/tools`
- `POST /broker/v1/call` `{ "tool", "arguments", "max_level?", "project_id?" }`

---

## Permission levels

| Level | Phase 3 | Examples |
|---|---|---|
| L0 | Granted | list/read files, sysinfo, toolchains, audit history, device node listing |
| L1 | Granted | create/write/copy in approved roots; allowlisted commands |
| L2 | **Not granted** | reserved |
| L3 | **Not granted** | flash/erase/etc. unregistered → denied |

Caller `max_level` is capped at L1 even if the client claims L3.

---

## Workspace boundaries

Approved roots come from Project OS (no second registry):

- **Write:** active project `workspace/` + `~/PyraWork/global/`
- **Read:** workspace + project tree + global + explicit test extras

Path resolution follows symlinks; real paths outside roots are denied. Cross-project absolute paths are denied when that project is not in the active root set.

---

## Command execution

- No shell (`shell=False`).
- Explicit argv allowlist (`policy.DEFAULT_COMMANDS`).
- Blocks `sudo`/`bash`/`sh`/metacharacters.
- Timeout + stdout/stderr size caps.
- Working directory must be inside approved roots.

---

## Audit

Append-only SQLite events: `requested → validated → executing → completed|denied|failed`.

Fields: operation_id, timestamp, principal, client, project_id, tool, level, redacted args, result summary, error, duration_ms.

Secrets (`token`, `password`, Bearer headers, etc.) are redacted before storage.

---

## Tools

`list_directory`, `get_file_info`, `read_text_file`, `create_directory`, `write_text_file`, `copy_file`, `get_system_info`, `get_platform_info`, `get_available_toolchains`, `get_installed_tool_versions`, `list_broker_tools`, `get_execution_history`, `list_connected_devices_readonly`, `run_allowed_command`

---

## Run & test

```bash
# Master + Dot + in-process Broker
cd /home/hem/pyra/agent-os && .venv/bin/python -m master

# Standalone MCP stdio broker
.venv/bin/python -m device_broker

# Tests
.venv/bin/python -m pytest /home/hem/pyra/tests/device_broker \
  /home/hem/pyra/tests/master /home/hem/pyra/tests/project_os -q
```

Example NL via Dot:

- "Show the files in my active project workspace."
- "What operating system is PYRA running on?"
- "Which embedded toolchains are installed?"
- "Create a directory called firmware inside this project."
- "Run the approved version-check command."
