---
name: gmail-migration
description: >
  Help mcgowee migrate from an old Gmail account to a new one. Covers subscription
  auditing, contact export, filter/label migration, forwarding setup, app re-auth,
  and scheduled WhatsApp reminders. Trigger on any mention of switching Gmail accounts,
  email migration, or moving to a new email address.
slug: gmail-migration
tags:
  - gmail
  - email
  - migration
  - productivity
---

# Gmail Migration Skill

## Intent Detection

Trigger this skill when the user mentions:
- Migrating from an old Gmail / email account to a new one
- Switching Gmail accounts
- Moving emails, contacts, or subscriptions to a new email
- Setting up email forwarding from old to new account
- Needing a Gmail migration checklist or plan
- Phrases like "old Gmail", "new Gmail", "switch email", "email migration"

---

## Skill Behavior

This skill guides mcgowee through a structured Gmail account migration. It can:

1. **Generate a full migration checklist** broken into phases
2. **Deep-dive into any specific phase** on request (e.g. "help me with subscriptions")
3. **Schedule WhatsApp reminder crons** for pending migration tasks
4. **Use the browser tool** to open Gmail settings pages when asked
5. **Run exec/bash** to schedule reminders or check migration state

---

## Migration Phases

When the user asks for a migration plan or checklist, output ALL phases below, formatted for WhatsApp (no markdown tables, use bullets and numbered lists):

---

### Phase 1 — Audit & Inventory (Do First)

**Subscriptions & newsletters**
- In old Gmail, search: `unsubscribe` → scan senders for newsletters/services
- Search: `"your subscription"` and `"receipt"` to find paid services
- Search: `"account" OR "welcome" AND "verify"` to find app sign-ups
- Export findings to a doc or note

**Important contacts**
- Go to contacts.google.com (old account) → Export as vCard or Google CSV
- Identify VIP contacts you actively correspond with
- Note any contacts with only this email address on file

**Active services using old Gmail as login**
- Check password manager (if used) — filter by old email domain
- Common categories: banking/finance, work tools, social media, streaming, shopping, cloud storage, government/tax portals

**Existing filters & labels**
- Gmail Settings → Filters and Blocked Addresses → export or note all rules
- Gmail Settings → Labels → screenshot or list all custom labels

**Email signature**
- Copy current signature from Settings → General

---

### Phase 2 — Set Up New Account

- Create new Gmail if not done: accounts.google.com
- Set up email signature in new account
- Enable 2FA on new account immediately
- Add new account to phone/apps alongside old one (don't remove old yet)

---

### Phase 3 — Forward & Redirect

**Enable forwarding from old → new**
- Old Gmail → Settings → See all settings → Forwarding and POP/IMAP
- Add new email as forwarding address → confirm via new inbox
- Choose: forward all mail, or filter-based forwarding

**Send-as from new account (reply as old address)**
- New Gmail → Settings → Accounts and Import → Send mail as → Add another address
- Lets you reply from new account but appear to come from old address during transition

**Set up vacation/auto-reply on old account**
- Inform senders of new address
- Example: "I've moved to [new@gmail.com]. Please update your records."

---

### Phase 4 — Migrate Subscriptions (Highest ROI)

Work through subscription list from Phase 1:
- Priority 1: Financial services (bank, brokerage, tax, insurance)
- Priority 2: Work-critical tools (Slack, GitHub, Jira, cloud providers)
- Priority 3: Frequently used services (streaming, shopping, social)
- Priority 4: Low-value newsletters → consider unsubscribing instead of migrating

Tactic: Use "Forgot password" on each service to trigger a reset to the new email — proves the new address works and updates login.

---

### Phase 5 — Contacts Import

- Go to contacts.google.com (new account) → Import → upload the CSV/vCard from Phase 1
- Merge duplicates if prompted

---

### Phase 6 — Recreate Filters & Labels

- In new Gmail, recreate important filters from Phase 1
- Re-create label structure
- Consider using Gmail's import/export filter XML:
  - Old account: Settings → Filters → Export (saves as mailFilters.xml)
  - New account: Settings → Filters → Import

---

### Phase 7 — Re-authorize Apps & Devices

- Any app using "Sign in with Google" (old account) needs re-auth with new account
- Common: Google Drive sync, third-party email clients, browser Google account
- Check: myaccount.google.com → Security → Third-party apps with account access

---

### Phase 8 — Archive & Wind Down

- In old Gmail: use Google Takeout (takeout.google.com) to export full archive
- Keep old account active for 6–12 months with forwarding enabled
- After 3 months: change forwarding to "send bounce notice" to train senders
- Notify contacts directly (personal email to VIPs)

---

## Scheduling WhatsApp Reminders

When the user asks to set a reminder for a migration task, use this pattern:

```bash
source "$HOME/.nvm/nvm.sh" && openclaw cron add \
  --name "Gmail migration: TASK_NAME" \
  --at "TIME" \
  --session isolated \
  --message "Remind mcgowee to complete this Gmail migration task: TASK_DESCRIPTION. Give a brief actionable prompt to get started." \
  --announce \
  --channel whatsapp \
  --to "+17205656924" \
  --delete-after-run
```

Replace `TASK_NAME`, `TIME`, and `TASK_DESCRIPTION` with user-specified values.

**Example time formats:** `2h` (2 hours), `1d` (1 day), `30m` (30 minutes)

For recurring reminders (e.g. daily check-in during migration):
```bash
source "$HOME/.nvm/nvm.sh" && openclaw cron add \
  --name "Gmail migration daily check" \
  --cron "0 9 * * *" \
  --tz "America/Denver" \
  --session isolated \
  --message "Daily Gmail migration check-in for mcgowee. Ask which phase they're on, celebrate progress, and prompt the next most important action. Keep it under 3 sentences." \
  --announce \
  --channel whatsapp \
  --to "+17205656924"
```

---

## Browser Tool Usage

When the user says "open Gmail settings" or "take me to [Gmail feature]", use the browser tool to navigate:

| Request | URL |
|---|---|
| Forwarding settings | https://mail.google.com/mail/u/0/#settings/fwdandpop |
| Filters | https://mail.google.com/mail/u/0/#settings/filters |
| Labels | https://mail.google.com/mail/u/0/#settings/labels |
| Google Takeout | https://takeout.google.com |
| Contacts export | https://contacts.google.com |
| Third-party app access | https://myaccount.google.com/permissions |
| Gmail send-as | https://mail.google.com/mail/u/0/#settings/accounts |

Note: For old account (not default), append `?authuser=1` or have mcgowee specify which account index.

---

## Response Format

Always format responses for WhatsApp:
- Use plain numbered lists and bullets (no markdown tables)
- Keep individual sections short — offer to expand any phase
- If giving the full checklist, chunk it into phases and ask "Which phase do you want to tackle first?"
- Use phase names as natural breakpoints: "Want me to schedule a reminder for Phase 4?"

---

## Quick-Start Response (when user first mentions migration)

When triggered, open with:

> "Gmail migration — good timing. Here's how I'd break it down into 8 phases:
>
> 1. Audit & inventory (subscriptions, contacts, filters)
> 2. Set up new account
> 3. Enable forwarding old → new
> 4. Migrate subscriptions (highest ROI)
> 5. Import contacts
> 6. Recreate filters & labels
> 7. Re-auth apps & devices
> 8. Archive & wind down old account
>
> Where are you starting from? I can give you a detailed checklist for any phase, help you open the right Gmail settings, or set WhatsApp reminders for tasks you want to do later."
