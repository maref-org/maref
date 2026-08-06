#!/usr/bin/env python3
"""Preview, send, and monitor arXiv endorsement requests from AthenaBot."""

from __future__ import annotations

import csv
import getpass
import gzip
import imaplib
import io
import os
import re
import smtplib
import ssl
import sys
import tarfile
import time
from argparse import ArgumentParser
from email import message_from_bytes
from email.header import decode_header
from email.mime.text import MIMEText
from pathlib import Path
from urllib.request import Request, urlopen

ARXIV_ACCOUNT = "87909004@qq.com"
ATHENA_FROM = "Athenabot@qq.com"
ENDORSE_URL = "https://arxiv.org/auth/endorse?x=VAE3BR"
ENDORSE_CODE = "VAE3BR"
TITLE = "MAREF: A Recursive Self-Evolving Governance Framework for Multi-Agent Systems"
SUBJECT = "arXiv cs.MA Endorsement Request — MAREF Agent Governance Framework"


def load_env() -> None:
    for env_file in [Path(".env"), Path.home() / ".maref.env"]:
        if env_file.is_file():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())
            break


def decode_mime(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            codec = enc or "utf-8"
            if codec.lower() == "unknown-8bit":
                codec = "utf-8"
            try:
                out.append(text.decode(codec, errors="replace"))
            except LookupError:
                out.append(text.decode("utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def fetch_url(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 MAREF-Endorsement-Operator/1.0"})
    with urlopen(request, timeout=30) as response:
        return response.read()


def extract_emails(text: str) -> list[str]:
    pattern = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    invalid_domains = {"example.com", "example.edu", "domain.invalid", "corporation.com", "affiliation.org", "marysville-ohio.com", "softconf.com", "prl.com"}
    found: list[str] = []
    seen: set[str] = set()
    for email in re.findall(pattern, text):
        normalized = email.strip(".,;:<>[](){}\"'").lower()
        domain = normalized.rsplit("@", 1)[-1]
        if domain in invalid_domains or normalized in seen:
            continue
        seen.add(normalized)
        found.append(normalized)
    return found


def extract_text_from_eprint(payload: bytes) -> str:
    data = payload
    try:
        data = gzip.decompress(payload)
    except OSError:
        pass
    try:
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            parts: list[str] = []
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                if not member.name.endswith((".tex", ".txt", ".bbl", ".md")):
                    continue
                file_obj = archive.extractfile(member)
                if file_obj:
                    parts.append(file_obj.read().decode("utf-8", errors="replace"))
            return "\n".join(parts)
    except tarfile.TarError:
        return data.decode("utf-8", errors="replace")


def parse_recent_papers(html: str) -> list[dict[str, str]]:
    text = re.sub(r"<[^>]+>", "\n", html)
    papers: list[dict[str, str]] = []
    chunks = re.split(r"arXiv:", text)
    for chunk in chunks[1:]:
        arxiv_match = re.match(r"\s*(\d{4}\.\d{4,5})", chunk)
        if not arxiv_match:
            continue
        arxiv_id = arxiv_match.group(1)
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        title = ""
        authors = ""
        for index, line in enumerate(lines):
            if line.startswith("Title:"):
                title = line.removeprefix("Title:").strip()
                if index + 1 < len(lines):
                    authors = lines[index + 1].removeprefix("Authors:").strip()
                break
        author_match = re.search(r"Authors?:\s*(.*?)\s*(?:Comments:|Subjects:)", chunk, re.S)
        if author_match:
            authors = re.sub(r"\s+", " ", author_match.group(1)).strip()
        if title and authors:
            papers.append({"arxiv_id": arxiv_id, "title": title, "authors": authors})
    return papers


def choose_author(authors: str) -> str:
    parts = [part.strip() for part in re.split(r",| and ", authors) if part.strip()]
    return parts[-1] if parts else ""


def discover_targets(limit: int = 10, fetch=fetch_url) -> list[dict[str, str]]:
    recent_html = fetch("https://arxiv.org/list/cs.MA/recent").decode("utf-8", errors="replace")
    targets: list[dict[str, str]] = []
    seen_emails: set[str] = set()
    for paper in parse_recent_papers(recent_html):
        if len(targets) >= limit:
            break
        source_urls = [
            f"https://arxiv.org/html/{paper['arxiv_id']}",
            f"https://arxiv.org/e-print/{paper['arxiv_id']}",
        ]
        emails: list[str] = []
        for url in source_urls:
            try:
                payload = fetch(url)
                text = extract_text_from_eprint(payload) if "/e-print/" in url else payload.decode("utf-8", errors="replace")
                emails.extend(extract_emails(text))
            except Exception:
                continue
        email = next((candidate for candidate in emails if candidate not in seen_emails), "")
        if not email:
            continue
        seen_emails.add(email)
        targets.append({"name": choose_author(paper["authors"]), "email": email, "topic": paper["title"]})
    return targets


def write_targets_csv(targets: list[dict[str, str]], csv_path: str) -> None:
    with Path(csv_path).open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["name", "email", "topic"])
        writer.writeheader()
        writer.writerows(targets)


