from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from maref.recursive.unified_audit import UnifiedAuditRecord, UnifiedAuditStore, make_record_id


@dataclass
class CRDTNode:
    node_id: str
    state: dict[str, Any] = field(default_factory=dict)
    vector_clock: dict[str, int] = field(default_factory=dict)
    peers: list[str] = field(default_factory=list)
    last_sync: float = field(default_factory=time.time)
    partition_id: int = 0

    @property
    def is_active(self) -> bool:
        return self.partition_id == 0


@dataclass
class CRDTOp:
    op_id: str
    op_type: str
    key: str
    value: Any
    node_id: str
    timestamp: float = field(default_factory=time.time)
    vector_clock: dict[str, int] = field(default_factory=dict)


@dataclass
class GossipMessage:
    source_node: str
    target_node: str
    ops: list[CRDTOp] = field(default_factory=list)
    vector_clock: dict[str, int] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class PartitionEvent:
    partition_id: int
    nodes: list[str]
    start_time: float
    end_time: float = 0.0
    recovered: bool = False


class DistributedCRDT:
    MERGE_RETRY_MAX = 3

    def __init__(self, audit_store: UnifiedAuditStore | None = None) -> None:
        self._nodes: dict[str, CRDTNode] = {}
        self._ops: dict[str, CRDTOp] = {}
        self._partitions: list[PartitionEvent] = []
        self._gossip_log: list[GossipMessage] = []
        self._audit_store = audit_store or UnifiedAuditStore()

    def register_node(self, node_id: str,
                       peers: list[str] | None = None) -> CRDTNode:
        node = CRDTNode(
            node_id=node_id,
            vector_clock={node_id: 0},
            peers=peers or [],
        )
        self._nodes[node_id] = node
        return node

    def apply_op(self, node_id: str, key: str, value: Any,
                  op_type: str = "set") -> CRDTOp | None:
        node = self._nodes.get(node_id)
        if node is None or not node.is_active:
            return None

        node.vector_clock[node_id] = node.vector_clock.get(node_id, 0) + 1
        op = CRDTOp(
            op_id=f"op_{node_id}_{node.vector_clock[node_id]}_{int(time.time() * 1000)}",
            op_type=op_type,
            key=key,
            value=value,
            node_id=node_id,
            vector_clock=dict(node.vector_clock),
        )
        node.state[key] = value
        self._ops[op.op_id] = op
        return op

    def gossip(self, source_id: str, target_id: str) -> GossipMessage | None:
        source = self._nodes.get(source_id)
        target = self._nodes.get(target_id)
        if source is None or target is None:
            return None
        if source.partition_id != target.partition_id:
            if source.partition_id >= 0 and target.partition_id >= 0:
                return None

        recent_ops = self._ops_to_sync(source_id, target_id)
        msg = GossipMessage(
            source_node=source_id,
            target_node=target_id,
            ops=recent_ops,
            vector_clock=dict(source.vector_clock),
        )
        self._gossip_log.append(msg)

        self._merge(target_id, msg.ops)
        target.last_sync = time.time()
        return msg

    def gossip_all(self) -> list[GossipMessage]:
        messages: list[GossipMessage] = []
        for source_id, source in self._nodes.items():
            if not source.is_active:
                continue
            for target_id in source.peers:
                if target_id in self._nodes:
                    msg = self.gossip(source_id, target_id)
                    if msg:
                        messages.append(msg)
        return messages

    def create_partition(self, partition_nodes: list[str]) -> int:
        partition_id = int(time.time() * 1000) % 100000
        event = PartitionEvent(
            partition_id=partition_id,
            nodes=list(partition_nodes),
            start_time=time.time(),
        )
        for node_id in partition_nodes:
            node = self._nodes.get(node_id)
            if node:
                node.partition_id = partition_id
        self._partitions.append(event)

        self._audit_store.append(UnifiedAuditRecord(
            record_id=make_record_id("part", partition_id % 100000),
            timestamp=time.time(),
            layer="evolution",
            round=46,
            event_type="network_partition",
            source_module="DistributedCRDT",
            target_module="cluster",
            decision=f"partition_{partition_id}",
            justification=f"Nodes isolated: {len(partition_nodes)}",
            outcome="partition",
            context_refs=partition_nodes,
        ))
        return partition_id

    def recover_partition(self, partition_id: int) -> bool:
        event = None
        for e in self._partitions:
            if e.partition_id == partition_id and not e.recovered:
                event = e
                break
        if event is None:
            return False

        for node_id in event.nodes:
            node = self._nodes.get(node_id)
            if node:
                node.partition_id = 0
        event.end_time = time.time()
        event.recovered = True

        self._heal_after_partition(event.nodes)
        return True

    def get_state(self, node_id: str) -> dict[str, Any] | None:
        node = self._nodes.get(node_id)
        return dict(node.state) if node else None

    def verify_consistency(self) -> bool:
        states: list[dict[str, Any]] = []
        for node in self._nodes.values():
            if node.is_active and node.partition_id == 0:
                states.append(node.state)

        if len(states) < 2:
            return True

        base = sorted(states[0].items())
        return all(sorted(s.items()) == base for s in states[1:])

    def get_statistics(self) -> dict[str, Any]:
        return {
            "total_nodes": len(self._nodes),
            "active_nodes": sum(1 for n in self._nodes.values() if n.is_active),
            "total_ops": len(self._ops),
            "gossip_messages": len(self._gossip_log),
            "partitions": len(self._partitions),
            "active_partitions": sum(
                1 for p in self._partitions if not p.recovered
            ),
            "consistent": self.verify_consistency(),
        }

    def _merge(self, node_id: str, ops: list[CRDTOp]) -> None:
        node = self._nodes.get(node_id)
        if node is None:
            return
        for op in ops:
            node.state[op.key] = op.value
            node.vector_clock = self._max_merge(node.vector_clock, op.vector_clock)

    def _max_merge(self, a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
        result = dict(a)
        for k, v in b.items():
            result[k] = max(result.get(k, 0), v)
        return result

    def _ops_to_sync(self, source_id: str, target_id: str) -> list[CRDTOp]:
        source = self._nodes.get(source_id)
        target = self._nodes.get(target_id)
        if source is None or target is None:
            return []

        to_sync: list[CRDTOp] = []
        for _op_id, op in self._ops.items():
            if op.node_id == source_id:
                target_vc = target.vector_clock.get(source_id, 0)
                src_vc = op.vector_clock.get(source_id, 0)
                if src_vc > target_vc:
                    to_sync.append(op)
        return to_sync

    def _heal_after_partition(self, nodes: list[str]) -> None:
        for _ in range(self.MERGE_RETRY_MAX):
            for node_id in nodes:
                node = self._nodes.get(node_id)
                if node:
                    for peer_id in node.peers:
                        if peer_id in self._nodes:
                            self.gossip(node_id, peer_id)

    def clear(self) -> None:
        self._nodes.clear()
        self._ops.clear()
        self._partitions.clear()
        self._gossip_log.clear()
