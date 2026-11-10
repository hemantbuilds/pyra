# Device Broker — Phase 3 Plan

**Status:** Implemented (see `DEVICE_BROKER.md`)  
**Date:** 2026-11-10  
**Basis:** Docs 03, 07, 09, 10, 12, 14 + accepted Phases 0–2

> **Baseline (2026-11-10):** Device Broker remains sole security authority. Future specialists call via **BrokerClient** (internal). Current MCP stdio is an **interop** surface over the same core — not the mandatory internal agent bus. See [`../architecture/PYRA_ARCHITECTURE_BASELINE.md`](../architecture/PYRA_ARCHITECTURE_BASELINE.md).

---

## Goals (this phase)

- Secure Device Broker foundation: permissions L0/L1, policy, tools, audit.
- MCP tool interface (stdio; Master also uses in-process client over the same core).
- Project OS workspace boundaries; no second project registry.
- Master capability integration via Dot path.
- No Engineering OS, flash, serial control, GPIO, or L2/L3 grants.

---

## Architecture

```text
Mark → Dot → Master capability → DeviceBroker.invoke()
                                       ├── Permission check (max_level vs tool level)
                                       ├── Path / command policy
                                       ├── Tool execution
                                       └── Audit SQLite
```

Independent process:

```text
python -m device_broker   # MCP JSON-RPC over stdio (tools/list, tools/call)
```

Same tool registry powers both the MCP server and Master’s in-process client so policy cannot diverge.

---

## Package layout

```text
agent-os/device_broker/
  broker.py          # DeviceBroker facade
  permissions.py     # L0–L3; principal max_level
  policy.py          # roots, command allowlist, limits
  paths.py           # jail / symlink / traversal
  audit.py           # append-only SQLite
  redaction.py       # secret scrubbing
  types.py
  tools/             # fs, sysinfo, exec
  mcp/server.py      # stdio MCP subset
  client.py          # in-process + HTTP helper
```

Storage: `~/PyraWork/broker_audit.db` (authoritative audit).  
Approved roots: active project `workspace/` (+ optional project tree read roots), `~/PyraWork/global/`, and explicit test roots.

---

## Tools (Phase 3)

| Tool | Level | Notes |
|---|---|---|
| `list_directory` | L0 | |
| `get_file_info` | L0 | |
| `read_text_file` | L0 | size limit |
| `get_system_info` | L0 | |
| `get_platform_info` | L0 | |
| `get_available_toolchains` | L0 | probe PATH |
| `get_installed_tool_versions` | L0 | allowlisted version cmds |
| `list_broker_tools` | L0 | |
| `get_execution_history` | L0 | audit query |
| `create_directory` | L1 | workspace only |
| `write_text_file` | L1 | workspace only |
| `copy_file` | L1 | src/dst jailed |
| `run_allowed_command` | L1 | argv allowlist, no shell |

L2/L3 tools are **not registered**. Requests for flash/erase/sudo return explicit denial.

---

## Master intents (deterministic)

Examples: list workspace files, read file, OS info, toolchains, create directory, run version-check, list broker tools.

Hardware bring-up remains a stub (Engineering OS / later phases).

---

## Security decisions

1. Broker enforces levels independently of model text (ADR-004).  
2. No generic shell; argv allowlist only.  
3. Paths resolved with symlink follow; realpath must stay under approved roots.  
4. Cross-project workspace access denied unless that project’s root is explicitly in the call’s allowed set.  
5. Audit never stores raw secrets (redaction).  
6. Default bind/MCP remains local; no LAN exposure in Phase 3.

---

## Out of scope

Playwright/browser, desktop automation, serial, flash, GPIO/SPI/I2C/CAN, Engineering OS, second orchestrator.
