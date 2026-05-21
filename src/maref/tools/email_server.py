from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from maref.integration.mcp_server import MCPServer


class RecipientWhitelist:
    def __init__(self, allowed_patterns: list[str] | None = None) -> None:
        self._patterns: list[str] = allowed_patterns or []

    def is_allowed(self, email: str) -> bool:
        sanitized = _sanitize_email(email)
        if not sanitized:
            return False
        for pattern in self._patterns:
            if pattern.startswith("*."):
                domain = pattern[2:]
                if sanitized.endswith(f"@{domain}"):
                    return True
            elif pattern == sanitized:
                return True
        return False

    @property
    def patterns(self) -> list[str]:
        return list(self._patterns)


class SensitiveWordFilter:
    def __init__(self, sensitive_words: list[str] | None = None) -> None:
        self._words: list[str] = sensitive_words or [
            "password", "secret", "confidential", "api_key", "token", "credential",
        ]

    def contains_sensitive(self, text: str) -> bool:
        text_lower = text.lower()
        return any(word.lower() in text_lower for word in self._words)

    @property
    def words(self) -> list[str]:
        return list(self._words)


@dataclass
class EmailMessage:
    id: str
    from_addr: str
    to_addr: list[str]
    subject: str
    body: str
    date: str
    attachments: list[dict[str, Any]] = field(default_factory=list)
    unread: bool = True


class MockEmailBackend:
    def __init__(self) -> None:
        self._messages: dict[str, EmailMessage] = {}

    def send(
        self,
        from_addr: str,
        to_addr: list[str],
        subject: str,
        body: str,
        attachments: list[dict[str, Any]] | None = None,
    ) -> str:
        msg_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self._messages[msg_id] = EmailMessage(
            id=msg_id,
            from_addr=from_addr,
            to_addr=to_addr,
            subject=subject,
            body=body,
            date=now,
            attachments=attachments or [],
        )
        return msg_id

    def list_emails(self, folder: str = "INBOX", max_count: int = 10) -> list[EmailMessage]:
        messages = sorted(
            self._messages.values(),
            key=lambda m: m.date,
            reverse=True,
        )
        return messages[:max_count]

    def read(self, message_id: str) -> EmailMessage | None:
        msg = self._messages.get(message_id)
        if msg is not None:
            msg.unread = False
        return msg

    def search(self, query: str = "", folder: str = "INBOX") -> list[EmailMessage]:
        if not query:
            return []
        query_lower = query.lower()
        results: list[EmailMessage] = []
        for msg in self._messages.values():
            if (
                query_lower in msg.subject.lower()
                or query_lower in msg.body.lower()
                or query_lower in msg.from_addr.lower()
            ):
                results.append(msg)
        return results


def _sanitize_email(email: str) -> str:
    email = email.strip().lower()
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        return ""
    return email


