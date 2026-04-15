#!/usr/bin/env python3
"""Gmail IMAP helper for Sage."""
import imaplib
import email
from email.header import decode_header
import sys
import os

GMAIL_USER = "mcgowee@gmail.com"
GMAIL_PASS = os.environ.get("GMAIL_APP_PASS", "gkwbvpwksegejjtq")

def decode_str(s):
    if s is None:
        return ""
    parts = decode_header(s)
    result = ""
    for part, enc in parts:
        if isinstance(part, bytes):
            result += part.decode(enc or "utf-8", errors="replace")
        else:
            result += part
    return result

def fetch_emails(folder="INBOX", count=10, unread_only=True):
    mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    mail.login(GMAIL_USER, GMAIL_PASS)
    mail.select(folder)

    criteria = "UNSEEN" if unread_only else "ALL"
    status, data = mail.search(None, criteria)
    ids = data[0].split()
    ids = ids[-count:]  # most recent

    emails = []
    for eid in reversed(ids):
        status, msg_data = mail.fetch(eid, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        subject = decode_str(msg.get("Subject", "(no subject)"))
        sender = decode_str(msg.get("From", ""))
        date = msg.get("Date", "")

        # Get body snippet
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode("utf-8", errors="replace")[:300]
                    break
        else:
            body = msg.get_payload(decode=True).decode("utf-8", errors="replace")[:300]

        emails.append({"id": eid.decode(), "subject": subject, "from": sender, "date": date, "snippet": body.strip()})

    mail.logout()
    return emails

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "unread"
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    unread_only = mode != "all"
    results = fetch_emails(count=count, unread_only=unread_only)
    for e in results:
        print(f"From: {e['from']}")
        print(f"Subject: {e['subject']}")
        print(f"Date: {e['date']}")
        print(f"Snippet: {e['snippet'][:200]}")
        print("---")
