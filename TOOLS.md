# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## Hosts

- **This machine (gateway host):** 192.168.1.148, user: mcgowee, Ubuntu 24.04, Intel EliteMini
- **Ollama GPU node:** 192.168.50.90:11434 — run `curl http://192.168.50.90:11434/api/tags` to list models (old IP 192.168.1.209 is stale — use 192.168.50.90)

## Services (~/services/)

| Service | Path | Port | Status |
|---|---|---|---|
| langgraph | ~/services/langgraph/langgraph_service.py | 5050 | stopped (no systemd unit yet) |
| slackbot | ~/services/slackbot/ | ? | unknown |
| monitoring | ~/services/monitoring/ | ? | unknown |
| prompt-search | ~/services/prompt-search/ | ? | unknown |

## Ollama Models (on 192.168.1.209)

- `llama3.2:1b` — fast, cheap, used for intent classification
- `llama3.1:8b` — good general purpose
- `llama3` — baseline Llama 3
- `mistral:7b-instruct` — instruction-tuned
- `mistral-small:24b` — largest local model
- `deepseek-r1:14b` — reasoning model
- `qwen2.5-coder:7b` — code tasks
- `nomic-embed-text`, `nomic-embed-text-v2-moe` — embeddings

## LangGraph venv

```bash
source ~/services/langgraph/venv/bin/activate
python ~/services/langgraph/langgraph_service.py
```

## Skills

- `langgraph-router` (custom) — ~/.openclaw/workspace/skills/langgraph-router/SKILL.md
- `healthcheck`, `skill-creator`, `tmux`, `weather` (built-in)

## WhatsApp

- Account: +17205656924 (personal, connected as default provider)
- Primary delivery channel for job search results

---

Add whatever helps you do your job. This is your cheat sheet.
