#!/usr/bin/env python3
"""
ask_claude.py — Send a message to Claude API with desktop context and conversation history.

Usage:
    python3 ask_claude.py "your message here" [--history-file /path/to/history.json]

Outputs JSON:
    {
        "response": "Claude's reply",
        "history_file": "/path/to/history.json"
    }
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

try:
    import anthropic
except ImportError:
    print(json.dumps({"error": "anthropic package not installed. Run: pip3 install anthropic"}))
    sys.exit(1)

SYSTEM_PROMPT = """You are a senior software engineer helping mcgowee develop projects on their desktop machine.

Environment:
- Desktop host: 192.168.50.90 (SSH: mcgowee@192.168.50.90)
- OS: Ubuntu 24.04, GPU: RTX 5070 Ti
- Active projects:
  - ~/projects/epstein-docs — PDF ingest pipeline (Python, pdfplumber, SQLite, Azure DI for OCR)
  - ~/projects/rpg-engine-basic — RPG engine (stack TBD)
- Stack: Python, Flask, SvelteKit
- Ollama running locally at 192.168.50.90:11434 with nomic-embed-text and other models
- Python venvs live at .venv/ inside each project

When suggesting changes:
- Be specific and direct — give exact code/commands, not vague suggestions
- If a fix requires running a command, say so explicitly so it can be executed
- Prefer minimal, surgical changes over rewrites
- Flag if a suggestion requires apply_change vs just running a shell command
"""

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 2000
MAX_HISTORY_EXCHANGES = 4  # keep last 4 pairs (8 messages)
HISTORY_DIR = Path("/tmp/ask-claude-history")


def load_history(history_file: Path) -> list:
    if history_file.exists():
        try:
            data = json.loads(history_file.read_text())
            # Trim to last MAX_HISTORY_EXCHANGES exchanges
            messages = data.get("messages", [])
            max_msgs = MAX_HISTORY_EXCHANGES * 2
            return messages[-max_msgs:] if len(messages) > max_msgs else messages
        except Exception:
            return []
    return []


def save_history(history_file: Path, messages: list):
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    history_file.write_text(json.dumps({"messages": messages, "updated": time.time()}, indent=2))


def find_api_key() -> str:
    # 1. Environment variable
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key

    # 2. OpenClaw auth-profiles (primary location)
    auth_profiles = Path.home() / ".openclaw" / "agents" / "main" / "agent" / "auth-profiles.json"
    if auth_profiles.exists():
        try:
            data = json.loads(auth_profiles.read_text())
            profiles = data.get("profiles", {})
            for profile_name in ["anthropic:default", "anthropic:manual"]:
                p = profiles.get(profile_name, {})
                key = p.get("key") or p.get("token") or p.get("apiKey") or ""
                if key and key.startswith("sk-"):
                    return key
        except Exception:
            pass

    # 3. ~/.env or .env
    for env_file in [Path.home() / ".env", Path("/home/mcgowee/.env")]:
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")

    return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("message", help="Message to send to Claude")
    parser.add_argument("--history-file", help="Path to conversation history JSON file")
    parser.add_argument("--reset", action="store_true", help="Clear conversation history before sending")
    args = parser.parse_args()

    # Resolve history file
    if args.history_file:
        history_file = Path(args.history_file)
    else:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        history_file = HISTORY_DIR / "default.json"

    # Load or reset history
    messages = [] if args.reset else load_history(history_file)

    # Append new user message
    messages.append({"role": "user", "content": args.message})

    # Get API key
    api_key = find_api_key()
    if not api_key:
        print(json.dumps({
            "error": "No Anthropic API key found. Set ANTHROPIC_API_KEY env var or add to ~/.env"
        }))
        sys.exit(1)

    # Call Claude
    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        reply = response.content[0].text
    except Exception as e:
        print(json.dumps({"error": f"API call failed: {e}"}))
        sys.exit(1)

    # Append assistant reply to history and save
    messages.append({"role": "assistant", "content": reply})
    save_history(history_file, messages)

    print(json.dumps({
        "response": reply,
        "history_file": str(history_file),
        "exchange": len(messages) // 2,
    }))


if __name__ == "__main__":
    main()
