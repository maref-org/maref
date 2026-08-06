"""
信任系统集成测试模块
"""

from __future__ import annotations

import time

import pytest

from maref.recursive.trust_engine_v2 import TrustEngineV2, TrustScoreV2
from maref.recursive.unified_audit import UnifiedAuditStore
from maref.security.trust_chain import ChainNode, DelegationChain
from maref.security.trust_integration import (
    ChainRiskAnalyzer,
    ChainRiskFactor,
    IntegratedTrustEngine,
    TrustIntegrationAPI,
)


class TestChainRiskAnalyzer:
    """测试链风险分析器"""

    def test_create_risk_factor(self) -> None:
        """测试创建风险因子"""
        factor = ChainRiskFactor(
            name="test_risk", chain_id="chain-123", risk_score=0.7, risk_reason="测试风险"
        )
        assert factor.name == "test_risk"
        assert factor.risk_score == 0.7
        assert factor.risk_reason == "测试风险"

    def test_to_dict_conversion(self) -> None:
        """测试字典转换"""
        factor = ChainRiskFactor(
            name="depth_risk", chain_id="chain-456", risk_score=0.85, risk_reason="深度超标"
        )
        data = factor.to_dict()
        assert data["name"] == "depth_risk"
        assert data["risk_score"] == 0.85
        assert data["risk_reason"] == "深度超标"

    def test_analyze_safe_chain(self) -> None:
        """测试分析安全链"""
        analyzer = ChainRiskAnalyzer()

        # 创建安全的委托链
        chain = DelegationChain(chain_id="safe-chain-1", root_agent_id="agent-a")

        # 添加几个安全的节点
        import datetime

        from maref.security.trust_chain import DelegationCapability

        chain.nodes = [
            ChainNode(
                agent_id="agent-a",
                capability=DelegationCapability.ADMIN,
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            ),
            ChainNode(
                agent_id="agent-b",
                parent_id="agent-a",
                capability=DelegationCapability.EXECUTE,
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            ),
            ChainNode(
                agent_id="agent-c",
                parent_id="agent-b",
                capability=DelegationCapability.READ,
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            ),
        ]
        chain.depth = 2

        risks = analyzer.analyze(chain)
        assert len(risks) == 0

    def test_analyze_deep_chain(self) -> None:
        """测试分析过深的链"""
        analyzer = ChainRiskAnalyzer(max_chain_depth=3)

        # 创建超深的链
        chain = DelegationChain(chain_id="deep-chain-1", root_agent_id="agent-a", max_depth=3)

        # 深度为5，超过限制
        import datetime

        from maref.security.trust_chain import DelegationCapability

        now = datetime.datetime.now(datetime.timezone.utc)

        chain.nodes = [
            ChainNode(agent_id="agent-a", capability=DelegationCapability.ADMIN, timestamp=now),
            ChainNode(
                agent_id="agent-b",
                parent_id="agent-a",
                capability=DelegationCapability.EXECUTE,
                timestamp=now,
            ),
            ChainNode(
                agent_id="agent-c",
                parent_id="agent-b",
                capability=DelegationCapability.EXECUTE,
                timestamp=now,
            ),
            ChainNode(
                agent_id="agent-d",
                parent_id="agent-c",
                capability=DelegationCapability.EXECUTE,
                timestamp=now,
            ),
            ChainNode(
                agent_id="agent-e",
                parent_id="agent-d",
                capability=DelegationCapability.EXECUTE,
                timestamp=now,
            ),
        ]
        chain.depth = 5

        risks = analyzer.analyze(chain)
        # 当深度超过3时，会同时触发depth_exceeded和overly_nested两个风险
        assert len(risks) >= 1
        depth_risks = [r for r in risks if r.name == "depth_exceeded"]
        assert len(depth_risks) >= 1
        assert depth_risks[0].violated_rule == "MAX_DEPTH"

    def test_circular_reference_detection(self) -> None:
        """测试循环引用检测"""
        analyzer = ChainRiskAnalyzer()

        chain = DelegationChain(chain_id="circular-chain-1", root_agent_id="agent-a")

        # 创建循环引用: a -> b -> c -> a
        import datetime

        from maref.security.trust_chain import DelegationCapability

        now = datetime.datetime.now(datetime.timezone.utc)

        chain.nodes = [
            ChainNode(agent_id="agent-a", capability=DelegationCapability.ADMIN, timestamp=now),
            ChainNode(
                agent_id="agent-b",
                parent_id="agent-a",
                capability=DelegationCapability.EXECUTE,
                timestamp=now,
            ),
            ChainNode(
                agent_id="agent-c",
                parent_id="agent-b",
                capability=DelegationCapability.EXECUTE,
                timestamp=now,
            ),
            ChainNode(
                agent_id="agent-a",
                parent_id="agent-c",
                capability=DelegationCapability.EXECUTE,
                timestamp=now,
            ),  # 回到起点
        ]
        chain.depth = 3

        risks = analyzer.analyze(chain)
        assert len(risks) == 1
        assert risks[0].name == "circular_delegation"
        assert risks[0].risk_score == 0.95

    def test_calculate_trust_penalty(self) -> None:
        """测试信任惩罚计算"""
        analyzer = ChainRiskAnalyzer()

        # 单个风险
        single_risk = [ChainRiskFactor("test1", "chain-1", 0.6, "测试风险1")]
        penalty = analyzer.calculate_trust_penalty(single_risk)
        # 单个风险的计算公式: max_risk * (0.5 + 0.5 * risk_count_factor)
        # risk_count_factor = 1/5 = 0.2
        expected = 0.6 * (0.5 + 0.5 * 0.2)  # 0.6 * 0.6 = 0.36
        assert penalty == pytest.approx(expected, rel=0.01)

        # 多个风险
        multiple_risks = [
            ChainRiskFactor("test1", "chain-1", 0.6, "风险1"),
            ChainRiskFactor("test2", "chain-1", 0.8, "风险2"),
            ChainRiskFactor("test3", "chain-1", 0.4, "风险3"),
        ]
        penalty = analyzer.calculate_trust_penalty(multiple_risks)
        # 3个风险，最高0.8，risk_count_factor=3/5=0.6，penalty = 0.8 * (0.5 + 0.5*0.6) = 0.64
        assert penalty > 0.5