class EmailServer(MCPServer):
    def __init__(
        self,
        name: str = "maref-email-server",
        version: str = "0.25.0",
        security_gate: Any | None = None,
        smtp_config: dict[str, Any] | None = None,
        imap_config: dict[str, Any] | None = None,
        backend: str = "mock",
        recipient_whitelist: RecipientWhitelist | None = None,
        sensitive_word_filter: SensitiveWordFilter | None = None,
        write_mode: bool = False,
    ) -> None:
        super().__init__(name=name, version=version, security_gate=security_gate)
        self._smtp_config = smtp_config
        self._imap_config = imap_config
        self._backend_type = backend
        self._recipient_whitelist = recipient_whitelist or RecipientWhitelist()
        self._sensitive_word_filter = sensitive_word_filter or SensitiveWordFilter()
        self._write_mode = write_mode
        self._mock_backend = MockEmailBackend()
        self._register_tools()

    def _register_tools(self) -> None:
        self.register_tool(
            name="email_send",
            description="Send an email to one or more recipients",
            input_schema={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "Email body content"},
                    "attachments": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "filename": {"type": "string"},
                                "content": {"type": "string"},
                            },
                        },
                        "description": "Optional list of attachments",
                    },
                },
                "required": ["to", "subject", "body"],
            },
            handler=self._handle_email_send,
        )
        self.register_tool(
            name="email_list",
            description="List emails in a folder",
            input_schema={
                "type": "object",
                "properties": {
                    "folder": {"type": "string", "description": "Folder name (default: INBOX)"},
                    "max_count": {"type": "integer", "description": "Maximum number of emails to return (default: 10)"},
                },
            },
            handler=self._handle_email_list,
        )
        self.register_tool(
            name="email_read",
            description="Read an email by message ID",
            input_schema={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string", "description": "Message ID of the email to read"},
                },
                "required": ["message_id"],
            },
            handler=self._handle_email_read,
        )
        self.register_tool(
            name="email_search",
            description="Search emails by query text",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query text"},
                    "folder": {"type": "string", "description": "Folder to search in (default: INBOX)"},
                },
            },
            handler=self._handle_email_search,
        )

    def _handle_email_send(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self._write_mode:
            return {"success": False, "message_id": "", "to": "", "subject": ""}

        to = args.get("to", "")
        subject = args.get("subject", "")
        body = args.get("body", "")
        attachments = args.get("attachments")

        sanitized_to = _sanitize_email(to)
        if not sanitized_to:
            return {"success": False, "message_id": "", "to": to, "subject": subject}

        if self._recipient_whitelist.patterns and not self._recipient_whitelist.is_allowed(to):
            return {"success": False, "message_id": "", "to": to, "subject": subject}

        if self._sensitive_word_filter.contains_sensitive(subject):
            return {"success": False, "message_id": "", "to": to, "subject": subject}

        if self._sensitive_word_filter.contains_sensitive(body):
            return {"success": False, "message_id": "", "to": to, "subject": subject}

        parsed_attachments: list[dict[str, Any]] = []
        if isinstance(attachments, list):
            for att in attachments:
                parsed_attachments.append({
                    "filename": att.get("filename", "attachment"),
                    "size": len(att.get("content", "")),
                })

        msg_id = self._mock_backend.send(
            from_addr="maref@localhost",
            to_addr=[sanitized_to],
            subject=subject,
            body=body,
            attachments=parsed_attachments,
        )

        return {"success": True, "message_id": msg_id, "to": sanitized_to, "subject": subject}

    def _handle_email_list(self, args: dict[str, Any]) -> dict[str, Any]:
        folder = args.get("folder", "INBOX")
        max_count = int(args.get("max_count", 10))
        emails = self._mock_backend.list_emails(folder=folder, max_count=max_count)
        return {
            "emails": [
                {
                    "id": e.id,
                    "from": e.from_addr,
                    "subject": e.subject,
                    "date": e.date,
                    "unread": e.unread,
                }
                for e in emails
            ],
            "count": len(emails),
            "folder": folder,
        }

    def _handle_email_read(self, args: dict[str, Any]) -> dict[str, Any]:
        message_id = args.get("message_id", "")
        msg = self._mock_backend.read(message_id)
        if msg is None:
            return {"id": "", "from": "", "to": [], "subject": "", "date": "", "body": "", "attachments": []}
        return {
            "id": msg.id,
            "from": msg.from_addr,
            "to": msg.to_addr,
            "subject": msg.subject,
            "date": msg.date,
            "body": msg.body,
            "attachments": msg.attachments,
        }

    def _handle_email_search(self, args: dict[str, Any]) -> dict[str, Any]:
        query = args.get("query", "")
        folder = args.get("folder", "INBOX")
        results = self._mock_backend.search(query=query, folder=folder)
        return {
            "results": [
                {
                    "id": r.id,
                    "subject": r.subject,
                    "from": r.from_addr,
                    "date": r.date,
                }
                for r in results
            ],
            "count": len(results),
            "query": query,
        }


def create_email_server(
    recipient_whitelist: list[str] | None = None,
    sensitive_words: list[str] | None = None,
    write_mode: bool = False,
    smtp_config: dict[str, Any] | None = None,
    imap_config: dict[str, Any] | None = None,
    backend: str = "mock",
) -> EmailServer:
    whitelist = RecipientWhitelist(recipient_whitelist) if recipient_whitelist else None
    word_filter = SensitiveWordFilter(sensitive_words) if sensitive_words else None
    return EmailServer(
        smtp_config=smtp_config,
        imap_config=imap_config,
        backend=backend,
        recipient_whitelist=whitelist,
        sensitive_word_filter=word_filter,
        write_mode=write_mode,
    )
