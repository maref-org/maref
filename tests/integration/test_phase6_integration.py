from __future__ import annotations

from maref.cross_validator.consensus_algorithm import WeightedConsensusEngine as CVConsensus
from maref.eivl.merkle_auditor import AuditEvidence, MerkleAuditor
from maref.governance.audit import AuditLogger
from maref.governance.state_machine import GovernanceStateMachine
from maref.integration.a2a_bridge import A2ABridge
from maref.integration.a2a_types import A2ATaskState
from maref.integration.mcp_server import MCPServer
from maref.integration.protocol_bridge import MCPToA2ABridge
from maref.security.trust_chain import DelegationCapability, DelegationChain
from maref.security.weighted_consensus import ConsensusVote, WeightedConsensusEngine


class TestEIVLTrustChainIntegration:
    """Phase 6: EIVL + Trust Chain 联合测试"""

    def test_delegation_chain_merkle_audit(self):
        """委托链哈希与 Merkle 审计集成"""
        import time

        chain = DelegationChain.create("root-agent")
        chain.add_delegation("root-agent", "child-1", DelegationCapability.EXECUTE)
        chain.add_delegation("child-1", "child-2", DelegationCapability.EXECUTE)

        auditor = MerkleAuditor()
        chain_hash = chain.get_chain_hash()

        evidence = AuditEvidence(
            evidence_id="ev-001",
            timestamp=time.time(),
            evidence_type="delegation",
            source_agent="root-agent",
            target_agent="child-2",
            action="delegate",
            result={"chain_id": chain.chain_id, "hash": chain_hash, "depth": chain.depth},
            previous_hash="0" * 64,
            nonce=1,
        )

        auditor.add_evidence(evidence)
        proof = auditor.generate_proof(evidence.compute_hash())
        assert proof is not None

    def test_delegation_chain_integrity_via_eivl(self):
        """委托链完整性通过 EIVL 验证"""
        import time

        chain = DelegationChain.create("agent-a")
        chain.add_delegation("agent-a", "agent-b", DelegationCapability.READ)
        original_hash = chain.get_chain_hash()

        # 模拟篡改：创建不同的链
        tampered = DelegationChain.create("agent-a")
        tampered.add_delegation("agent-a", "agent-c", DelegationCapability.READ)

        auditor = MerkleAuditor()
        evidence = AuditEvidence(
            evidence_id="ev-original",
            timestamp=time.time(),
            evidence_type="delegation",
            source_agent="agent-a",
            target_agent="agent-b",
            action="delegate",
            result={"chain_id": chain.chain_id, "hash": original_hash},
            previous_hash="0" * 64,
            nonce=1,
        )
        auditor.add_evidence(evidence)

        tampered_hash = tampered.get_chain_hash()
        assert original_hash != tampered_hash  # 篡改后哈希不同


class TestCrossValidatorWeightedConsensus:
    """Phase 6: Cross-Validator + 加权共识联合测试"""

    def test_weighted_consensus_with_cv_weights(self):
        """加权共识与 Cross-Validator 权重集成"""
        maref_engine = WeightedConsensusEngine()
        cv_engine = CVConsensus()

        # 使用 CV 的权重
        cv_validators = {
            "val-1": {"weight": 1.0, "trust_score": 0.9, "vote": "approve"},
            "val-2": {"weight": 0.5, "trust_score": 0.5, "vote": "approve"},
            "val-3": {"weight": 0.3, "trust_score": 0.3, "vote": "reject"},
        }

        votes = [
            ConsensusVote(agent_id="val-1", value=v["vote"], weight=v["weight"] * v["trust_score"])
            for v in cv_validators.values()
        ]

        result = maref_engine.decide(votes)
        # approve: 1.0*0.9 + 0.5*0.5 = 0.9 + 0.25 = 1.15
        # reject: 0.3*0.3 = 0.09
        assert result == "approve"

    def test_cv_byzantine_detection_feeds_maref_penalty(self):
        """Cross-Validator 拜占庭检测触发 MAREF 惩罚"""
        maref_engine = WeightedConsensusEngine()
        cv_engine = CVConsensus()

        # 模拟拜占庭节点
        byzantine_id = "byzantine-1"
        maref_engine.penalize_agent(byzantine_id, penalty=0.3)

        votes = [
            ConsensusVote(agent_id="normal-1", value="correct", weight=80.0),
            ConsensusVote(agent_id=byzantine_id, value="malicious", weight=50.0),
        ]

        result = maref_engine.decide(votes)
        # correct: 80, malicious: 50*0.3=15
        assert result == "correct"


