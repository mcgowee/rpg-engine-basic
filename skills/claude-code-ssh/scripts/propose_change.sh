#!/usr/bin/env bash
# propose_change.sh — SSH to desktop and ask Claude Code to describe (not apply) changes
# Usage: propose_change.sh "task description" [workdir]
#
# Prints Claude's full stdout+stderr output.

set -euo pipefail

TASK="${1:?Usage: propose_change.sh <task> [workdir]}"
WORKDIR="${2:-/home/mcgowee}"
SSH_HOST="mcgowee@192.168.50.90"

PROMPT="Describe what changes you would make to accomplish: ${TASK} — do not make any changes yet, just describe them clearly"

ssh -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new "$SSH_HOST" \
    "cd $(printf '%q' "$WORKDIR") && claude -p $(printf '%q' "$PROMPT") 2>&1"
