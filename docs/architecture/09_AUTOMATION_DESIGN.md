# Document 9 — Automation Design (n8n)

---

## 1. Role

n8n = **deterministic workflow engine** for personal/ops integrations and event notifications.  
Master = intelligence that decides *whether* and *which* workflow to run.

---

## 2. Deployment on this Pi

| Item | Plan |
|---|---|
| Runtime | Docker  
| Compose | Requires installing `docker-compose-plugin` or equivalent (currently missing)  
| DB | Postgres container  
| Resources | Cap memory (~512MB–1GB n8n); avoid on Pi if host RAM < headroom — optional off-box later  
| Auth | Enable auth; MCP endpoints authenticated  

---

## 3. Integration patterns

### A. n8n as MCP server (preferred)

- MCP Server Trigger nodes expose curated tools: `email_triage`, `gh_create_issue`, `calendar_add`, `reminder_create`, `cab_book_stub`.  
- Master ops agent allowlisted to these tools only.  
- Each call → execution id returned → Master stores in Project OS events (or global ops log).

### B. Webhooks

- Engineering events (`build_failed`, `flash_done`) POST to n8n.  
- n8n notifies (Telegram/email) or calls Master `/v1/events`.

### C. Instance MCP (optional)

- Cursor/Claude may edit workflows during development.  
- Not required at runtime for agents.

### D. n8n AI Agent node

- Allowed for narrow ops assistants **inside** n8n.  
- Must not orchestrate PYRA engineering agents.

---

## 4. Lifecycle

| Concern | Design |
|---|---|
| Discovery | Master caches `tools/list` from n8n MCP on startup + periodic refresh |
| Approval | Level 2 for send/post/book; Level 1 for draft/list |
| Failures | Surface n8n error + execution URL; retry policy inside n8n for idempotent steps |
| Versioning | Export workflows to `agent-os/integrations/n8n/workflows/*.json` in git |
| Credentials | n8n credential store; never into LLM context |
| Audit | execution id + workflow name in Pyra events |

---

## 5. Example mappings

| User request | Flow |
|---|---|
| Check important mail | ops → `email_triage` → speech summary |
| Create GH issue for bug | ops → `gh_create_issue` with project artifact excerpt |
| Remind tomorrow | n8n schedule / reminder workflow |
| CI failed | GitHub webhook → n8n → Master event → Mark proactive |
| Weekly summary | cron → gather Project OS → docs agent → mail draft |

---

## 6. What not to put in n8n

- Multi-agent engineering graphs  
- Device Broker enforcement  
- Project switching  
- Long ACP coding sessions  
