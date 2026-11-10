# Document 7 — Device OS Design (Linux Control Plane)

---

## 1. Purpose

Provide **authorized, verified** interaction with the host as a human operator would — via a Device Broker that is independent of any LLM.

---

## 2. Capability matrix (this host, 2026-11-09)

| Capability | Backend candidates | Status now |
|---|---|---|
| Read/write files (jailed) | Custom MCP fs | Buildable |
| Shell (allowlisted) | Custom MCP shell | Buildable (pukky proof) |
| Process start/stop | shell/psutil | Buildable |
| Open app | `xdg-open` / `.desktop` (Mark open_app) | Likely OK |
| Browser automate | Playwright | Needs working browser install |
| Fill web forms | Playwright | Same |
| Display page to user | Mark HUD / browser window | OK via Mark |
| Screenshot | grim; portal | Partial |
| Global type/click | pyautogui / ydotool | **Blocked / missing on Wayland** |
| Raise windows | wmctrl | Missing + Wayland limits |
| Git | git CLI MCP | Buildable |
| Serial | pyserial | No device attached |
| Flash/debug | openocd/probe-rs/esptool | Install later |
| Hailo | hailortcli | **Verified device** |
| Remote observe | wayvnc :5900 | Active |

---

## 3. Desktop abstraction

```text
DesktopBackend (Protocol)
  open_application(name) -> Outcome
  focus_application(name) -> Outcome
  type_text(text) -> Outcome
  hotkey(keys) -> Outcome
  screenshot() -> Outcome[path]
```

Implementations:
1. `NullBackend` — reports unsupported (safe default on Wayland).  
2. `PlaywrightBackend` — web-centric; preferred.  
3. `X11Backend` — pyautogui/xdotool when session is X11.  
4. `WaylandExperimentalBackend` — ydotool/wtype if installed later.

Broker selects backend from detected session (`platform_support` logic). Agents never call pyautogui directly.

---

## 4. Browser model

Distinguish profiles:

| Profile | Use | Risk |
|---|---|---|
| `agent` | Isolated Playwright profile | Default automation |
| `user` | Explicit opt-in to user profile | High — approvals for submit |
| `display` | Open URL for human viewing | Low |

Rules:
- Purchases, auth, mail send, banking → Level 2–3 approval.  
- Downloads land in project `artifacts/downloads/`.  
- Page text wrapped as untrusted before LLM.

---

## 5. Device Broker

Single privileged service exposing MCP tools. Agents hold **identity + max_level**; Broker enforces.

### Outcome format (align Mark)

```
status=done|started|failed|unverified|ask action=... key=value ...
```

Machine JSON twin stored in audit log.

### Permission levels

| Level | Examples | Gate |
|---|---|---|
| 0 | read file, list procs, search web, read serial log file | Agent allowlist |
| 1 | write project files, run tests, open app, browser navigate | Agent allowlist |
| 2 | apt install, git push, send email, submit forms, system config | Human approve |
| 3 | flash, mass erase, fuse/OTP, delete critical, payments | Human approve + explicit phrase |

Root is **never** granted to model-facing shell. Optional `pyra-privileged` helper with polkit for rare Level 3.

---

## 6. MCP server split (recommended)

| Server | Tools |
|---|---|
| `pyra.fs` | read/write/list within roots |
| `pyra.shell` | allowlisted commands |
| `pyra.proc` | ps, kill (policy) |
| `pyra.browser` | Playwright |
| `pyra.desktop` | backend-specific |
| `pyra.git` | status/diff/commit/branch (push=L2) |
| `pyra.lab` | serial, hailo, flash |
| `pyra.project` | Project OS operations |

Reuse community MCP servers only when policy wrappers exist; prefer first-party thin servers on Pi for auditability.

---

## 7. Mark actions relationship

Short term: Mark’s existing actions remain usable by voice directly.  
Medium term: Mark plugin routes “computer work” to Master → Broker.  
Long term: duplicate logic collapses into Broker; Mark actions become thin shims or retire.

---

## 8. Verification principle

Examples of required evidence:
- App open → process or window observed  
- Flash → probe tool output + optional serial banner  
- File write → checksum/size readback  
- Workflow → n8n execution id success  

`started` for long jobs; never upgrade to `done` without evidence.
