from __future__ import annotations

import pytest

from maref.loop.interactive import (
    ConversationContext,
    InteractiveLoop,
    RepetitionDetector,
    SentimentSafetyValve,
)
from maref.loop.protocols import LoopStopReason


class TestSentimentSafetyValve:
    def test_default_not_tripped(self):
        v = SentimentSafetyValve()
        assert v.tripped is False

    def test_escalate_below_threshold(self):
        v = SentimentSafetyValve(threshold=-0.3)
        assert v.should_escalate(-0.5) is True
        assert v.tripped is True

    def test_not_escalate_above_threshold(self):
        v = SentimentSafetyValve(threshold=-0.5)
        assert v.should_escalate(0.0) is False
        assert v.tripped is False

    def test_reset(self):
        v = SentimentSafetyValve(threshold=0.0)
        v.should_escalate(-1.0)
        assert v.tripped is True
        v.reset()
        assert v.tripped is False


class TestRepetitionDetector:
    def test_no_repetition(self):
        d = RepetitionDetector(window=5, max_count=3)
        assert d.check("a") is False
        assert d.check("b") is False

    def test_detects_repetition(self):
        d = RepetitionDetector(window=5, max_count=3)
        d.check("repeat")
        d.check("repeat")
        assert d.check("repeat") is True

    def test_window_slides(self):
        d = RepetitionDetector(window=3, max_count=2)
        d.check("a")
        d.check("b")
        d.check("c")
        d.check("a")
        assert d.check("a") is True
        d.reset()
        assert d.check("a") is False

    def test_reset(self):
        d = RepetitionDetector(window=3, max_count=2)
        d.check("x")
        d.check("x")
        d.reset()
        assert d.check("x") is False


class TestConversationContext:
    def test_add_messages(self):
        ctx = ConversationContext(max_history=10)
        ctx.add_user_message("hello")
        ctx.add_agent_message("hi")
        assert len(ctx.messages) == 2
        assert ctx.turn_count == 1

    def test_turn_count(self):
        ctx = ConversationContext()
        ctx.add_user_message("a")
        assert ctx.turn_count == 0
        ctx.add_agent_message("b")
        assert ctx.turn_count == 1

    def test_trim(self):
        ctx = ConversationContext(max_history=4)
        for i in range(6):
            ctx.add_user_message(f"msg{i}")
            ctx.add_agent_message(f"resp{i}")
        assert len(ctx.messages) == 4

    def test_reset(self):
        ctx = ConversationContext()
        ctx.add_user_message("hello")
        ctx.reset()
        assert ctx.messages == []
        assert ctx.turn_count == 0


class TestInteractiveLoop:
    @pytest.mark.asyncio
    async def test_turn_returns_response(self, mock_respond_fn):
        loop = InteractiveLoop(respond_fn=mock_respond_fn)
        response = await loop.turn("hello")
        assert response.content == "You said: hello"
        assert response.end_conversation is False

    @pytest.mark.asyncio
    async def test_sentiment_escalation(self, mock_respond_fn):
        loop = InteractiveLoop(
            respond_fn=mock_respond_fn,
            sentiment_analyzer=lambda _: -0.9,
            sentiment_threshold=-0.5,
        )
        response = await loop.turn("terrible")
        assert response.escalate is True
        assert response.end_conversation is True

    @pytest.mark.asyncio
    async def test_repetition_escalation(self, mock_respond_fn):
        loop = InteractiveLoop(
            respond_fn=mock_respond_fn,
            intent_classifier=lambda _: "same_intent",
            repetition_max_count=2,
        )
        await loop.turn("a")
        response = await loop.turn("b")
        assert response.escalate is True

    @pytest.mark.asyncio
    async def test_default_intent(self):
        loop = InteractiveLoop(respond_fn=lambda u, c: "ok")
        assert loop._default_intent("  Hello World!  ") == "hello world!"

    @pytest.mark.asyncio
    async def test_default_sentiment(self):
        loop = InteractiveLoop(respond_fn=lambda u, c: "ok")
        neg = loop._default_sentiment("this is bad and terrible")
        assert neg < 0
        pos = loop._default_sentiment("nice day")
        assert pos == 0.0

    @pytest.mark.asyncio
    async def test_detect_end_conversation(self, mock_respond_fn):
        loop = InteractiveLoop(respond_fn=mock_respond_fn)
        assert loop._detect_end_conversation("bye") is True
        assert loop._detect_end_conversation("thank you") is True
        assert loop._detect_end_conversation("continue") is False

    @pytest.mark.asyncio
    async def test_run_returns_summary(self):
        def stopping_respond(user_input, context):
            loop.stop()
            return f"You said: {user_input}"

        loop = InteractiveLoop(respond_fn=stopping_respond, max_turns=5)
        result = await loop.run(greeting="hello", simulated_input="bye")
        assert result.stop_reason == LoopStopReason.MANUAL_STOP
