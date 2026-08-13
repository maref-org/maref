from __future__ import annotations

from maref.integration.mcp_envelope import make_envelope
from maref.integration.mcp_transport import JSONRPCRequest
from maref.tools.email_server import (
    EmailServer,
    MockEmailBackend,
    RecipientWhitelist,
    SensitiveWordFilter,
    create_email_server,
)


class TestRecipientWhitelist:
    def test_exact_email_match(self):
        whitelist = RecipientWhitelist(["alice@example.com"])
        assert whitelist.is_allowed("alice@example.com")
        assert not whitelist.is_allowed("bob@example.com")

    def test_domain_pattern_match(self):
        whitelist = RecipientWhitelist(["*.example.com"])
        assert whitelist.is_allowed("alice@example.com")
        assert whitelist.is_allowed("bob@example.com")
        assert not whitelist.is_allowed("alice@other.com")

    def test_empty_whitelist_allows_none(self):
        whitelist = RecipientWhitelist([])
        assert not whitelist.is_allowed("alice@example.com")

    def test_default_whitelist_empty(self):
        whitelist = RecipientWhitelist()
        assert whitelist.patterns == []

    def test_invalid_email_not_allowed(self):
        whitelist = RecipientWhitelist(["*.example.com"])
        assert not whitelist.is_allowed("not-an-email")

    def test_multiple_patterns(self):
        whitelist = RecipientWhitelist(["alice@example.com", "*.corp.com"])
        assert whitelist.is_allowed("alice@example.com")
        assert whitelist.is_allowed("bob@corp.com")
        assert not whitelist.is_allowed("charlie@other.com")


class TestSensitiveWordFilter:
    def test_default_words_contain_sensitive(self):
        word_filter = SensitiveWordFilter()
        assert "password" in word_filter.words
        assert "secret" in word_filter.words
        assert "confidential" in word_filter.words
        assert "api_key" in word_filter.words
        assert "token" in word_filter.words
        assert "credential" in word_filter.words

    def test_contains_sensitive_case_insensitive(self):
        word_filter = SensitiveWordFilter(["password"])
        assert word_filter.contains_sensitive("My Password is 123")
        assert word_filter.contains_sensitive("my PASSWORD is 123")
        assert word_filter.contains_sensitive("password")

    def test_contains_sensitive_partial_match(self):
        word_filter = SensitiveWordFilter(["secret"])
        assert word_filter.contains_sensitive("This is a secret message")
        assert word_filter.contains_sensitive("secretary")  # partial match
        assert not word_filter.contains_sensitive("This is safe")

    def test_no_sensitive_content(self):
        word_filter = SensitiveWordFilter(["password", "secret"])
        assert not word_filter.contains_sensitive("Hello, this is a normal email")
        assert not word_filter.contains_sensitive("Just checking in")

    def test_custom_words(self):
        word_filter = SensitiveWordFilter(["custom_sensitive"])
        assert word_filter.contains_sensitive("custom_sensitive data")
        assert not word_filter.contains_sensitive("password")


