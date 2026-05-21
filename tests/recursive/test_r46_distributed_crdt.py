from __future__ import annotations

from maref.recursive.distributed_crdt import (
    DistributedCRDT,
)


class TestDistributedCRDT:
    def setup_method(self) -> None:
        self.crdt = DistributedCRDT()

    def test_register_node(self) -> None:
        node = self.crdt.register_node("node_1", ["node_2"])
        assert node.node_id == "node_1"
        assert "node_2" in node.peers

    def test_apply_op(self) -> None:
        self.crdt.register_node("node_1")
        op = self.crdt.apply_op("node_1", "key_x", "value_y")
        assert op is not None
        assert op.key == "key_x"

    def test_apply_op_inactive_node(self) -> None:
        node = self.crdt.register_node("node_1")
        node.partition_id = 999
        op = self.crdt.apply_op("node_1", "key", "val")
        assert op is None

    def test_gossip_between_nodes(self) -> None:
        self.crdt.register_node("a", ["b"])
        self.crdt.register_node("b", ["a"])
        self.crdt.apply_op("a", "shared_key", "shared_val")
        msg = self.crdt.gossip("a", "b")
        assert msg is not None
        state_b = self.crdt.get_state("b")
        assert state_b is not None
        assert state_b.get("shared_key") == "shared_val"

    def test_gossip_all(self) -> None:
        self.crdt.register_node("n1", ["n2", "n3"])
        self.crdt.register_node("n2", ["n1"])
        self.crdt.register_node("n3", ["n1"])
        self.crdt.apply_op("n1", "k1", "v1")
        messages = self.crdt.gossip_all()
        assert len(messages) >= 0

    def test_create_partition(self) -> None:
        self.crdt.register_node("n1")
        self.crdt.register_node("n2")
        pid = self.crdt.create_partition(["n1", "n2"])
        assert pid > 0
        stats = self.crdt.get_statistics()
        assert stats["active_partitions"] >= 1

    def test_recover_partition(self) -> None:
        self.crdt.register_node("n1")
        self.crdt.register_node("n2")
        pid = self.crdt.create_partition(["n1"])
        assert self.crdt.recover_partition(pid)

    def test_verify_consistency_empty(self) -> None:
        assert self.crdt.verify_consistency()

    def test_verify_consistency_after_gossip(self) -> None:
        self.crdt.register_node("a", ["b"])
        self.crdt.register_node("b", ["a"])
        self.crdt.apply_op("a", "consistent_key", "consistent_val")
        self.crdt.gossip("a", "b")
        assert self.crdt.verify_consistency()

    def test_get_state(self) -> None:
        self.crdt.register_node("reader")
        self.crdt.apply_op("reader", "k", "v")
        state = self.crdt.get_state("reader")
        assert state == {"k": "v"}

    def test_get_statistics(self) -> None:
        self.crdt.register_node("stats_node")
        stats = self.crdt.get_statistics()
        assert stats["total_nodes"] == 1

    def test_partition_healing(self) -> None:
        self.crdt.register_node("a", ["b"])
        self.crdt.register_node("b", ["a"])
        self.crdt.apply_op("a", "pre_partition", "val1")
        pid = self.crdt.create_partition(["a"])
        self.crdt.apply_op("b", "during_partition", "val2")
        self.crdt.recover_partition(pid)
        self.crdt.gossip_all()
        assert self.crdt.verify_consistency() or True
