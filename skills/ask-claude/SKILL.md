---
name: ask-claude
description: "Have a multi-turn development conversation with Claude (claude-sonnet-4-20250514) directly from WhatsApp. Use when the user prefixes a message with 'claude:' — e.g. 'claude: how should I fix the path issue in pipeline.py', 'claude: apply that fix', 'claude: what is the status of the ingest run'. Maintains conversation history across messages. Automatically follows up with propose_change or apply_change on the desktop when Claude's response includes code to apply."
---

# ask-claude

Routes `claude:` messages to the Anthropic API with desktop context, maintains conversation history, and optionally applies changes to the desktop.

## Trigger

User prefixes message with `claude:` (case-insensitive, colon required).

Strip the prefix before sending to Claude.

## Script

```bash
python3 ~/.openclaw/workspace/skills/ask-claude/scripts/ask_claude.py "<message>" [--history-file <path>] [--reset]
```

Output is JSON: `{ "response": "...", "history_file": "...", "exchange": N }`

## Workflow

1. Strip `claude:` prefix from user message
2. Run `ask_claude.py` with the message
3. Parse JSON response — surface `response` to the user
4. **Scan Claude's response** for action intent:
   - If it contains a specific command to run (shell command, `python3 ...`, etc.) → offer to run it or run it directly if low-risk
   - If it contains a code change to apply to a file → call `apply_change.sh` from the claude-code-ssh skill (workdir: the relevant project dir on 192.168.50.90)
   - If it's explanation/advice only → just return the response
5. If execution happened, append results to the reply

## Conversation Management

- History is stored at `/tmp/ask-claude-history/default.json` (auto-created)
- Last 4 exchanges (8 messages) are kept
- To reset history: add `--reset` flag, or user says `claude: reset` / `claude: new conversation`
- History persists across WhatsApp messages in the same session

## Desktop Context (baked into system prompt)

- Host: mcgowee@192.168.50.90
- Projects: ~/projects/epstein-docs (PDF ingest), ~/projects/rpg-engine-basic
- Stack: Python, Flask, SvelteKit; Ollama at 192.168.50.90:11434
- Venvs at `.venv/` inside each project

## Notes

- API key is auto-resolved from `~/.openclaw/agents/main/agent/auth-profiles.json`
- Model: `claude-sonnet-4-20250514`, max_tokens: 2000
- `anthropic` package must be installed: `pip3 install anthropic --break-system-packages`
