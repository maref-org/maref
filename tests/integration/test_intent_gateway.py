"""Tests for Intent Gateway — input normalization."""

import pytest

from maref.integration.intent_gateway import (
    InputSource,
    IntentClassifier,
    IntentGateway,
    IntentType,
)


class TestIntentClassifier:
    def test_classify_task(self):
        assert IntentClassifier.classify("analyze sales data") == IntentType.TASK
        assert IntentClassifier.classify("generate report") == IntentType.TASK

    def test_classify_command(self):
        assert IntentClassifier.classify("/deploy") == IntentType.COMMAND
        assert IntentClassifier.classify("!run tests") == IntentType.COMMAND

    def test_classify_preference(self):
        assert IntentClassifier.classify("always use local model") == IntentType.PREFERENCE
        assert IntentClassifier.classify("remember my setting") == IntentType.PREFERENCE

    def test_classify_feedback(self):
        assert IntentClassifier.classify("good job") == IntentType.FEEDBACK
        assert IntentClassifier.classify("fix the output format") == IntentType.FEEDBACK

    def test_classify_query(self):
        assert IntentClassifier.classify("what is the weather today") == IntentType.QUERY

    def test_classify_empty_unknown(self):
        assert IntentClassifier.classify("") == IntentType.UNKNOWN


class TestIntentGateway:
    def test_process_normalizes_input(self):
        gateway = IntentGateway()
        event = gateway.process(
            source=InputSource.HTTP,
            raw_input="analyze sales data for Q2",
            user_id="user-1",
            session_id="sess-1",
        )
        assert event.intent_type == IntentType.TASK
        assert event.user_id == "user-1"
        assert event.session_id == "sess-1"
        assert event.source == InputSource.HTTP
        assert event.event_id is not None

    def test_rejects_empty_input(self):
        gateway = IntentGateway()
        with pytest.raises(ValueError, match="empty"):
            gateway.process(source=InputSource.HTTP, raw_input="")

    def test_rejects_oversized_input(self):
        gateway = IntentGateway()
        with pytest.raises(ValueError, match="exceeds"):
            gateway.process(source=InputSource.HTTP, raw_input="x" * 60_000)

    def test_stores_event_history(self):
        gateway = IntentGateway()
        gateway.process(source=InputSource.HTTP, raw_input="hello")
        gateway.process(source=InputSource.CLI, raw_input="world")
        events = gateway.get_recent_events(10)
        assert len(events) == 2

    def test_clear_events(self):
        gateway = IntentGateway()
        gateway.process(source=InputSource.HTTP, raw_input="test")
        gateway.clear_events()
        assert len(gateway.get_recent_events()) == 0
