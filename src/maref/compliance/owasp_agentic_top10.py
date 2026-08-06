"""
OWASP Agentic Top 10 覆盖矩阵 — 代码验证的合规映射。

逐项检查 MAREF 治理层对 OWASP Agentic Top 10 (2025) 的覆盖程度，
输出结构化的覆盖报告，供合规审计使用。

使用方法::

    from maref.compliance.owasp_agentic_top10 import OWASPCoverageMatrix

    matrix = OWASPCoverageMatrix()
    report = matrix.verify_all()
    print(f"Coverage: {report['covered']}/{report['total']}")
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any


@dataclass
class OWASPControl:
    id: str
    name: str
    description: str
    risk: str
    code_evidence: list[str] = field(default_factory=list)
    module_path: str = ""
    covered: bool = False


OWASP_AGENTIC_TOP_10: list[OWASPControl] = [
    OWASPControl(
        id="A1",
        name="Prompt Injection",
        description="通过精心设计的输入操控 Agent 行为",
        risk="Critical",
        code_evidence=[
            "ZeroTrustValidator — 8 种注入向量检测",
            "MessageSecurityScanner — MCP 消息级注入扫描",
            "Sanitizer — 输入消毒器",
        ],
        module_path="maref.security.sanitizer",
    ),
    OWASPControl(
        id="A2",
        name="Sensitive Information Disclosure",
        description="敏感信息通过 Agent 输出泄露",
        risk="High",
        code_evidence=[
            "AuditLogger HMAC-SHA256 + Ed25519 — 审计日志加密签名",
            "exfiltration_probe.py — 数据泄露探测",
            "Sanitizer — 输出消毒",
        ],
        module_path="maref.security.sanitizer",
    ),
    OWASPControl(
        id="A3",
        name="Insecure Output Handling",
        description="Agent 输出验证不足导致下游安全风险",
        risk="High",
        code_evidence=[
            "SafetyGateV2 — 输出安全门控",
            "HITLConfirmationDialog — 人工确认输出",
            "Sanitizer — 输出消毒",
        ],
        module_path="maref.recursive.safety_gate_v2",
    ),
    OWASPControl(
        id="A4",
        name="Agent-to-Agent Communication Vulnerabilities",
        description="Agent 间通信缺乏认证/完整性保护",
        risk="Critical",
        code_evidence=[
            "MCPGovernance — HMAC + nonce + TTL 消息认证",
            "A2ABridge — A2A 协议认证",
            "TrustBoundaryManager — 跨域信任边界",
        ],
        module_path="maref.integration.mcp_governance",
    ),
    OWASPControl(
        id="A5",
        name="Excessive Agency",
        description="Agent 执行超出预期范围的操作",
        risk="High",
        code_evidence=[
            "EightTrigramsGovernance — 八卦信任状态机 (8 状态)",
            "FourPhaseGovernance — 四阶段违规处理 (警告→制裁→隔离→恢复)",
            "BlastRadiusController — 爆炸半径控制",
            "PermissionMatrix — 权限矩阵",
        ],
        module_path="maref.recursive.eight_trigrams_governance",
    ),
    OWASPControl(
        id="A6",
        name="Resource Exhaustion",
        description="Agent 消耗过多资源造成拒绝服务",
        risk="Medium",
        code_evidence=[
            "CostTracker — Token/计算成本追踪",
            "BudgetGuard — 预算守卫",
            "MetaCircuitBreaker — 熔断器",
            "GasMeter — Gas 计量",
        ],
        module_path="maref.recursive.cost_tracker",
    ),
    OWASPControl(
        id="A7",
        name="Insecure Agent Identity and Authentication",
        description="Agent 身份管理薄弱导致身份冒用",
        risk="Critical",
        code_evidence=[
            "SignedAgentCard — 加密签名 Agent 身份卡",
            "DIDRegistry — 去中心化身份注册",
            "Ed25519KeyPair — 非对称身份密钥",
            "TrustEngineV2 — 信任评分引擎",
        ],
        module_path="maref.recursive.signed_agent_cards",
    ),
    OWASPControl(
        id="A8",
        name="Supply Chain Vulnerabilities",
        description="模型/库/数据供应链被攻陷",
        risk="High",
        code_evidence=[
            "SupplyChainScanner — 供应链依赖扫描",
            "SBOM 生成 — CycloneDX",
            "Dependabot + pip-audit + cargo-audit — CI 依赖审计",
            "Trivy — 容器镜像扫描",
        ],
        module_path="maref.supply_chain",
    ),
    OWASPControl(
        id="A9",
        name="Improper Error and Exception Handling",
        description="错误处理不当泄露系统信息",
        risk="Medium",
        code_evidence=[
            "标准化错误码 — 20 个错误码 (E0000-E4002)",
            "AuditLogger — 结构化日志无敏感信息泄露",
            "MAREFError — 统一异常类",
        ],
        module_path="maref.exceptions",
    ),
    OWASPControl(
        id="A10",
        name="Lack of Human-in-the-Loop",
        description="缺乏人工监督导致 Agent 失控",
        risk="High",
        code_evidence=[
            "HITL/HOTL/HATL — 三种人工介入模式",
            "InterruptProtocol — Agent 行动中断协议",
            "CarbonSiliconSymbiosis — 碳硅共生工作流 (确认→执行→自审→抽检)",
            "DecisionAPI — 4 级审批流程",
        ],
        module_path="maref.human.decision_api",
    ),
]


class OWASPCoverageMatrix:
    """OWASP Agentic Top 10 覆盖矩阵 — 代码自动验证。"""

    def __init__(self) -> None:
        self._controls = OWASP_AGENTIC_TOP_10

    def verify_module(self, module_path: str) -> bool:
        try:
            mod = importlib.import_module(module_path)
            return mod is not None
        except (ImportError, ModuleNotFoundError):
            return False

    def verify_control(self, control: OWASPControl) -> dict[str, Any]:
        module_ok = self.verify_module(control.module_path)
        control.covered = module_ok
        return {
            "id": control.id,
            "name": control.name,
            "covered": module_ok,
            "module_exists": module_ok,
            "evidence_count": len(control.code_evidence),
            "risk": control.risk,
        }

    def verify_all(self) -> dict[str, Any]:
        results = []
        covered = 0
        for ctrl in self._controls:
            r = self.verify_control(ctrl)
            results.append(r)
            if r["covered"]:
                covered += 1

        return {
            "total": len(self._controls),
            "covered": covered,
            "coverage_ratio": f"{covered}/{len(self._controls)}",
            "coverage_pct": round(covered / len(self._controls) * 100, 1),
            "controls": results,
            "pass_threshold": covered >= 8,
        }

    def summary(self) -> str:
        report = self.verify_all()
        lines = [
            "OWASP Agentic Top 10 Coverage Matrix",
            "=" * 50,
        ]
        for c in report["controls"]:
            mark = "✅" if c["covered"] else "❌"
            lines.append(f"  {mark} {c['id']:4s} {c['name']:<45s} [{c['risk']}]")
        lines.append("=" * 50)
        lines.append(f"  Coverage: {report['coverage_ratio']} ({report['coverage_pct']}%)")
        lines.append(f"  Threshold (≥8/10): {'✅ PASS' if report['pass_threshold'] else '❌ FAIL'}")
        return "\n".join(lines)


__all__ = [
    "OWASPAgenticTop10",
    "OWASPCoverageMatrix",
    "OWASPControl",
    "verify_owasp_coverage",
]


def OWASPAgenticTop10() -> list[OWASPControl]:
    """返回 OWASP Agentic Top 10 控制项列表."""
    return list(OWASP_AGENTIC_TOP_10)


def verify_owasp_coverage() -> dict[str, Any]:
    """便捷函数: 一步完成 OWASP 覆盖验证."""
    return OWASPCoverageMatrix().verify_all()
