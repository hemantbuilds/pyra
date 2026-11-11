# Phase 6 — Security Review

**Date:** 2026-11-10

## New L2 operations

| Tool | Level | Purpose |
|---|---|---|
| `west_build` | L2 | Constrained Zephyr build inside project workspace |
| `serial_capture_passive` | L2 | Bounded read-only serial capture |

## Authorization enforcement

1. Tool registry declares required level.
2. Caller `max_level` capped at `MAX_GRANTABLE = L2`.
3. `level_allowed` refuses required > grantable (L3 tools cannot be enabled by claim alone).
4. Engineering OS requests L2 explicitly for build/capture only.
5. ResearchAgent / AgentBrokerSession remain capped at their configured `max_level` (typically L0/L1); allowlisting a tool does not escalate Broker permission.

## Broker boundaries

- No unrestricted shell (`shell=False`).
- `west_build` constructs argv internally; board/source validated; metacharacters rejected.
- Controlled environment allowlist (PATH/HOME/Zephyr vars only) — no `LD_PRELOAD` injection path.
- Timeouts and output size bounded.
- Injectable runners exist **only for tests**; production uses subprocess/serial backends.

## Workspace isolation

- Source/build paths pass `resolve_in_roots`.
- Cross-project workspace access denied under another project's `project_id`.
- Firmware prep writes only under the active project's workspace via L1 tools.

## Serial restrictions

- Device path must be under `/dev/ttyACM*`, `/dev/ttyUSB*`, `/dev/ttyAMA*`, or `/dev/serial/by-id/`.
- No TX tool registered.
- Capture duration ≤ 30s; bytes capped.
- Enumeration remains L0 and does not open ports.

## L3 denial

- `flash_firmware`, `erase_flash`, `mass_erase`, `program_otp`, `write_fuse`, `serial_transmit` unregistered → denied.
- No hidden flash flags or generic command escape for L3.
- Automated tests assert denial and absence of build-runner side effects.

## Residual risks

1. ~~If an operator manually raises an agent's `max_level` to L2 and allowlists `west_build`, builds become possible~~ **Mitigated in Phase 6.1:** L2 requires a Broker-issued session with an explicit tool grant; agent config/allowlist alone cannot escalate.
2. Host `west` binary trust is assumed (same as any allowlisted tool).
3. Passive serial capture could still observe sensitive UART traffic if connected — treat as confidential operational data.
4. Board mis-identification remains possible with ambiguous USB evidence; workflow refuses build when ambiguous.
5. Build workspace locks are in-process only (not cross-host).

## Confirmations

- No unrestricted shell.
- No Broker bypass from Engineering OS / agents.
- No cross-project access in tests.
- No unauthorized L2 without max_level ≥ L2.
- No L3 execution path.
- No flashing or erasing implemented.
