# OpenClaw Feature Tour

Quick reference for testing core OpenClaw functionality.
All CLI commands require NVM loaded: `source "$HOME/.nvm/nvm.sh"`

---

## 1. Status & Health

```bash
openclaw status
openclaw doctor
```

---

## 2. Skills (5 ready out of 52)

Ready: `healthcheck`, `skill-creator`, `tmux`, `weather`, `langgraph-router`

**Test via WhatsApp:**
```
What's the weather in Denver?
```
Skills trigger automatically from intent — no slash command needed.

**CLI:**
```bash
openclaw skills list
openclaw skills info weather
openclaw skills check langgraph-router
```

---

## 3. Cron Jobs

**One-shot → WhatsApp delivery (correct syntax):**
```bash
openclaw cron add \
  --name "WA delivery test" \
  --at "1m" \
  --session isolated \
  --message "This is a test cron job. Reply with a brief acknowledgment." \
  --announce \
  --channel whatsapp \
  --to "+17205656924" \
  --delete-after-run
```

**Recurring — Morning brief at 8am Mountain:**
```bash
openclaw cron add \
  --name "Morning brief" \
  --cron "0 8 * * *" \
  --tz "America/Denver" \
  --session isolated \
  --message "Give mcgowee a brief good morning: weather in Denver + anything in HEARTBEAT.md." \
  --announce \
  --channel whatsapp \
  --to "+17205656924"
```

**Inspect:**
```bash
openclaw cron list
openclaw cron runs --id <job-id>
openclaw cron run <job-id>   # force-run now
```

> **Note:** `--session main --system-event` runs silently (no WhatsApp delivery).
> Use `--session isolated --message --announce --channel --to` for WhatsApp output.

---

## 4. Heartbeat

Runs every 30 min automatically. Edit `~/.openclaw/workspace/HEARTBEAT.md` to give it tasks:

```bash
cat > ~/.openclaw/workspace/HEARTBEAT.md << 'EOF'
# Heartbeat tasks (checked every 30 min)

- If it's between 09:00-17:00 Mountain time and you haven't sent a message in 4+ hours, send a brief status check to mcgowee.
- If any background cron jobs have run since last heartbeat, summarize results.
EOF
```

**Manual trigger:**
```bash
openclaw system event --text "Check HEARTBEAT.md and act on it." --mode now
```

---

## 5. Sub-agents

**Via WhatsApp** (note: agentId `main` required as first arg):
```
/subagents spawn main "Search the web for the top 5 trending ML/AI job titles in Denver right now and summarize them"
```

**Control:**
```
/subagents list
/subagents log 1
/subagents kill all
```

---

## 6. Slash Commands (WhatsApp)

| Command | What it does |
|---|---|
| `/status` | System health snapshot |
| `/whoami` | Shows your sender ID |
| `/model claude-opus-4-6` | Switch to Opus for this session |
| `/think high` | Enable extended reasoning |
| `/verbose on` | See all tool calls in replies |
| `/new` | Start a fresh session |
| `/subagents list` | Show active sub-agents |

---

## 7. Web Dashboard

**From the server itself:**
```
http://127.0.0.1:18789/
```

**From another machine on LAN (use a different local port to avoid conflicts):**
```bash
ssh -N -L 18790:127.0.0.1:18789 mcgowee@192.168.1.148
# then open http://127.0.0.1:18790/
```

**Auth:** Paste gateway token when prompted:
```
f57ed27b6ab55c6e4c7d6342a70c00532200ac87c1bb34dd
```
Token is also in: `/home/mcgowee/.config/systemd/user/openclaw-gateway.service` (OPENCLAW_GATEWAY_TOKEN)

---

## 8. Direct CLI Chat (no WhatsApp)

```bash
openclaw agent --to +17205656924 --message "Hello from the CLI" --deliver
```

---

## Lessons Learned

- Cron `--at` takes `2m` not `+2m`
- `/subagents spawn` requires agentId first: `/subagents spawn main "task"`
- `--session main --system-event` = silent (no delivery). Always use `--session isolated + --announce + --channel + --to` for WhatsApp output.
- LAN browser connections require device pairing approval: `openclaw devices list` then `openclaw devices approve <id>`
