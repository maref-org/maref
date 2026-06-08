#!/usr/bin/env python3
"""Send email notification for MAREF study syncing.

Usage:
    python scripts/email_notify.py --subject "..." --body "..."

Environment variables (from .env or ~/.maref.env):
    SMTP_SERVER    — SMTP server (default: smtp.qq.com)
    SMTP_PORT      — SMTP port (default: 587)
    SMTP_USERNAME  — SMTP login username
    SMTP_PASSWORD  — SMTP login password (QQ 16-char auth code)
    EMAIL_FROM     — Sender address
    EMAIL_TO       — Recipient address
"""

import os
import smtplib
import sys
from argparse import ArgumentParser
from email.mime.text import MIMEText


def load_env() -> None:
    for env_file in [".env", os.path.expanduser("~/.maref.env")]:
        if os.path.isfile(env_file):
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())
            break


def main() -> None:
    load_env()

    parser = ArgumentParser(description="Send email notification for MAREF sync")
    parser.add_argument("--subject", required=True)
    parser.add_argument("--body", required=True)
    args = parser.parse_args()

    smtp_server = os.environ.get("SMTP_SERVER", "smtp.qq.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    from_addr = os.environ.get("EMAIL_FROM")
    to_addr = os.environ.get("EMAIL_TO")

    if not all([username, password, from_addr, to_addr]):
        print("ERROR: SMTP_USERNAME, SMTP_PASSWORD, EMAIL_FROM, EMAIL_TO must be set", file=sys.stderr)
        sys.exit(1)

    msg = MIMEText(args.body, _charset="utf-8")
    msg["Subject"] = args.subject
    msg["From"] = from_addr
    msg["To"] = to_addr

    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=15) as s:
            s.starttls()
            s.login(username, password)
            s.send_message(msg)
        print(f"OK: email sent to {to_addr}")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
