# MEMORY.md - Long-Term Memory

_Curated. Updated from daily notes. Load only in main session._

## Identity

- Name: Sage 🌿
- Came online: 2026-03-06
- Vibe: calm, thorough, methodical

## mcgowee

- Username: mcgowee | Timezone: America/Denver (MST/MDT)
- Comfortable with Linux, systemd, self-hosted infra
- Prefers things that actually work, not toy demos
- WhatsApp: +17205656924 (primary channel)

## Active Projects

### Job Search Automation (started 2026-03-06)
- Goal: automated job discovery + delivery via WhatsApp
- Stack: OpenClaw → langgraph-router skill → LangGraph Flask (port 5050) → Ollama GPU node
- Targets: LinkedIn Jobs + Indeed (scraping via browser tool)
- Role target: Data / ML / AI, Denver/Colorado area, on-site or hybrid
- Status: LangGraph service exists but is a stub; not yet running as a service

## Infrastructure Quick-Reference

| Thing | Location |
|---|---|
| OpenClaw workspace | ~/.openclaw/workspace/ |
| LangGraph service | ~/services/langgraph/langgraph_service.py |
| Ollama GPU node | 192.168.50.90:11434 |
| Gateway port | 18789 |
| Gateway token | in systemd env (OPENCLAW_GATEWAY_TOKEN) |

## Ollama Models Available
llama3, llama3.1:8b, llama3.2:1b, mistral:7b-instruct, mistral-small:24b, deepseek-r1:14b, qwen2.5-coder:7b
