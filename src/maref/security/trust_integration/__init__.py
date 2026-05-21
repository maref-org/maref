"""
信任系统集成模块

连接 trust_engine_v2 与 trust_chain，建立统一信任管理系统。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from maref.recursive.trust_engine_v2 import (
    AgentProfileV2,
    GoodhartDetection,
    TrustEngineV2,
    TrustFactor,
    TrustScoreV2,
)
from maref.security.trust_chain import DelegationChain
from maref.security.trust_boundary import TrustBoundaryManager


@dataclass
class ChainRiskFactor:
    """委托链风险评估因子"""
    
    name: str
    chain_id: str
    risk_score: float  # 0.0-1.0, 越高风险越大
    risk_reason: str
    violated_rule: Optional[str] = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "chain_id": self.chain_id,
            "risk_score": round(self.risk_score, 3),
            "risk_reason": self.risk_reason,
            "violated_rule": self.violated_rule,
        }


class ChainRiskAnalyzer:
    """委托链风险分析器"""
    
    def __init__(self, max_chain_depth: int = 5):
        self.max_chain_depth = max_chain_depth
        self.risk_patterns = {
            "depth_exceeded": {
                "pattern": "委托链深度超过最大限制",
                "risk_score": 0.9
            },
            "circular_delegation": {
                "pattern": "循环委托检测",
                "risk_score": 0.95
            },
            "cross_domain_without_auth": {
                "pattern": "跨信任域调用缺少认证",
                "risk_score": 0.8
            },
            "overly_nested": {
                "pattern": "过度嵌套委托",
                "risk_score": 0.0  # 将在_analyze_nested_pattern中计算
            }
        }
    
    def analyze(self, chain: DelegationChain, boundary_manager: Optional[TrustBoundaryManager] = None) -> list[ChainRiskFactor]:
        """分析委托链风险"""
        risks = []
        
        # 检查深度超限
        if chain.depth > chain.max_depth:
            risks.append(ChainRiskFactor(
                name="depth_exceeded",
                chain_id=chain.chain_id,
                risk_score=0.9,
                risk_reason=f"委托链深度{chain.depth}超过最大限制{chain.max_depth}",
                violated_rule="MAX_DEPTH"
            ))
        
        # 检查循环委托
        if self._detect_circular_reference(chain):
            risks.append(ChainRiskFactor(
                name="circular_delegation",
                chain_id=chain.chain_id,
                risk_score=0.95,
                risk_reason="检测到循环委托，可能导致无限递归",
                violated_rule="NO_CIRCULAR_REF"
            ))
        
        # 检查信任边界（如有边界管理器）
        if boundary_manager:
            cross_domain_risks = self._analyze_cross_domain(chain, boundary_manager)
            risks.extend(cross_domain_risks)
        
        # 检查嵌套模式
        nested_risk = self._analyze_nested_pattern(chain)
        if nested_risk:
            risks.append(nested_risk)
        
        return risks
    
    def _detect_circular_reference(self, chain: DelegationChain) -> bool:
        """检测循环委托"""
        agent_ids = []
        for node in chain.nodes:
            agent_ids.append(node.agent_id)
        
        # 如果有重复Agent ID，可能存在循环
        return len(agent_ids) != len(set(agent_ids))
    
    def _analyze_cross_domain(self, chain: DelegationChain, boundary_manager: TrustBoundaryManager) -> list[ChainRiskFactor]:
        """分析跨信任域调用风险"""
        risks = []
        
        for i in range(len(chain.nodes) - 1):
            current_agent = chain.nodes[i].agent_id
            next_agent = chain.nodes[i + 1].agent_id
            
            # 检查是否跨域
            if boundary_manager.check_cross_domain(current_agent, next_agent):
                risks.append(ChainRiskFactor(
                    name="cross_domain_call",
                    chain_id=chain.chain_id,
                    risk_score=0.8,
                    risk_reason=f"跨信任域调用检测: {current_agent} -> {next_agent}",
                    violated_rule="CROSS_DOMAIN_AUTH_REQUIRED"
                ))
        
        return risks
    
    def _analyze_nested_pattern(self, chain: DelegationChain) -> Optional[ChainRiskFactor]:
        """分析嵌套模式风险"""
        if chain.depth > 3:  # 深度超过3级认为是过度嵌套
            score = min(0.7 + (chain.depth - 3) * 0.1, 0.95)
            return ChainRiskFactor(
                name="overly_nested",
                chain_id=chain.chain_id,
                risk_score=score,
                risk_reason=f"过度嵌套委托: 深度{chain.depth}级",
                violated_rule="RECOMMENDED_MAX_NESTING=3"
            )
        return None
    
    def calculate_trust_penalty(self, risks: list[ChainRiskFactor]) -> float:
        """基于风险计算信任惩罚分数"""
        if not risks:
            return 0.0
        
        # 采用最高风险分数作为惩罚基准
        max_risk = max(risk.risk_score for risk in risks)
        
        # 多个风险的叠加效应
        risk_count_factor = min(len(risks) / 5, 1.0)  # 最多5个风险完全惩罚
        
        penalty = max_risk * (0.5 + 0.5 * risk_count_factor)
        return min(penalty, 0.95)  # 最大惩罚95%


class IntegratedTrustEngine:
    """集成的信任引擎 - 连接trust_engine_v2与委托链"""
    
    def __init__(
        self,
        trust_engine: TrustEngineV2,
        chain_analyzer: Optional[ChainRiskAnalyzer] = None
    ):
        self.trust_engine = trust_engine
        self.chain_analyzer = chain_analyzer or ChainRiskAnalyzer()
        self.chain_risk_cache: dict[str, list[ChainRiskFactor]] = {}
        
    def evaluate_with_chain(
        self,
        agent_id: str,
        chain: Optional[DelegationChain] = None
    ) -> tuple[TrustScoreV2, list[ChainRiskFactor]]:
        """
        结合委托链进行信任评估
        
        Args:
            agent_id: 待评估Agent ID
            chain: 相关的委托链，可选
            
        Returns:
            Tuple[信任评分, 风险评估列表]
        """
        # 1. 原始的信任评估
        trust_score = self.trust_engine.assess(agent_id)
        if not trust_score:  # 如果没有评分，创建默认评分
            trust_score = TrustScoreV2(
                agent_id=agent_id,
                overall_trust=50.0,  # 中等信任度
                factors=[],
                timestamp=time.time()
            )
            trust_score.finalize()
        
        # 2. 如果没有委托链，只返回原始评估
        if not chain:
            return trust_score, []
        
        # 3. 分析委托链风险
        risks = self.chain_analyzer.analyze(chain)
        self.chain_risk_cache[agent_id] = risks
        
        # 4. 根据风险调整信任评分
        if risks:
            penalty = self.chain_analyzer.calculate_trust_penalty(risks)
            adjusted_trust = trust_score.overall_trust * (1.0 - penalty)
            
            # 创建调整后的信任评分
            adjusted_score = TrustScoreV2(
                agent_id=agent_id,
                overall_trust=adjusted_trust,
                factors=trust_score.factors,
                goodhart=trust_score.goodhart,
                temporal_decay_factor=trust_score.temporal_decay_factor,
                trust_tier=trust_score.trust_tier,
                confidence_interval=trust_score.confidence_interval,
                timestamp=time.time()
            )
            
            # 添加委托链风险因素到评分中
            chain_factor = TrustFactor(
                name="delegation_chain_risk",
                value=1.0 - penalty,  # 转换成正面因素
                weight=0.15,  # 分配15%的权重
                status="adjusted" if penalty > 0.1 else "normal"
            )
            chain_factor.normalized = chain_factor.value * chain_factor.weight * 100.0
            adjusted_score.factors.append(chain_factor)
            
            # 重新计算总体信任度（加权平均）
            adjusted_score.overall_trust = self._recalculate_trust(adjusted_score.factors)
            adjusted_score.finalize()
            
            return adjusted_score, risks
        
        # 无风险，返回原始评分
        return trust_score, []
    
    def _recalculate_trust(self, factors: list[TrustFactor]) -> float:
        """根据各因素权重重新计算总体信任度"""
        total_weight = sum(factor.weight for factor in factors)
        if total_weight == 0:
            return 50.0  # 默认值
        
        weighted_sum = sum(factor.value * factor.weight for factor in factors)
        return (weighted_sum / total_weight) * 100.0
    
    def get_agent_chain_risk_summary(self, agent_id: str) -> dict[str, Any]:
        """获取Agent的委托链风险摘要"""
        risks = self.chain_risk_cache.get(agent_id, [])
        
        if not risks:
            return {
                "agent_id": agent_id,
                "has_chain_risk": False,
                "risk_count": 0,
                "max_risk_score": 0.0
            }
        
        return {
            "agent_id": agent_id,
            "has_chain_risk": True,
            "risk_count": len(risks),
            "max_risk_score": max(risk.risk_score for risk in risks),
            "risks": [risk.to_dict() for risk in risks]
        }
    
    def generate_combined_report(self, agent_id: str, chain: Optional[DelegationChain] = None) -> dict[str, Any]:
        """生成综合信任报告"""
        trust_score, risks = self.evaluate_with_chain(agent_id, chain)
        
        report = {
            "agent_id": agent_id,
            "timestamp": datetime.now().isoformat(),
            "trust_score": trust_score.to_dict(),
            "chain_impact": {
                "has_chain": chain is not None,
                "chain_id": chain.chain_id if chain else None,
                "chain_depth": chain.depth if chain else 0,
                "risk_count": len(risks),
                "trust_penalty": self.chain_analyzer.calculate_trust_penalty(risks) if risks else 0.0
            }
        }
        
        # 如果有委托链，添加链信息
        if chain:
            report["delegation_chain"] = {
                "chain_id": chain.chain_id,
                "root_agent": chain.root_agent_id,
                "depth": chain.depth,
                "max_depth": chain.max_depth,
                "node_count": len(chain.nodes),
                "is_valid": chain.validate()
            }
        
        return report


class TrustIntegrationAPI:
    """统一信任API接口"""
    
    def __init__(self, integrated_engine: IntegratedTrustEngine):
        self.engine = integrated_engine
    
    def get_trust_score(self, agent_id: str, chain_data: Optional[dict] = None) -> dict[str, Any]:
        """获取信任评分API"""
        delegation_chain = None
        
        # 如果有链数据，解析成委托链对象
        if chain_data:
            try:
                from maref.security.trust_chain import ChainNode
                nodes = []
                for node_data in chain_data.get("nodes", []):
                    node = ChainNode(
                        agent_id=node_data["agent_id"],
                        parent_id=node_data.get("parent_id"),
                        timestamp=node_data.get("timestamp", time.time()),
                        action=node_data.get("action", "delegate"),
                        capability=node_data.get("capability", "EXECUTE"),
                        metadata=node_data.get("metadata", {})
                    )
                    nodes.append(node)
                
                delegation_chain = DelegationChain(
                    chain_id=chain_data.get("chain_id"),
                    root_agent_id=chain_data.get("root_agent_id"),
                    max_depth=chain_data.get("max_depth", 5)
                )
                delegation_chain.nodes = nodes
                delegation_chain.depth = len(nodes)
                
            except Exception as e:
                # 解析失败，仍然继续但不考虑链
                print(f"Warning: Failed to parse chain data: {e}")
        
        # 执行评估
        trust_score, risks = self.engine.evaluate_with_chain(agent_id, delegation_chain)
        
        return {
            "success": True,
            "agent_id": agent_id,
            "timestamp": datetime.now().isoformat(),
            "trust_score": trust_score.overall_trust,
            "trust_tier": trust_score.trust_tier,
            "confidence_interval": trust_score.confidence_interval,
            "chain_risk_count": len(risks),
            "chain_risk_summary": self.engine.get_agent_chain_risk_summary(agent_id),
            "details": {
                "factors": [f.to_dict() for f in trust_score.factors],
                "risks": [r.to_dict() for r in risks] if risks else None
            }
        }
    
    def get_trust_report(self, agent_id: str, include_chain: bool = True) -> dict[str, Any]:
        """获取详细信任报告"""
        if include_chain:
            # 这里应该查询Agent相关的委托链
            # 由于这是一个简化实现，我们返回基本报告
            pass
        
        return self.engine.generate_combined_report(agent_id)


def create_integrated_trust_system() -> tuple[IntegratedTrustEngine, TrustIntegrationAPI]:
    """创建集成的信任系统"""
    # 创建信任引擎V2（需要审计记录）
    from maref.recursive.unified_audit import UnifiedAuditStore
    audit_store = UnifiedAuditStore()
    
    # 创建信任引擎
    trust_engine = TrustEngineV2(audit_store=audit_store)
    
    # 创建集成引擎
    integrated_engine = IntegratedTrustEngine(trust_engine)
    
    # 创建API
    api = TrustIntegrationAPI(integrated_engine)
    
    return integrated_engine, api


# 导出主要类
__all__ = [
    "ChainRiskAnalyzer",
    "IntegratedTrustEngine", 
    "TrustIntegrationAPI",
    "ChainRiskFactor",
    "create_integrated_trust_system"
]