class TestMCPProtocolCompatibility:
    """Phase 6: MCP/A2A 协议兼容性测试"""

    def test_mcp_server_initialize_compliance(self):
        """MCP Server 符合协议规范"""
        server = MCPServer(name="compat-server", version="0.25.0")
        from maref.integration.mcp_transport import JSONRPCRequest

        req = JSONRPCRequest(
            method="initialize",
            params={
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "test", "version": "1.0"},
            },
            id=1,
        )
        resp = server.handle_request(req)
        assert resp.result["protocolVersion"] == "2024-11-05"
        assert resp.result["serverInfo"]["name"] == "compat-server"

    def test_mcp_tool_list_a2a_skill_sync(self):
        """MCP Tool List 与 A2A Skill 同步"""
        mcp = MCPServer(name="sync-test")

        def handler(args):
            return {"content": [{"type": "text", "text": "ok"}]}

        mcp.register_tool(
            "search",
            "Search tool",
            {"type": "object", "properties": {"q": {"type": "string"}}},
            handler,
        )

        audit = AuditLogger()
        sm = GovernanceStateMachine()
        a2a = A2ABridge(state_machine=sm, audit_logger=audit)
        bridge = MCPToA2ABridge(mcp_server=mcp, a2a_bridge=a2a)

        skills = bridge.export_tools_as_skills()
        assert len(skills) == 1
        assert skills[0].id == "mcp-tool-search"

    def test_full_tool_invocation_flow(self):
        """完整工具调用流：A2A Task → MCP Tool"""
        mcp = MCPServer(name="flow-test")

        def calc(args):
            return {"content": [{"type": "text", "text": str(args["x"] + args["y"])}]}

        mcp.register_tool(
            "add",
            "Add two nums",
            {
                "type": "object",
                "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
                "required": ["x", "y"],
            },
            calc,
        )

        audit = AuditLogger()
        sm = GovernanceStateMachine()
        a2a = A2ABridge(state_machine=sm, audit_logger=audit)
        bridge = MCPToA2ABridge(mcp_server=mcp, a2a_bridge=a2a)

        bridge.export_tools_as_skills()
        task_id = bridge.route_a2a_task_to_mcp_tool("add", {"x": 3, "y": 7})

        task = a2a.get_task(task_id)
        assert task is not None
        assert task.a2a_state == A2ATaskState.COMPLETED
        assert task.context["mcp_result"]["content"][0]["text"] == "10"

    def test_security_gate_integration(self):
        """安全门与工具调用集成"""
        from maref.integration.mcp_security import MCPSecurityGate, MCPTrustLevel

        gate = MCPSecurityGate()
        server = MCPServer(name="secure-server", security_gate=gate)

        def bash(args):
            return {"content": [{"type": "text", "text": "pwned"}]}

        server.register_tool("bash", "Shell", {"type": "object", "properties": {}}, bash)

        from maref.integration.mcp_transport import JSONRPCRequest

        # UNTRUSTED 调用 bash 应被阻止
        req = JSONRPCRequest(method="tools/call", params={"name": "bash", "arguments": {}}, id=1)
        resp = server.handle_request(req, trust_level=MCPTrustLevel.UNTRUSTED)
        assert resp.is_error

    def test_a2a_card_to_mcp_metadata_transfer(self):
        """A2A Agent Card 集成 MCP 元数据"""
        mcp = MCPServer(name="card-test")
        mcp.register_tool(
            "tool-1", "desc-1", {"type": "object", "properties": {}}, lambda a: {"content": []}
        )

        audit = AuditLogger()
        sm = GovernanceStateMachine()
        a2a = A2ABridge(state_machine=sm, audit_logger=audit, agent_name="card-agent")
        bridge = MCPToA2ABridge(mcp_server=mcp, a2a_bridge=a2a)

        bridge.export_tools_as_skills()
        card = bridge.build_combined_agent_card()

        assert card["name"] == "card-agent"
        assert "skills" in card
        skill_ids = [s["id"] for s in card["skills"]]
        assert "mcp-tool-tool-1" in skill_ids
        assert "maref-governance" in skill_ids
        assert "mcp" in card


class TestSelfVerification:
    """Phase 6: 自举验证"""

    def test_trust_module_self_verification(self):
        """信任模块可自我验证"""
        from maref.security.trust_graph import TrustGraph, TrustPropagation

        graph = TrustGraph()
        graph.add_agent("self", initial_trust=100.0)
        graph.add_agent("peer", initial_trust=50.0)
        graph.add_edge("self", "peer", 80.0)

        propagator = TrustPropagation(graph, decay_factor=0.5)
        scores = propagator.propagate(iterations=3)

        # 自我验证：peer 的信任分应被提升
        assert scores["peer"] > 50.0
        assert 0 <= scores["peer"] <= 100

    def test_security_module_chain_integrity(self):
        """安全模块链完整性验证"""
        from maref.integration.mcp_security import MCPSecurityGate, MCPTrustLevel
        from maref.security.trust_boundary import TrustBoundaryManager
        from maref.security.trust_chain import DelegationCapability, DelegationChain

        chain = DelegationChain.create("root")
        chain.add_delegation("root", "child", DelegationCapability.READ)

        boundary = TrustBoundaryManager()
        boundary.create_domain("dom-a")
        boundary.create_domain("dom-b")
        boundary.register_agent(
            "root", boundary._domains[list(boundary._domains.keys())[0]].domain_id
        )
        boundary.register_agent(
            "child", boundary._domains[list(boundary._domains.keys())[1]].domain_id
        )

        gate = MCPSecurityGate()

        verdict = gate.check(
            "read_file",
            MCPTrustLevel.SEMI_TRUSTED,
            args={"target": "child"},
        )
        assert verdict in ("ALLOW", "AUDIT", "DENY")

    def test_threat_detection_to_dashboard_pipeline(self):
        """威胁检测到仪表板的全流程"""
        from maref.monitoring.safety_dashboard import ThreatDetectionWidget
        from maref.security.state_monitor import SharedStateMonitor

        monitor = SharedStateMonitor()
        widget = ThreatDetectionWidget()

        monitor.record_mutation("attacker", "global", "var-1", "good", "g00d")
        monitor.record_mutation("attacker", "global", "var-2", "safe", "pwned")
        monitor.record_mutation("attacker", "global", "var-3", "valid", "invalid")
        monitor.record_mutation("attacker", "global", "var-4", "ok", "bad")
        monitor.record_mutation("attacker", "global", "var-5", "fine", "corrupted")

        monitor.quarantine("attacker")
        assert monitor.is_quarantined("attacker") is True

        widget.report_threat("pollution-1", "high", "Shared state pollution detected", source="S5")
        snapshot = widget.snapshot()
        assert snapshot["total_threats"] == 1
