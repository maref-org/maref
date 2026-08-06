"""Tests for C34: Life State Messaging."""

from __future__ import annotations

import time

from maref.life_state.messaging import (
    LifeStateMessage,
    MessageBus,
    MessageType,
    Priority,
)


class TestMessageType:
    def test_all_types_defined(self):
        assert MessageType.HEARTBEAT.value == "heartbeat"
        assert MessageType.REQUEST.value == "request"
        assert MessageType.RESPONSE.value == "response"
        assert MessageType.EVENT.value == "event"
        assert MessageType.ALERT.value == "alert"


class TestPriority:
    def test_priority_order(self):
        assert Priority.LOW.value == 1
        assert Priority.NORMAL.value == 2
        assert Priority.HIGH.value == 3
        assert Priority.CRITICAL.value == 4


class TestLifeStateMessage:
    def test_default_creation(self):
        msg = LifeStateMessage()
        assert len(msg.msg_id) == 12
        assert msg.msg_type == MessageType.EVENT
        assert msg.sender_id == ""
        assert msg.recipient_id == ""
        assert msg.payload == {}
        assert msg.priority == Priority.NORMAL
        assert msg.timeout_ms == 5000.0

    def test_custom_creation(self):
        msg = LifeStateMessage(
            msg_id="m1",
            msg_type=MessageType.ALERT,
            sender_id="s1",
            recipient_id="r1",
            payload={"key": "val"},
            priority=Priority.CRITICAL,
            timeout_ms=1000.0,
        )
        assert msg.msg_id == "m1"
        assert msg.msg_type == MessageType.ALERT
        assert msg.sender_id == "s1"
        assert msg.recipient_id == "r1"
        assert msg.payload == {"key": "val"}
        assert msg.priority == Priority.CRITICAL
        assert msg.timeout_ms == 1000.0

    def test_not_expired(self):
        msg = LifeStateMessage(timestamp=time.time(), timeout_ms=10000.0)
        assert not msg.is_expired()

    def test_expired(self):
        msg = LifeStateMessage(timestamp=time.time() - 10.0, timeout_ms=1000.0)
        assert msg.is_expired()

    def test_to_dict(self):
        msg = LifeStateMessage(msg_id="m1", msg_type=MessageType.REQUEST)
        d = msg.to_dict()
        assert d["msg_id"] == "m1"
        assert d["msg_type"] == "request"
        assert d["priority"] == 2


class TestMessageBus:
    def test_send_and_store(self):
        bus = MessageBus()
        msg = LifeStateMessage(sender_id="s1", recipient_id="r1")
        bus.send(msg)
        assert bus.count() == 1

    def test_direct_message_delivery(self):
        bus = MessageBus()
        received: list[LifeStateMessage] = []
        bus.subscribe("r1", lambda m: received.append(m))
        msg = LifeStateMessage(sender_id="s1", recipient_id="r1", payload={"data": 1})
        bus.send(msg)
        assert len(received) == 1
        assert received[0].payload["data"] == 1

    def test_broadcast_delivery(self):
        bus = MessageBus()
        received1: list[LifeStateMessage] = []
        received2: list[LifeStateMessage] = []
        bus.subscribe("r1", lambda m: received1.append(m))
        bus.subscribe("r2", lambda m: received2.append(m))
        bus.broadcast("s1", MessageType.EVENT, {"info": "hello"})
        assert len(received1) == 1
        assert len(received2) == 1

    def test_request(self):
        bus = MessageBus()
        received: list[LifeStateMessage] = []
        bus.subscribe("r1", lambda m: received.append(m))
        bus.request("s1", "r1", {"action": "ping"})
        assert len(received) == 1
        assert received[0].msg_type == MessageType.REQUEST

    def test_global_subscription(self):
        bus = MessageBus()
        received: list[LifeStateMessage] = []
        bus.subscribe_global(lambda m: received.append(m))
        bus.send(LifeStateMessage(sender_id="s1"))
        assert len(received) == 1

    def test_unsubscribe(self):
        bus = MessageBus()
        received: list[LifeStateMessage] = []
        handler = lambda m: received.append(m)
        bus.subscribe("r1", handler)
        bus.unsubscribe("r1", handler)
        bus.send(LifeStateMessage(recipient_id="r1"))
        assert len(received) == 0

    def test_get_messages(self):
        bus = MessageBus()
        bus.send(LifeStateMessage(sender_id="s1", recipient_id="r1"))
        bus.send(LifeStateMessage(sender_id="s2", recipient_id="r2"))
        all_msgs = bus.get_messages()
        assert len(all_msgs) == 2
        s1_msgs = bus.get_messages("s1")
        assert len(s1_msgs) == 1

    def test_get_messages_by_type(self):
        bus = MessageBus()
        bus.send(LifeStateMessage(msg_type=MessageType.ALERT))
        bus.send(LifeStateMessage(msg_type=MessageType.EVENT))
        bus.send(LifeStateMessage(msg_type=MessageType.ALERT))
        alerts = bus.get_messages_by_type(MessageType.ALERT)
        assert len(alerts) == 2

    def test_clear(self):
        bus = MessageBus()
        bus.send(LifeStateMessage())
        bus.clear()
        assert bus.count() == 0

    def test_handler_exception_isolated(self):
        bus = MessageBus()
        bus.subscribe("r1", lambda m: (_ for _ in ()).throw(RuntimeError("boom")))
        bus.send(LifeStateMessage(recipient_id="r1"))
        assert bus.count() == 1
