#!/usr/bin/env bash
# apply_change.sh — SSH to desktop and ask Claude Code to apply changes
# Usage: apply_change.sh "task description" [workdir]
#
# Prints Claude's full stdout+stderr output.

set -euo pipefail

TASK="${1:?Usage: apply_change.sh <task> [workdir]}"
WORKDIR="${2:-/home/mcgowee}"
SSH_HOST="mcgowee@192.168.50.90"

ssh -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new "$SSH_HOST" \
    "cd $(printf '%q' "$WORKDIR") && claude -p $(printf '%q' "$TASK") 2>&1"