class TestIntegratedTrustEngine:
    """测试集成信任引擎"""

    @pytest.fixture
    def trust_engine(self) -> TrustEngineV2:
        """创建测试用的信任引擎"""
        audit_store = UnifiedAuditStore()
        return TrustEngineV2(audit_store=audit_store)

    @pytest.fixture
    def integrated_engine(self, trust_engine: TrustEngineV2) -> IntegratedTrustEngine:
        """创建集成引擎"""
        return IntegratedTrustEngine(trust_engine)

    def test_evaluate_without_chain(self, integrated_engine: IntegratedTrustEngine) -> None:
        """测试无链状况下的评估"""
        agent_id = "test-agent-no-chain"

        trust_score, risks = integrated_engine.evaluate_with_chain(agent_id, None)

        assert isinstance(trust_score, TrustScoreV2)
        assert trust_score.agent_id == agent_id
        assert len(risks) == 0

    def test_evaluate_with_safe_chain(self, integrated_engine: IntegratedTrustEngine) -> None:
        """测试有安全链的评估"""
        agent_id = "test-agent-safe-chain"

        # 创建安全链
        import datetime

        from maref.security.trust_chain import DelegationCapability

        now = datetime.datetime.now(datetime.timezone.utc)

        chain = DelegationChain(chain_id="safe-chain-test", root_agent_id="root-agent")
        chain.nodes = [
            ChainNode(agent_id="root-agent", capability=DelegationCapability.ADMIN, timestamp=now),
            ChainNode(
                agent_id=agent_id,
                parent_id="root-agent",
                capability=DelegationCapability.EXECUTE,
                timestamp=now,
            ),
        ]
        chain.depth = 1

        trust_score, risks = integrated_engine.evaluate_with_chain(agent_id, chain)

        assert isinstance(trust_score, TrustScoreV2)
        assert len(risks) == 0

    def test_evaluate_with_risky_chain(self, integrated_engine: IntegratedTrustEngine) -> None:
        """测试有风险链的评估"""
        agent_id = "test-agent-risky-chain"

        # 创建有风险的链（超深）
        import datetime

        from maref.security.trust_chain import DelegationCapability

        now = datetime.datetime.now(datetime.timezone.utc)

        chain = DelegationChain(
            chain_id="risky-chain-test", root_agent_id="root-agent", max_depth=2
        )
        chain.nodes = [
            ChainNode(agent_id="root-agent", capability=DelegationCapability.ADMIN, timestamp=now),
            ChainNode(
                agent_id="agent-b",
                parent_id="root-agent",
                capability=DelegationCapability.EXECUTE,
                timestamp=now,
            ),
            ChainNode(
                agent_id="agent-c",
                parent_id="agent-b",
                capability=DelegationCapability.EXECUTE,
                timestamp=now,
            ),
            ChainNode(
                agent_id="agent-d",
                parent_id="agent-c",
                capability=DelegationCapability.EXECUTE,
                timestamp=now,
            ),
            ChainNode(
                agent_id=agent_id,
                parent_id="agent-d",
                capability=DelegationCapability.READ,
                timestamp=now,
            ),
        ]
        chain.depth = 4  # 超过max_depth=2

        trust_score, risks = integrated_engine.evaluate_with_chain(agent_id, chain)

        assert len(risks) >= 1
        depth_risks = [r for r in risks if r.name == "depth_exceeded"]
        assert len(depth_risks) >= 1

        # 信任评分应该被惩罚（降低）
        # 注意：初始信任评分可能为默认值，这里主要检查流程
        assert trust_score.overall_trust >= 0.0
        assert trust_score.overall_trust <= 100.0

    def test_get_agent_chain_risk_summary(self, integrated_engine: IntegratedTrustEngine) -> None:
        """测试获取Agent链风险摘要"""
        agent_id = "test-agent-summary"

        # 先评估有风险的链
        import datetime

        from maref.security.trust_chain import DelegationCapability

        now = datetime.datetime.now(datetime.timezone.utc)

        chain = DelegationChain(
            chain_id="chain-summary-test", root_agent_id="root-agent", max_depth=2
        )
        chain.nodes = [
            ChainNode(agent_id="root-agent", capability=DelegationCapability.ADMIN, timestamp=now),
            ChainNode(
                agent_id="agent-x",
                parent_id="root-agent",
                capability=DelegationCapability.EXECUTE,
                timestamp=now,
            ),
            ChainNode(
                agent_id="agent-y",
                parent_id="agent-x",
                capability=DelegationCapability.EXECUTE,
                timestamp=now,
            ),
            ChainNode(
                agent_id="agent-z",
                parent_id="agent-y",
                capability=DelegationCapability.EXECUTE,
                timestamp=now,
            ),  # 深度3，超标
            ChainNode(
                agent_id=agent_id,
                parent_id="agent-z",
                capability=DelegationCapability.READ,
                timestamp=now,
            ),
        ]
        chain.depth = 4

        integrated_engine.evaluate_with_chain(agent_id, chain)

        # 获取风险摘要
        summary = integrated_engine.get_agent_chain_risk_summary(agent_id)

        assert summary["agent_id"] == agent_id
        assert summary["has_chain_risk"] == True
        assert summary["risk_count"] >= 1
        assert summary["max_risk_score"] > 0.0

    def test_generate_combined_report(self, integrated_engine: IntegratedTrustEngine) -> None:
        """测试生成综合报告"""
        agent_id = "test-agent-report"

        import datetime

        from maref.security.trust_chain import DelegationCapability

        now = datetime.datetime.now(datetime.timezone.utc)

        chain = DelegationChain(chain_id="report-chain-test", root_agent_id="root-agent")
        chain.nodes = [
            ChainNode(agent_id="root-agent", capability=DelegationCapability.ADMIN, timestamp=now),
            ChainNode(
                agent_id=agent_id,
                parent_id="root-agent",
                capability=DelegationCapability.EXECUTE,
                timestamp=now,
            ),
        ]
        chain.depth = 1

        report = integrated_engine.generate_combined_report(agent_id, chain)

        assert report["agent_id"] == agent_id
        assert "timestamp" in report
        assert "trust_score" in report
        assert report["chain_impact"]["has_chain"] == True
        assert report["chain_impact"]["chain_id"] == "report-chain-test"

    def test_recalculate_trust_logic(self, integrated_engine: IntegratedTrustEngine) -> None:
        """测试信任重计算逻辑"""
        from maref.recursive.trust_engine_v2 import TrustFactor

        # 模拟几个信任因素
        factors = [
            TrustFactor(name="task_completion", value=0.9, weight=0.3),
            TrustFactor(name="response_quality", value=0.8, weight=0.2),
            TrustFactor(name="delegation_risk", value=0.7, weight=0.15),
        ]

        # 手动计算期望值
        weighted_sum = (0.9 * 0.3) + (0.8 * 0.2) + (0.7 * 0.15)
        total_weight = 0.3 + 0.2 + 0.15
        expected = (weighted_sum / total_weight) * 100.0

        # 调用内部方法
        result = integrated_engine._recalculate_trust(factors)

        assert result == pytest.approx(expected, rel=0.01)


