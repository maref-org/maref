from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable
from typing import Any

from maref.loop.base import LoopBase, LoopResult
from maref.loop.protocols import (
    AgentResponse,
    ConversationSummary,
    LoopStopReason,
    ToolBoundary,
    TurnResult,
)


class SentimentSafetyValve:
    def __init__(self, threshold: float = -0.5):
        self._threshold = threshold
        self._tripped = False

    @property
    def tripped(self) -> bool:
        return self._tripped

    def should_escalate(self, sentiment_score: float) -> bool:
        if sentiment_score < self._threshold:
            self._tripped = True
            return True
        return False

    def reset(self) -> None:
        self._tripped = False


class RepetitionDetector:
    def __init__(self, window: int = 5, max_count: int = 3):
        self._window = window
        self._max_count = max_count
        self._intents: list[str] = []

    def check(self, intent: str) -> bool:
        self._intents.append(intent)
        if len(self._intents) > self._window:
            self._intents.pop(0)
        counts = Counter(self._intents)
        return counts[intent] >= self._max_count

    def reset(self) -> None:
        self._intents.clear()


class ConversationContext:
    def __init__(self, max_history: int = 50):
        self._messages: list[dict[str, str]] = []
        self._max_history = max_history

    def add_user_message(self, content: str) -> None:
        self._messages.append({"role": "user", "content": content})
        self._trim()

    def add_agent_message(self, content: str) -> None:
        self._messages.append({"role": "agent", "content": content})
        self._trim()

    @property
    def messages(self) -> list[dict[str, str]]:
        return list(self._messages)

    @property
    def turn_count(self) -> int:
        return len(self._messages) // 2

    def _trim(self) -> None:
        if len(self._messages) > self._max_history:
            self._messages = self._messages[-self._max_history:]

    def reset(self) -> None:
        self._messages.clear()


class InteractiveLoop(LoopBase):
    END_PHRASES = {"再见", "bye", "goodbye", "没事了", "解决了", "thank you", "thanks"}

    def __init__(
        self,
        respond_fn: Callable[[str, list[dict[str, str]]], str],
        intent_classifier: Callable[[str], str] | None = None,
        sentiment_analyzer: Callable[[str], float] | None = None,
        knowledge_matcher: Callable[[str], float] | None = None,
        tool_boundary: ToolBoundary | None = None,
        max_turns: int = 50,
        sentiment_threshold: float = -0.5,
        repetition_window: int = 5,
        repetition_max_count: int = 3,
        human_escalation_timeout: float = 300.0,
    ):
        super().__init__(None, tool_boundary, max_turns)
        self._respond_fn = respond_fn
        self._intent_classifier = intent_classifier or self._default_intent
        self._sentiment_analyzer = sentiment_analyzer or self._default_sentiment
        self._knowledge_matcher = knowledge_matcher
        self._context = ConversationContext()
        self._safety_valve = SentimentSafetyValve(sentiment_threshold)
        self._repetition_detector = RepetitionDetector(repetition_window, repetition_max_count)
        self._human_escalation_timeout = human_escalation_timeout
        self._turns: list[TurnResult] = []
        self._escalation_count = 0
        self._compliance_issues: list[str] = []

    @staticmethod
    def _default_intent(user_input: str) -> str:
        return user_input.lower().strip()[:50]

    @staticmethod
    def _default_sentiment(user_input: str) -> float:
        negative_words = {"bad", "terrible", "awful", "angry", "frustrated", "mad", "wrong", "error"}
        words = set(user_input.lower().split())
        if not words:
            return 0.0
        ratio = len(words & negative_words) / len(words)
        return -ratio

    async def turn(self, user_input: str) -> AgentResponse:
        turn_id = len(self._turns)
        self._context.add_user_message(user_input)
        start_ms = int(time.time() * 1000)

        sentiment = self._sentiment_analyzer(user_input)
        if self._safety_valve.should_escalate(sentiment):
            self._escalation_count += 1
            return AgentResponse(
                content="I'll transfer you to a human agent who can better assist you.",
                end_conversation=True,
                escalate=True,
            )

        intent = self._intent_classifier(user_input)
        if self._repetition_detector.check(intent):
            self._escalation_count += 1
            return AgentResponse(
                content="I notice this issue may need specialized assistance. Let me connect you with a human agent.",
                end_conversation=True,
                escalate=True,
            )

        knowledge_match = 0.0
        if self._knowledge_matcher:
            knowledge_match = self._knowledge_matcher(user_input)

        reply = self._respond_fn(user_input, self._context.messages)
        self._context.add_agent_message(reply)
        elapsed_ms = int(time.time() * 1000) - start_ms

        turn_result = TurnResult(
            turn_id=turn_id,
            user_input=user_input,
            agent_response=reply,
            sentiment_score=sentiment,
            intent_match=True,
            knowledge_match=knowledge_match,
            response_time_ms=elapsed_ms,
        )
        self._turns.append(turn_result)

        if self._detect_end_conversation(user_input):
            return AgentResponse(content=reply, end_conversation=True)

        if self._context.turn_count >= self._max_rounds:
            return AgentResponse(
                content=reply,
                end_conversation=True,
            )

        return AgentResponse(content=reply)

    @staticmethod
    def _detect_end_conversation(user_input: str) -> bool:
        lower = user_input.lower().strip()
        return any(phrase in lower for phrase in InteractiveLoop.END_PHRASES)

    async def run(self, *args: Any, **kwargs: Any) -> LoopResult[Any]:
        greeting = args[0] if args else kwargs.get("greeting", "Hello! How can I help you?")
        self._running = True

        while self._running:
            response = AgentResponse(content=greeting)

            while not response.end_conversation:
                if not self._running:
                    break
                user_input = kwargs.get("simulated_input")
                if not user_input:
                    break
                response = await self.turn(user_input)

        summary = ConversationSummary(
            turns=list(self._turns),
            total_turns=self._context.turn_count,
            resolved=response.end_conversation,
            escalation_count=self._escalation_count,
            compliance_issues=list(self._compliance_issues),
        )

        stop_reason = LoopStopReason.USER_ENDED
        if self._escalation_count > 0 and self._safety_valve.tripped:
            stop_reason = LoopStopReason.SENTIMENT_TRIP
        elif self._context.turn_count >= self._max_rounds:
            stop_reason = LoopStopReason.MAX_ROUNDS
        elif not self._running:
            stop_reason = LoopStopReason.MANUAL_STOP

        return LoopResult(
            output=summary,
            stop_reason=stop_reason,
            rounds_completed=self._context.turn_count,
        )