class TestMockEmailBackend:
    def test_send_and_list(self):
        backend = MockEmailBackend()
        msg_id = backend.send(
            from_addr="alice@example.com",
            to_addr=["bob@example.com"],
            subject="Hello",
            body="Hi Bob!",
        )
        messages = backend.list_emails()
        assert len(messages) == 1
        assert messages[0].id == msg_id
        assert messages[0].subject == "Hello"
        assert messages[0].from_addr == "alice@example.com"

    def test_read_marks_as_read(self):
        backend = MockEmailBackend()
        msg_id = backend.send(
            from_addr="alice@example.com",
            to_addr=["bob@example.com"],
            subject="Hello",
            body="Hi Bob!",
        )
        msg = backend.read(msg_id)
        assert msg is not None
        assert msg.unread is False
        assert msg.subject == "Hello"
        assert msg.body == "Hi Bob!"

    def test_read_nonexistent(self):
        backend = MockEmailBackend()
        assert backend.read("nonexistent") is None

    def test_search_by_subject(self):
        backend = MockEmailBackend()
        backend.send(
            from_addr="a@x.com", to_addr=["b@x.com"], subject="Meeting tomorrow", body="Details"
        )
        backend.send(from_addr="c@x.com", to_addr=["d@x.com"], subject="Lunch", body="Pizza?")
        results = backend.search(query="meeting")
        assert len(results) == 1
        assert results[0].subject == "Meeting tomorrow"

    def test_search_by_body(self):
        backend = MockEmailBackend()
        backend.send(from_addr="a@x.com", to_addr=["b@x.com"], subject="Hi", body="Meeting at 3pm")
        results = backend.search(query="3pm")
        assert len(results) == 1

    def test_search_by_from(self):
        backend = MockEmailBackend()
        backend.send(from_addr="alice@example.com", to_addr=["b@x.com"], subject="Hi", body="Hello")
        results = backend.search(query="alice")
        assert len(results) == 1

    def test_search_empty_query(self):
        backend = MockEmailBackend()
        backend.send(from_addr="a@x.com", to_addr=["b@x.com"], subject="Hi", body="Hello")
        results = backend.search(query="")
        assert results == []

    def test_list_max_count(self):
        backend = MockEmailBackend()
        for i in range(5):
            backend.send(
                from_addr=f"a{i}@x.com",
                to_addr=["b@x.com"],
                subject=f"Subject {i}",
                body=f"Body {i}",
            )
        messages = backend.list_emails(max_count=3)
        assert len(messages) == 3

    def test_list_returns_newest_first(self):
        backend = MockEmailBackend()
        ids = []
        for i in range(3):
            msg_id = backend.send(
                from_addr=f"a{i}@x.com",
                to_addr=["b@x.com"],
                subject=f"Subject {i}",
                body=f"Body {i}",
            )
            ids.append(msg_id)
        messages = backend.list_emails()
        assert messages[0].id == ids[2]

    def test_search_case_insensitive(self):
        backend = MockEmailBackend()
        backend.send(from_addr="a@x.com", to_addr=["b@x.com"], subject="HELLO World", body="Test")
        results = backend.search(query="hello")
        assert len(results) == 1
        results = backend.search(query="HELLO")
        assert len(results) == 1

    def test_search_with_attachments(self):
        backend = MockEmailBackend()
        backend.send(
            from_addr="a@x.com",
            to_addr=["b@x.com"],
            subject="With attachment",
            body="See attached",
            attachments=[{"filename": "doc.pdf", "size": 1024}],
        )
        msg = backend.read(list(backend._messages.keys())[0])
        assert msg is not None
        assert len(msg.attachments) == 1
        assert msg.attachments[0]["filename"] == "doc.pdf"