def build_body(name: str, topic: str) -> str:
    greeting = f"Dear Prof. {name}," if name else "Dear Professor,"
    topic_line = f" I noticed your recent work on {topic}." if topic else " I noticed your recent work in multi-agent systems."
    return f"""{greeting}

I am AthenaBot writing on behalf of Frankie Yang to request your endorsement for an arXiv cs.MA submission.

Frankie's arXiv account email: {ARXIV_ACCOUNT}
Endorsement link: {ENDORSE_URL}
Endorsement code: {ENDORSE_CODE}

Title: {TITLE}
Area: multi-agent systems, agent governance, formal verification

MAREF focuses on agent governance as a standalone operating-system layer for multi-agent systems, with Gray-code governance states, TLA+ formal verification, and safety-boundary mechanisms.{topic_line}

If you are eligible to endorse cs.MA, your help would be greatly appreciated.

Best regards,
AthenaBot
on behalf of Frankie Yang ({ARXIV_ACCOUNT})
"""


def load_rows(csv_path: str) -> list[dict[str, str]]:
    return list(csv.DictReader(Path(csv_path).read_text().splitlines()))


def require_password() -> str:
    password = os.environ.get("SMTP_PASSWORD") or os.environ.get("IMAP_PASSWORD")
    if password:
        return password
    return getpass.getpass("QQ mail authorization code: ")


def env_key_for_email(prefix: str, email: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]", "_", email).upper()
    return f"{prefix}_{normalized}"


def password_for_account(username: str) -> str:
    specific = os.environ.get(env_key_for_email("IMAP_PASSWORD", username))
    if specific:
        return specific
    password = os.environ.get("IMAP_PASSWORD") or os.environ.get("SMTP_PASSWORD")
    if password:
        return password
    return getpass.getpass(f"IMAP authorization code for {username}: ")


def parse_monitor_accounts() -> list[dict[str, str]]:
    value = os.environ.get("MONITOR_ACCOUNTS", "")
    accounts: list[dict[str, str]] = []
    for raw in value.split(","):
        raw = raw.strip()
        if not raw:
            continue
        username, _, server = raw.partition(":")
        accounts.append({"username": username.strip(), "server": server.strip() or "imap.qq.com"})
    if accounts:
        return accounts
    username = os.environ.get("IMAP_USERNAME") or os.environ.get("SMTP_USERNAME", ATHENA_FROM)
    server = os.environ.get("IMAP_SERVER", "imap.qq.com")
    return [{"username": username, "server": server}]


def send_email(to_addr: str, subject: str, body: str, password: str) -> None:
    smtp_server = os.environ.get("SMTP_SERVER", "smtp.qq.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME", ATHENA_FROM)
    from_addr = os.environ.get("EMAIL_FROM", ATHENA_FROM)
    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    with smtplib.SMTP(smtp_server, smtp_port, timeout=20) as smtp:
        smtp.starttls()
        smtp.login(username, password)
        smtp.send_message(msg)


def print_preview(rows: list[dict[str, str]]) -> int:
    count = 0
    for idx, row in enumerate(rows, 1):
        name = (row.get("name") or "").strip()
        email = (row.get("email") or "").strip()
        topic = (row.get("topic") or "").strip()
        if not email:
            print(f"SKIP {idx}: missing email")
            continue
        count += 1
        print(f"\n--- PREVIEW {idx}/{len(rows)} -> {email} ---")
        print(f"Subject: {SUBJECT}\n")
        print(build_body(name, topic))
    return count


def confirm_send(count: int) -> bool:
    if count == 0:
        print("No emails ready to send", file=sys.stderr)
        return False
    answer = input(f"Send {count} emails from {ATHENA_FROM}? Type SEND to confirm: ")
    return answer.strip() == "SEND"


def send_all(rows: list[dict[str, str]], delay: float) -> int:
    ready = print_preview(rows)
    if not confirm_send(ready):
        print("Cancelled")
        return 1
    password = require_password()
    sent = 0
    for row in rows:
        name = (row.get("name") or "").strip()
        email = (row.get("email") or "").strip()
        topic = (row.get("topic") or "").strip()
        if not email:
            continue
        send_email(email, SUBJECT, build_body(name, topic), password)
        sent += 1
        print(f"OK {sent}/{ready} sent to {email}")
        time.sleep(delay)
    return 0


# Persistent state: tracks which messages we've already reported
_SEEN_MESSAGES: set[str] = set()


def should_report_message(sender: str, subject: str, targets: set[str]) -> bool:
    lowered_subject = subject.lower()
    return (
        not targets
        or any(target in sender for target in targets)
        or "arxiv" in lowered_subject
        or "endorse" in lowered_subject
        or "reply" in lowered_subject
        or "re:" in lowered_subject
    )


