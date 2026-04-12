---
name: claude-code-ssh
description: "Run Claude Code on mcgowee's desktop (192.168.50.90) via SSH. Provides two tools: propose_change (describe changes without applying) and apply_change (actually make the changes). Use when the user asks to run Claude Code on the desktop, propose or apply code changes remotely, or delegate coding tasks to the GPU desktop machine. Triggers on phrases like 'run claude code on my desktop', 'propose a change', 'apply a change', 'ask Claude Code to', or any task targeting 192.168.50.90."
---

# Claude Code SSH

Two tools for running Claude Code on the desktop (192.168.50.90) via SSH.

## SSH Target

- **Host:** mcgowee@192.168.50.90
- **Claude binary:** `/usr/local/bin/claude`
- **Default workdir:** `/home/mcgowee` (override with a second argument)

## Tool 1: propose_change

Ask Claude Code to describe what it *would* do — no files are modified.

```bash
~/.openclaw/workspace/skills/claude-code-ssh/scripts/propose_change.sh "<task>" [workdir]
```

Example:
```bash
~/.openclaw/workspace/skills/claude-code-ssh/scripts/propose_change.sh \
  "add type hints to all functions in services/langgraph/langgraph_service.py" \
  /home/mcgowee/services/langgraph
```

## Tool 2: apply_change

Ask Claude Code to actually make the changes.

```bash
~/.openclaw/workspace/skills/claude-code-ssh/scripts/apply_change.sh "<task>" [workdir]
```

Example:
```bash
~/.openclaw/workspace/skills/claude-code-ssh/scripts/apply_change.sh \
  "add type hints to all functions in services/langgraph/langgraph_service.py" \
  /home/mcgowee/services/langgraph
```

## Workflow

1. Use `exec` to run the appropriate script, capturing stdout+stderr.
2. Return the full output to the user.
3. For propose → apply workflows: run propose first, show the user, then run apply only if they approve.

## Notes

- Both scripts redirect stderr to stdout (`2>&1`) so all output is captured.
- SSH uses `StrictHostKeyChecking=accept-new` — first-run key acceptance is automatic.
- Claude Code runs non-interactively via `-p` flag (print mode).
- If the task needs a specific working directory (e.g. a git repo), pass it as the second arg.
- Timeout: SSH ConnectTimeout=15s. For long-running tasks, use `exec` with a higher `timeout` or `yieldMs`.
