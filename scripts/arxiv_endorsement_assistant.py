#!/usr/bin/env python3
"""arXiv endorsement assistant — tracks multi-round conversations, composes outlines."""

from __future__ import annotations

import csv
import json
import os
import re
import smtplib
import ssl
import sys
import time
from argparse import ArgumentParser
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path

HOTMAIL_FROM = "frankiehot@hotmail.com"
ARXIV_ACCOUNT = "87909004@qq.com"
ENDORSE_URL = "https://arxiv.org/auth/endorse?x=VAE3BR"
ENDORSE_CODE = "VAE3BR"
STATE_FILE = Path("~/.arxiv_endorsement_state.json").expanduser()


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"rounds": {}, "last_sent": {}}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def load_csv(path: str) -> list[dict]:
    return list(csv.DictReader(Path(path).read_text().splitlines()))


def list_targets(csv_path: str) -> None:
    rows = load_csv(csv_path)
    state = load_state()
    print(f"{'#':<3} {'Priority':<8} {'Name':<20} {'Email':<35} {'Round':<6} {'Status':<12} Topic")
    print("-" * 120)
    for i, row in enumerate(rows, 1):
        email = row.get("email", "").strip()
        info = state.get(email, {})
        r = info.get("round", 0)
        status = info.get("status", "ready")
        print(f"{i:<3} {row.get('priority','P2'):<8} {row.get('name',''):<20} {email:<35} {r:<6} {status:<12} {row.get('topic','')[:40]}")


def round1_body(name: str, topic: str) -> str:
    return f"""Dear Dr. {name},

I've been reading your work on {topic} with great interest — it intersects with some questions I've been wrestling with in my own research on agent governance architectures.

I have a specific question I'd love to get your perspective on, if you have a moment.

Best regards,
Ziliang Yang
Independent Researcher, Agent Governance Systems"""


def send_email(to_addr: str, subject: str, body: str) -> None:
    password = os.environ.get("HOTMAIL_PASSWORD") or os.environ.get("SMTP_PASSWORD")
    if not password:
        print("ERROR: set HOTMAIL_PASSWORD environment variable", file=sys.stderr)
        sys.exit(1)
    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = HOTMAIL_FROM
    msg["To"] = to_addr
    with smtplib.SMTP("smtp-mail.outlook.com", 587, timeout=20) as smtp:
        smtp.starttls()
        smtp.login(HOTMAIL_FROM, password)
        smtp.send_message(msg)


def send_round(csv_path: str, target_num: int) -> None:
    rows = load_csv(csv_path)
    if target_num < 1 or target_num > len(rows):
        print(f"Target {target_num} out of range (1-{len(rows)})")
        return
    row = rows[target_num - 1]
    email = row.get("email", "").strip()
    name = row.get("name", "").strip()
    topic = row.get("topic", "").strip()
    state = load_state()
    info = state.setdefault(email, {"round": 0, "status": "ready", "notes": ""})
    r = info["round"]
    print(f"\n=== Target #{target_num}: {name} <{email}> ===")
    print(f"Current round: {r} | Status: {info['status']}")
    print(f"Topic: {topic}")
    print(f"\nRound {r+1} email template:\n")
    print(f"To: {email}")
    print(f"Subject: [WILL BE COMPOSED MANUALLY]")
    print(f"\nBody outline:\n")
    if r == 0:
        print(round1_body(name, topic))
    elif r == 1:
        print("[Acknowledge their reply → share your insight → ask a deeper question]")
    elif r == 2:
        print("[Thank → share preprint → ask for endorsement naturally]")
    print(f"\n---")
    print(f"\nTo send, run with --confirm {target_num}. BUT: compose the subject/body yourself.")
    print(f"Copy the template above, personalize it, then paste into --compose.")


def confirm_send() -> bool:
    answer = input(f"Send from {HOTMAIL_FROM}? Type SEND to confirm: ")
    return answer.strip() == "SEND"


def send_composed(csv_path: str, target_num: int, subject: str, body: str) -> None:
    rows = load_csv(csv_path)
    row = rows[target_num - 1]
    email = row.get("email", "").strip()
    name = row.get("name", "").strip()
    print(f"\nPreview:")
    print(f"To: {email}")
    print(f"Subject: {subject}")
    print(f"\n{body}\n")
    if not confirm_send():
        print("Cancelled")
        return
    send_email(email, subject, body)
    state = load_state()
    info = state.setdefault(email, {"round": 0, "status": "ready", "notes": ""})
    info["round"] += 1
    info["status"] = "sent"
    info["last_sent"] = datetime.now().isoformat()
    save_state(state)
    print(f"Sent. Round {info['round']} logged.")


def follow_up_due(days: int = 5) -> None:
    state = load_state()
    now = datetime.now()
    for email, info in state.items():
        last = info.get("last_sent")
        if not last:
            continue
        last_dt = datetime.fromisoformat(last)
        if info["status"] == "sent" and info["round"] < 3 and (now - last_dt).days >= days:
            print(f"FOLLOW-UP DUE: {email} (round {info['round']}, last {last})")


def mark_replied(email: str) -> None:
    state = load_state()
    if email in state:
        state[email]["status"] = "replied"
        save_state(state)
        print(f"{email} marked as replied")


def main() -> int:
    parser = ArgumentParser(description="arXiv endorsement assistant (v2 — personal approach)")
    parser.add_argument("--csv", default="docs/arxiv-endorsement-targets.csv")
    parser.add_argument("--list", action="store_true", help="List all targets and their status")
    parser.add_argument("--send", type=int, metavar="NUM", help="Preview round for target #NUM")
    parser.add_argument("--compose", type=int, metavar="NUM", help="Send composed email to target #NUM")
    parser.add_argument("--subject", help="Email subject (with --compose)")
    parser.add_argument("--body", help="Email body (with --compose)")
    parser.add_argument("--follow-up", action="store_true", help="Check which targets need follow-up")
    parser.add_argument("--replied", metavar="EMAIL", help="Mark target as having replied")
    args = parser.parse_args()

    if args.list:
        list_targets(args.csv)
    elif args.send:
        send_round(args.csv, args.send)
    elif args.compose:
        if not args.subject or not args.body:
            print("ERROR: --compose requires --subject and --body", file=sys.stderr)
            return 1
        send_composed(args.csv, args.compose, args.subject, args.body)
    elif args.follow_up:
        follow_up_due()
    elif args.replied:
        mark_replied(args.replied)
    else:
        parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