def message_fingerprint(msg_id: bytes, sender: str, subject: str) -> str:
    return f"{msg_id.decode(errors='replace')}|{sender}|{subject}"


def monitor_one_account(account: dict[str, str], rows: list[dict[str, str]],
                        state_file: Path | None = None) -> int:
    username = account["username"]
    server = account["server"]
    password = password_for_account(username)
    targets = {((row.get("email") or "").strip().lower()) for row in rows if (row.get("email") or "").strip()}
    context = ssl.create_default_context()
    reported = 0
    try:
        with imaplib.IMAP4_SSL(server, 993, ssl_context=context) as imap:
            imap.login(username, password)
            imap.select("INBOX", readonly=False)
            # Search ALL messages, not just UNSEEN
            _, data = imap.search(None, "ALL")
            ids = data[0].split() if data and data[0] else []
            print(f"[{time.strftime('%H:%M:%S')}] {username}: scanning {len(ids)} messages", flush=True)
            for msg_id in ids:
                fp = message_fingerprint(msg_id, "", "")
                if fp in _SEEN_MESSAGES:
                    continue
                _, msg_data = imap.fetch(msg_id, "(RFC822)")
                raw = msg_data[0][1]
                msg = message_from_bytes(raw)
                sender = decode_mime(msg.get("From")).lower()
                subject = decode_mime(msg.get("Subject"))
                msg_fp = message_fingerprint(msg_id, sender, subject)
                if msg_fp in _SEEN_MESSAGES:
                    continue
                if should_report_message(sender, subject, targets):
                    _SEEN_MESSAGES.add(msg_fp)
                    reported += 1
                    date_str = decode_mime(msg.get("Date")) or ""
                    # Mark as read if it was unread
                    imap.store(msg_id, "+FLAGS", "\\Seen")
                    print(f"[{time.strftime('%H:%M:%S')}] {username} NEW: From={decode_mime(msg.get('From'))} | Subject={subject} | Date={date_str}", flush=True)
                    # Extract body preview
                    body_preview = extract_body_preview(msg)
                    if body_preview:
                        print(f"  Body preview: {body_preview[:200]}", flush=True)
    except Exception as exc:
        print(f"[{time.strftime('%H:%M:%S')}] {username} monitor error: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
    # Persist state
    if state_file and reported > 0:
        save_seen_state(state_file)
    return reported


def extract_body_preview(msg) -> str:
    """Extract a short text preview from the email body."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    text = payload.decode(charset, errors="replace")
                    return text.strip()[:500]
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            return text.strip()[:500]
    return ""


_SEEN_STATE_FILE = Path(".arxiv_monitor_state")


def load_seen_state(path: Path | None = None) -> None:
    p = path or _SEEN_STATE_FILE
    if p.is_file():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line:
                _SEEN_MESSAGES.add(line)
    print(f"[{time.strftime('%H:%M:%S')}] Loaded {_SEEN_MESSAGES.__len__()} previously seen messages from {p}", flush=True)


def save_seen_state(path: Path | None = None) -> None:
    p = path or _SEEN_STATE_FILE
    p.write_text("\n".join(sorted(_SEEN_MESSAGES)) + "\n")


def monitor_inbox(rows: list[dict[str, str]], interval: int, loops: int) -> int:
    load_seen_state()
    accounts = parse_monitor_accounts()
    total_reported = 0
    print(f"[{time.strftime('%H:%M:%S')}] Starting monitor: {len(accounts)} account(s), interval={interval}s, max_loops={loops}", flush=True)
    for loop in range(loops):
        loop_reported = 0
        for account in accounts:
            try:
                loop_reported += monitor_one_account(account, rows, state_file=_SEEN_STATE_FILE)
            except Exception as exc:
                print(f"[{time.strftime('%H:%M:%S')}] {account['username']} monitor error: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        total_reported += loop_reported
        if loop_reported > 0:
            print(f"[{time.strftime('%H:%M:%S')}] Loop {loop+1}/{loops}: {loop_reported} new message(s) found (total: {total_reported})", flush=True)
        if loop < loops - 1:
            time.sleep(interval)
    print(f"[{time.strftime('%H:%M:%S')}] Monitor finished. Total new messages: {total_reported}", flush=True)
    return total_reported


def main() -> int:
    load_env()
    parser = ArgumentParser(description="Preview, send, and monitor arXiv endorsement requests")
    parser.add_argument("--csv", default="docs/arxiv-endorsement-targets.csv")
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--monitor", action="store_true")
    parser.add_argument("--delay", type=float, default=3.0)
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--loops", type=int, default=60)
    args = parser.parse_args()
    if args.discover:
        targets = discover_targets(limit=args.limit)
        write_targets_csv(targets, args.csv)
        print(f"Discovered {len(targets)} targets -> {args.csv}")
    rows = load_rows(args.csv)
    if args.monitor:
        return monitor_inbox(rows, args.interval, args.loops)
    if args.send:
        return send_all(rows, args.delay)
    print_preview(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
