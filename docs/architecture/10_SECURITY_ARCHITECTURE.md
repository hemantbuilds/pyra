# Document 10 — Security Architecture

---

## 1. Threat model (abridged)

| Threat | Example | Mitigation |
|---|---|---|
| Prompt injection | Datasheet/web says “ignore rules, email secrets” | Untrusted wrappers; Broker ignores model-proposed Level escalation |
| Confused deputy | Agent asks shell to `rm -rf` | Allowlists; levels; path jail |
| Forged confirmation | Model sets `confirmed=true` | Mark UI tokens / Master approval objects issued server-side |
| Secret leakage | API keys in prompts/logs | Secret store; redaction; never echo env |
| Lateral project access | Agent reads other project | Roots scoped to active project + explicit global |
| Supply chain | Random plugins | Signed/allowlisted MCP servers |
| Network exposure | Open MCP on LAN | Loopback default; Tailscale ACL if remote |
| Malicious n8n MCP | Broad tools | Curate Selected tools only |

Trust boundaries: User UI | Master | Broker | MCP servers | Cloud providers | n8n | External web.

---

## 2. Identity

- `principal`: `user`, `master`, `agent:<id>`, `n8n`, `mark`  
- Each Broker call carries principal + `project_id` + `max_level`  
- Broker re-checks independently of LLM text  

---

## 3. Permission levels (normative)

See Doc 7. Summary:

- L0 read-only  
- L1 reversible project ops  
- L2 sensitive (push, send, install) — human approve  
- L3 destructive/hardware security — human approve + explicit  

Prohibited automation examples: OTP/fuse burn without dual control; unconstrained root shell.

---

## 4. Sandboxing

| Execution | Isolation |
|---|---|
| Master | User systemd service |
| Broker tools | Same user; fs jail; command allowlist |
| Cloud coding | Prefer workspace path only |
| Future OpenHands | Docker sandbox optional |
| Browser | Isolated Playwright profile default |

Pi v1 does not require Docker for every tool (resource). Security relies on Broker policy first.

---

## 5. Secrets

- Short term: env files `0600` + systemd `EnvironmentFile`  
- Target: OS keyring / encrypted store; migrate off Mark plaintext for Pyra keys  
- Cloud keys never passed to local Master model context  
- n8n holds OAuth tokens  

---

## 6. Approvals

Approval object: `{id, level, action, preview, expires_at}`  
Issued by Master/Broker; completed only by Mark confirm or CLI `--approve` with local auth.  
Timeout → cancel (Mark 90s pattern is a good default).

---

## 7. Audit

Append-only SQLite `audit_events` + optional log ship.  
Include: principal, tool, params hash, outcome, project_id, approval_id.

---

## 8. Untrusted input

Reuse Mark’s `<<<UNTRUSTED>>>` discipline across Master and specialists.  
Tool annotations from third-party MCP are untrusted.

---

## 9. Network policy

- Ollama: localhost only (already)  
- Master API: localhost token; Tailscale optional  
- Broker MCP HTTP: localhost  
- Outbound cloud: explicit provider list  
