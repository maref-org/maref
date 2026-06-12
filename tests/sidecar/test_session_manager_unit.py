import pytest
from sidecar.session_manager import ChatMessage, Session, SessionManager


class TestSessionManager:
    def test_create_session(self):
        sm = SessionManager()
        s = sm.create_session("Test", "chat", "ollama", "llama3")
        assert s.title == "Test"
        assert s.mode == "chat"
        assert s.provider == "ollama"
        assert s.model == "llama3"
        assert s.id.startswith("sess-")

    def test_list_sessions(self):
        sm = SessionManager()
        sm.create_session("A", "chat", "ollama", "llama3")
        sm.create_session("B", "agent", "openai", "gpt-4")
        assert len(sm.list_sessions()) == 2

    def test_get_session(self):
        sm = SessionManager()
        s = sm.create_session("A", "chat", "ollama", "llama3")
        found = sm.get_session(s.id)
        assert found is not None
        assert found.id == s.id

    def test_get_session_missing(self):
        sm = SessionManager()
        assert sm.get_session("nonexistent") is None

    def test_delete_session(self):
        sm = SessionManager()
        s = sm.create_session("A", "chat", "ollama", "llama3")
        assert sm.delete_session(s.id) is True
        assert sm.get_session(s.id) is None

    def test_delete_session_missing(self):
        sm = SessionManager()
        assert sm.delete_session("x") is False

    def test_update_session(self):
        sm = SessionManager()
        s = sm.create_session("A", "chat", "ollama", "llama3")
        updated = sm.update_session(s.id, title="New")
        assert updated is not None
        assert updated.title == "New"

    def test_update_session_missing(self):
        sm = SessionManager()
        assert sm.update_session("x", title="New") is None

    def test_add_message(self):
        sm = SessionManager()
        s = sm.create_session("A", "chat", "ollama", "llama3")
        msg = sm.add_message(s.id, "user", "hello")
        assert msg is not None
        assert msg.role == "user"
        assert msg.content == "hello"

    def test_add_message_missing_session(self):
        sm = SessionManager()
        assert sm.add_message("x", "user", "hello") is None

    def test_get_messages(self):
        sm = SessionManager()
        s = sm.create_session("A", "chat", "ollama", "llama3")
        sm.add_message(s.id, "user", "hello")
        msgs = sm.get_messages(s.id)
        assert len(msgs) == 1

    def test_get_messages_missing(self):
        sm = SessionManager()
        assert sm.get_messages("x") == []

    def test_update_message(self):
        sm = SessionManager()
        s = sm.create_session("A", "chat", "ollama", "llama3")
        msg = sm.add_message(s.id, "assistant", "draft")
        assert sm.update_message(s.id, msg.id, "final", "complete") is True
        msgs = sm.get_messages(s.id)
        assert msgs[0].content == "final"
        assert msgs[0].status == "complete"

    def test_update_message_missing(self):
        sm = SessionManager()
        s = sm.create_session("A", "chat", "ollama", "llama3")
        assert sm.update_message(s.id, "bad-id", "x", "complete") is False


class TestChatMessage:
    def test_to_dict(self):
        msg = ChatMessage(id="m1", session_id="s1", role="user", content="hi")
        d = msg.to_dict()
        assert d["id"] == "m1"
        assert d["role"] == "user"
        assert d["content"] == "hi"


class TestSession:
    def test_to_dict(self):
        s = Session(id="s1", title="T", mode="chat", provider="p", model="m")
        d = s.to_dict()
        assert d["id"] == "s1"
        assert d["title"] == "T"
        assert d["mode"] == "chat"