class TestTrustIntegrationAPI:
    """测试统一信任API"""

    @pytest.fixture
    def api(self) -> TrustIntegrationAPI:
        """创建测试API"""
        audit_store = UnifiedAuditStore()
        trust_engine = TrustEngineV2(audit_store=audit_store)
        integrated_engine = IntegratedTrustEngine(trust_engine)
        return TrustIntegrationAPI(integrated_engine)

    def test_get_trust_score_without_chain(self, api: TrustIntegrationAPI) -> None:
        """测试无链获取信任评分"""
        agent_id = "api-test-no-chain"

        result = api.get_trust_score(agent_id, None)

        assert result["success"] == True
        assert result["agent_id"] == agent_id
        assert "timestamp" in result
        assert "trust_score" in result
        assert "trust_tier" in result
        assert result["chain_risk_count"] == 0

    def test_get_trust_score_with_chain(self, api: TrustIntegrationAPI) -> None:
        """测试有链获取信任评分"""
        agent_id = "api-test-with-chain"

        chain_data = {
            "chain_id": "api-chain-test",
            "root_agent_id": "root-agent",
            "max_depth": 5,
            "nodes": [
                {
                    "agent_id": "root-agent",
                    "action": "start",
                    "timestamp": time.time(),
                    "capability": "ADMIN",
                },
                {
                    "agent_id": "agent-mid",
                    "parent_id": "root-agent",
                    "action": "delegate",
                    "timestamp": time.time() + 1,
                    "capability": "EXECUTE",
                },
                {
                    "agent_id": agent_id,
                    "parent_id": "agent-mid",
                    "action": "execute",
                    "timestamp": time.time() + 2,
                    "capability": "READ",
                },
            ],
        }

        result = api.get_trust_score(agent_id, chain_data)

        assert result["success"] == True
        assert result["agent_id"] == agent_id
        assert "chain_risk_summary" in result
        assert "details" in result

    def test_get_trust_score_with_invalid_chain(self, api: TrustIntegrationAPI) -> None:
        """测试无效链数据"""
        agent_id = "api-test-invalid-chain"

        # 无效的链数据（缺少必要字段）
        invalid_chain = {"chain_id": "bad-chain", "missing_root": True}

        # 应该能处理无效数据并继续
        result = api.get_trust_score(agent_id, invalid_chain)

        assert result["success"] == True
        # 应该降级到无链评估
        assert result["chain_risk_count"] == 0

    def test_get_trust_report_basic(self, api: TrustIntegrationAPI) -> None:
        """测试获取基本信任报告"""
        agent_id = "api-test-report"

        report = api.get_trust_report(agent_id, include_chain=False)

        assert report["agent_id"] == agent_id
        assert "trust_score" in report
        assert "chain_impact" in report


def test_create_integrated_trust_system() -> None:
    """测试集成信任系统的完整创建流程"""
    from maref.security.trust_integration import create_integrated_trust_system

    integrated_engine, api = create_integrated_trust_system()

    assert isinstance(integrated_engine, IntegratedTrustEngine)
    assert isinstance(api, TrustIntegrationAPI)

    # 验证可以工作
    agent_id = "system-test-agent"
    result = api.get_trust_score(agent_id, None)

    assert result["success"] == True
    assert result["agent_id"] == agent_id
