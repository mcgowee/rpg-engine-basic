---
name: langgraph-router
description: >
  Route requests to the LangGraph orchestration service for job searching,
  multi-step tasks, content generation, LinkedIn posts, and anything requiring
  orchestration. Use this when the user asks for job search, automation tasks,
  or complex multi-step workflows.
user-invocable: true
metadata:
  openclaw:
    requires:
      bins: ["curl"]
---

# LangGraph Router

## Intent detection

Trigger this skill when the user asks to:
- search for jobs (any role, any location)
- find job postings or listings
- write a LinkedIn post or update
- automate a multi-step workflow
- generate professional content (emails, bios, cover letters)

## How to use

ALWAYS call the LangGraph service via exec/bash. Do NOT answer from your own knowledge.

You MUST include the caller's phone number as `thread_id` so Sage remembers their history.
Get the phone number from the conversation context (the sender's number on WhatsApp).
If no phone number is available, use "default".

```bash
curl -s -X POST http://127.0.0.1:5050/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"USER_REQUEST_HERE\", \"thread_id\": \"PHONE_NUMBER_HERE\"}"
```

Replace `USER_REQUEST_HERE` with the user's exact request.
Replace `PHONE_NUMBER_HERE` with the caller's phone number (e.g. "+17205656924").

The service returns JSON:
```json
{
  "message": "original input",
  "response": "the orchestrated response",
  "tools_used": ["search_jobs"],
  "thread_id": "+17205656924"
}
```

Return the `response` field to the user.