class TestEmailServerSend:
    def test_send_email_with_write_mode(self):
        server = EmailServer(write_mode=True)
        req = JSONRPCRequest(
            method="tools/call",
            params={
                **make_envelope("test-agent"),
                "name": "email_send",
                "arguments": {
                    "to": "bob@example.com",
                    "subject": "Hello",
                    "body": "Hi Bob!",
                },
            },
            id=1,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["success"] is True
        assert resp.result["to"] == "bob@example.com"
        assert resp.result["subject"] == "Hello"
        assert len(resp.result["message_id"]) > 0

    def test_send_blocked_without_write_mode(self):
        server = EmailServer(write_mode=False)
        req = JSONRPCRequest(
            method="tools/call",
            params={
                **make_envelope("test-agent"),
                "name": "email_send",
                "arguments": {
                    "to": "bob@example.com",
                    "subject": "Hello",
                    "body": "Hi Bob!",
                },
            },
            id=1,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["success"] is False
        assert resp.result["message_id"] == ""

    def test_send_blocked_by_whitelist(self):
        server = EmailServer(
            recipient_whitelist=RecipientWhitelist(["alice@example.com"]),
            write_mode=True,
        )
        req = JSONRPCRequest(
            method="tools/call",
            params={
                **make_envelope("test-agent"),
                "name": "email_send",
                "arguments": {
                    "to": "bob@example.com",
                    "subject": "Hello",
                    "body": "Hi Bob!",
                },
            },
            id=1,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["success"] is False

    def test_send_allowed_by_whitelist(self):
        server = EmailServer(
            recipient_whitelist=RecipientWhitelist(["alice@example.com"]),
            write_mode=True,
        )
        req = JSONRPCRequest(
            method="tools/call",
            params={
                **make_envelope("test-agent"),
                "name": "email_send",
                "arguments": {
                    "to": "alice@example.com",
                    "subject": "Hello",
                    "body": "Hi!",
                },
            },
            id=1,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["success"] is True

    def test_send_blocked_by_sensitive_word_in_subject(self):
        server = EmailServer(write_mode=True)
        req = JSONRPCRequest(
            method="tools/call",
            params={
                **make_envelope("test-agent"),
                "name": "email_send",
                "arguments": {
                    "to": "bob@example.com",
                    "subject": "My password is 123",
                    "body": "Normal body",
                },
            },
            id=1,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["success"] is False

    def test_send_blocked_by_sensitive_word_in_body(self):
        server = EmailServer(write_mode=True)
        req = JSONRPCRequest(
            method="tools/call",
            params={
                **make_envelope("test-agent"),
                "name": "email_send",
                "arguments": {
                    "to": "bob@example.com",
                    "subject": "Normal subject",
                    "body": "This contains confidential information",
                },
            },
            id=1,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["success"] is False

    def test_send_with_custom_sensitive_words(self):
        server = EmailServer(
            sensitive_word_filter=SensitiveWordFilter(["custom_secret"]),
            write_mode=True,
        )
        req = JSONRPCRequest(
            method="tools/call",
            params={
                **make_envelope("test-agent"),
                "name": "email_send",
                "arguments": {
                    "to": "bob@example.com",
                    "subject": "Normal",
                    "body": "This has custom_secret data",
                },
            },
            id=1,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["success"] is False

    def test_send_with_attachments(self):
        server = EmailServer(write_mode=True)
        req = JSONRPCRequest(
            method="tools/call",
            params={
                **make_envelope("test-agent"),
                "name": "email_send",
                "arguments": {
                    "to": "bob@example.com",
                    "subject": "With files",
                    "body": "Check attachments",
                    "attachments": [
                        {"filename": "report.pdf", "content": "PDF content here"},
                    ],
                },
            },
            id=1,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["success"] is True

    def test_send_invalid_email(self):
        server = EmailServer(write_mode=True)
        req = JSONRPCRequest(
            method="tools/call",
            params={
                **make_envelope("test-agent"),
                "name": "email_send",
                "arguments": {
                    "to": "not-an-email",
                    "subject": "Hi",
                    "body": "Hello",
                },
            },
            id=1,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["success"] is False

    def test_send_domain_whitelist_pattern(self):
        server = EmailServer(
            recipient_whitelist=RecipientWhitelist(["*.example.com"]),
            write_mode=True,
        )
        req = JSONRPCRequest(
            method="tools/call",
            params={
                **make_envelope("test-agent"),
                "name": "email_send",
                "arguments": {
                    "to": "user@example.com",
                    "subject": "Hi",
                    "body": "Hello",
                },
            },
            id=1,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["success"] is True

    def test_send_sensitive_word_case_insensitive(self):
        server = EmailServer(write_mode=True)
        req = JSONRPCRequest(
            method="tools/call",
            params={
                **make_envelope("test-agent"),
                "name": "email_send",
                "arguments": {
                    "to": "bob@example.com",
                    "subject": "My PASSWORD is 123",
                    "body": "Normal body",
                },
            },
            id=1,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["success"] is False


class TestEmailServerList:
    def test_list_emails_after_send(self):
        server = EmailServer(write_mode=True)
        server._handle_email_send(
            {
                "to": "bob@example.com",
                "subject": "Test",
                "body": "Body",
            }
        )
        req = JSONRPCRequest(
            method="tools/call",
            params={
                **make_envelope("test-agent"),
                "name": "email_list",
                "arguments": {},
            },
            id=1,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["count"] == 1
        assert len(resp.result["emails"]) == 1
        assert resp.result["emails"][0]["subject"] == "Test"
        assert resp.result["emails"][0]["from"] == "maref@localhost"
        assert resp.result["folder"] == "INBOX"

    def test_list_empty(self):
        server = EmailServer()
        req = JSONRPCRequest(
            method="tools/call",
            params={
                **make_envelope("test-agent"),
                "name": "email_list",
                "arguments": {},
            },
            id=1,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["count"] == 0
        assert resp.result["emails"] == []

    def test_list_with_max_count(self):
        server = EmailServer(write_mode=True)
        for i in range(5):
            server._handle_email_send(
                {
                    "to": f"bob{i}@example.com",
                    "subject": f"Test {i}",
                    "body": f"Body {i}",
                }
            )
        req = JSONRPCRequest(
            method="tools/call",
            params={
                **make_envelope("test-agent"),
                "name": "email_list",
                "arguments": {"max_count": 3},
            },
            id=1,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["count"] == 3

    def test_list_with_custom_folder(self):
        server = EmailServer(write_mode=True)
        server._handle_email_send(
            {
                "to": "bob@example.com",
                "subject": "Test",
                "body": "Body",
            }
        )
        req = JSONRPCRequest(
            method="tools/call",
            params={
                **make_envelope("test-agent"),
                "name": "email_list",
                "arguments": {"folder": "SENT"},
            },
            id=1,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["folder"] == "SENT"


class TestEmailServerRead:
    def test_read_email_by_id(self):
        server = EmailServer(write_mode=True)
        send_result = server._handle_email_send(
            {
                "to": "bob@example.com",
                "subject": "Read test",
                "body": "This is the body content",
            }
        )
        msg_id = send_result["message_id"]
        req = JSONRPCRequest(
            method="tools/call",
            params={
                **make_envelope("test-agent"),
                "name": "email_read",
                "arguments": {"message_id": msg_id},
            },
            id=1,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["id"] == msg_id
        assert resp.result["subject"] == "Read test"
        assert resp.result["body"] == "This is the body content"
        assert resp.result["from"] == "maref@localhost"
        assert resp.result["to"] == ["bob@example.com"]

    def test_read_nonexistent_email(self):
        server = EmailServer()
        req = JSONRPCRequest(
            method="tools/call",
            params={
                **make_envelope("test-agent"),
                "name": "email_read",
                "arguments": {"message_id": "nonexistent-id"},
            },
            id=1,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["id"] == ""

    def test_read_marks_unread_false(self):
        server = EmailServer(write_mode=True)
        send_result = server._handle_email_send(
            {
                "to": "bob@example.com",
                "subject": "Unread test",
                "body": "Body",
            }
        )
        msg_id = send_result["message_id"]
        list_req = JSONRPCRequest(
            method="tools/call",
            params={
                **make_envelope("test-agent"),
                "name": "email_list",
                "arguments": {},
            },
            id=1,
        )
        list_resp = server.handle_request(list_req)
        assert list_resp.result["emails"][0]["unread"] is True
        server._handle_email_read({"message_id": msg_id})
        list_resp2 = server.handle_request(list_req)
        assert list_resp2.result["emails"][0]["unread"] is False


class TestEmailServerSearch:
    def test_search_by_subject(self):
        server = EmailServer(write_mode=True)
        server._handle_email_send(
            {
                "to": "bob@example.com",
                "subject": "Meeting at 3pm",
                "body": "Details here",
            }
        )
        server._handle_email_send(
            {
                "to": "alice@example.com",
                "subject": "Lunch",
                "body": "Pizza?",
            }
        )
        req = JSONRPCRequest(
            method="tools/call",
            params={
                **make_envelope("test-agent"),
                "name": "email_search",
                "arguments": {"query": "Meeting"},
            },
            id=1,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["count"] == 1
        assert resp.result["results"][0]["subject"] == "Meeting at 3pm"
        assert resp.result["query"] == "Meeting"

    def test_search_by_body(self):
        server = EmailServer(write_mode=True)
        server._handle_email_send(
            {
                "to": "bob@example.com",
                "subject": "Hi",
                "body": "Meeting at 3pm tomorrow",
            }
        )
        req = JSONRPCRequest(
            method="tools/call",
            params={
                **make_envelope("test-agent"),
                "name": "email_search",
                "arguments": {"query": "3pm"},
            },
            id=1,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["count"] == 1

    def test_search_case_insensitive(self):
        server = EmailServer(write_mode=True)
        server._handle_email_send(
            {
                "to": "bob@example.com",
                "subject": "HELLO World",
                "body": "Test body",
            }
        )
        req = JSONRPCRequest(
            method="tools/call",
            params={
                **make_envelope("test-agent"),
                "name": "email_search",
                "arguments": {"query": "hello"},
            },
            id=1,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["count"] == 1

    def test_search_no_results(self):
        server = EmailServer(write_mode=True)
        server._handle_email_send(
            {
                "to": "bob@example.com",
                "subject": "Test",
                "body": "Body",
            }
        )
        req = JSONRPCRequest(
            method="tools/call",
            params={
                **make_envelope("test-agent"),
                "name": "email_search",
                "arguments": {"query": "nonexistent"},
            },
            id=1,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["count"] == 0

    def test_search_with_folder(self):
        server = EmailServer(write_mode=True)
        server._handle_email_send(
            {
                "to": "bob@example.com",
                "subject": "Test",
                "body": "Body",
            }
        )
        req = JSONRPCRequest(
            method="tools/call",
            params={
                **make_envelope("test-agent"),
                "name": "email_search",
                "arguments": {"query": "Test", "folder": "INBOX"},
            },
            id=1,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["count"] == 1

    def test_search_empty_query(self):
        server = EmailServer(write_mode=True)
        server._handle_email_send(
            {
                "to": "bob@example.com",
                "subject": "Test",
                "body": "Body",
            }
        )
        req = JSONRPCRequest(
            method="tools/call",
            params={
                **make_envelope("test-agent"),
                "name": "email_search",
                "arguments": {"query": ""},
            },
            id=1,
        )
        resp = server.handle_request(req)
        assert not resp.is_error
        assert resp.result["count"] == 0


class TestEmailServerFactory:
    def test_create_email_server_defaults(self):
        server = create_email_server()
        assert server._write_mode is False
        assert server._backend_type == "mock"
        assert server._recipient_whitelist.patterns == []
        assert "password" in server._sensitive_word_filter.words

    def test_create_email_server_with_whitelist(self):
        server = create_email_server(
            recipient_whitelist=["alice@example.com"],
            write_mode=True,
        )
        assert server._recipient_whitelist.is_allowed("alice@example.com")
        assert not server._recipient_whitelist.is_allowed("bob@example.com")

    def test_create_email_server_with_sensitive_words(self):
        server = create_email_server(
            sensitive_words=["company_secret"],
            write_mode=True,
        )
        assert server._sensitive_word_filter.words == ["company_secret"]
        assert server._sensitive_word_filter.contains_sensitive("company_secret data")

    def test_create_email_server_with_write_mode(self):
        server = create_email_server(write_mode=True)
        assert server._write_mode is True

    def test_create_email_server_with_config(self):
        server = create_email_server(
            smtp_config={"host": "smtp.example.com", "port": 587},
            imap_config={"host": "imap.example.com", "port": 993},
        )
        assert server._smtp_config == {"host": "smtp.example.com", "port": 587}
        assert server._imap_config == {"host": "imap.example.com", "port": 993}


class TestEmailServerIntegration:
    def test_full_flow_send_list_read(self):
        server = EmailServer(write_mode=True)
        send_result = server._handle_email_send(
            {
                "to": "bob@example.com",
                "subject": "Integration test",
                "body": "Testing full flow",
            }
        )
        assert send_result["success"] is True
        msg_id = send_result["message_id"]
        list_result = server._handle_email_list({})
        assert list_result["count"] == 1
        assert list_result["emails"][0]["id"] == msg_id
        read_result = server._handle_email_read({"message_id": msg_id})
        assert read_result["subject"] == "Integration test"
        assert read_result["body"] == "Testing full flow"

    def test_fallback_to_mock_without_config(self):
        server = EmailServer(
            smtp_config=None,
            imap_config=None,
            write_mode=True,
        )
        result = server._handle_email_send(
            {
                "to": "bob@example.com",
                "subject": "Fallback test",
                "body": "Should work with mock backend",
            }
        )
        assert result["success"] is True
        assert len(result["message_id"]) > 0
        list_result = server._handle_email_list({})
        assert list_result["count"] == 1

    def test_sensitive_word_filter_partial_match(self):
        word_filter = SensitiveWordFilter(["secret"])
        assert word_filter.contains_sensitive("secretary meeting")
        assert word_filter.contains_sensitive("topsecret info")
        assert word_filter.contains_sensitive("my secret plan")

    def test_sanitize_email(self):
        from maref.tools.email_server import _sanitize_email

        assert _sanitize_email("  Alice@Example.COM  ") == "alice@example.com"
        assert _sanitize_email("invalid") == ""
        assert _sanitize_email("user@.com") == ""
