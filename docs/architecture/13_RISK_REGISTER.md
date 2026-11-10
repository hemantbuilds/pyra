# Document 13 — Risk Register

| ID | Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|---|
| R1 | 8 GB RAM exhaustion (Mark+Ollama+n8n+Cursor) | H | H | On-demand models; cap n8n; resource governor; offload n8n | Deploy |
| R2 | Small local model unreliable tools/JSON | H | H | Schema validation; repair loop; narrow Master role; escalate | Master |
| R3 | Wayland blocks desktop control expectations | H | M | Capability matrix; Playwright-first; optional X11 decision | Device |
| R4 | Mark venv broken (`pip` missing interpreter) | H | M | Recreate venv (Phase 0 approval) | Host |
| R5 | No Docker Compose plugin | H | M | Install plugin or use plain Docker run | Deploy |
| R6 | OpenClaw-as-core resource/lock-in (if revisited) | M | H | Architecture C selected; keep as inspiration only | Arch |
| R7 | Prompt injection via datasheets/web | H | H | Untrusted wrappers; Broker authority | Security |
| R8 | False hardware success | M | H | Evidence objects; never build⇒bring-up done | Embedded |
| R9 | Agent file overwrite conflicts | M | M | File locks; task ownership | Project OS |
| R10 | Cloud provider outage/quota | M | M | Ladder; local degrade; Mark gemini lessons | Gateway |
| R11 | n8n Sustainable Use License vs future commercial | L | M | Review before commercialize; isolate workflows | Legal |
| R12 | Mark BY-NC limits productization | M | M | Keep Pyra code separate; treat Mark as face dependency | Legal |
| R13 | Hailo treated as LLM accelerator | M | M | Architecture forbids; vision-only path | Arch |
| R14 | ACP session loss after reboot | M | M | Project OS authoritative; rehydrate | Agents |
| R15 | Serial/hardware not attached → blocked demos | H | L | Explicit `no_target` states; fixtures | Lab |
| R16 | AnyDesk/VNC expand attack surface | M | M | Firewall; don’t expose Broker remotely | Security |
| R17 | Uncontrolled recursive delegation | M | H | Depth/fan-out caps | Orchestrator |
| R18 | Secret leakage in logs/HUD | M | H | Redaction; secret store | Security |
| R19 | Framework sprawl (CrewAI+LangGraph+OpenClaw…) | M | H | ADR stack discipline | Arch |
| R20 | Upstream Mark breaks plugin API | M | M | Thin plugin; pin Mark revision | Mark |

---

## Top 5 to resolve before Phase 1 coding

1. R2 benchmark on this Pi  
2. R3 desktop strategy decision  
3. R4 Mark environment repair plan  
4. R1 memory policy (n8n on/off box)  
5. Architecture C sign-off (Doc 3)
