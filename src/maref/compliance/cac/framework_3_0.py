"""《人工智能安全治理框架3.0》— MAREF 技术映射与覆盖自证。

依据：全国网络安全标准化技术委员会（TC260）《人工智能安全治理框架3.0》
（2026-09，全文 136 页）。本模块聚焦其附件 2《智能体风险管理框架》的
9 类风险 × 7 组防范措施，逐条映射到 MAREF 真实模块，并提供 fail-closed
的模块路径校验，防止映射"吹牛"（引用不存在的模块/符号）。

设计对齐同目录 blockchain_traceability.py 的映射范式，但更严格：
- module_path 使用 Python 导入路径（非文件路径），verify 走 find_spec + AST；
- 校验不触发真实 import，避免副作用与可选依赖缺失导致的误报。

术语纪律：框架原文无"物理熔断"一词，原文用"暂停、终止或转人工处理"
（运行时动态管理）、"紧急停机"（具身智能）、"应急处置与熔断机制"（违法信息）。
本模块对外一律使用框架原生术语。
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Any

# 仓库 src 根目录（本文件位于 src/maref/compliance/cac/ 下）
_SRC_ROOT = Path(__file__).resolve().parents[3]

# ---------------------------------------------------------------------------
# 框架附件 2「7 组防范措施」常量
# ---------------------------------------------------------------------------

CATEGORY_RISK_PREVENTION = "1.风险预防前置"
CATEGORY_IDENTITY_PERMISSION = "2.身份与权限管理"
CATEGORY_HUMAN_APPROVAL = "3.加强人工审批"
CATEGORY_SUPPLY_CHAIN = "4.供应链与工具管理"
CATEGORY_RUNTIME_CONTROL = "5.运行时动态管理"
CATEGORY_MONITORING_AUDIT = "6.持续监测与审计"
CATEGORY_DECOMMISSION = "7.停用安全管理"

CATEGORIES: tuple[str, ...] = (
    CATEGORY_RISK_PREVENTION,
    CATEGORY_IDENTITY_PERMISSION,
    CATEGORY_HUMAN_APPROVAL,
    CATEGORY_SUPPLY_CHAIN,
    CATEGORY_RUNTIME_CONTROL,
    CATEGORY_MONITORING_AUDIT,
    CATEGORY_DECOMMISSION,
)

STATUS_COVERED = "covered"
STATUS_PARTIAL = "partial"
STATUS_MISSING = "missing"

STATUS_LABELS: dict[str, str] = {
    STATUS_COVERED: "已覆盖",
    STATUS_PARTIAL: "部分覆盖",
    STATUS_MISSING: "缺失",
}


@dataclass(frozen=True)
class FrameworkMapping:
    """单条「框架要求 → MAREF 实现」映射。"""

    category: str
    clause: str
    requirement: str
    maref_implementation: str
    module_path: str
    symbol: str
    status: str
    openclaw_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        effective = effective_status(self)
        data["effective_status"] = effective
        data["effective_status_label"] = STATUS_LABELS.get(effective, effective)
        data["status_label"] = STATUS_LABELS.get(self.status, self.status)
        return data


# ---------------------------------------------------------------------------
# 映射矩阵（7 类防范措施）
# ---------------------------------------------------------------------------

MAPS: tuple[FrameworkMapping, ...] = (
    # ---- 1. 风险预防前置（附件2 二.1）----
    FrameworkMapping(
        category=CATEGORY_RISK_PREVENTION,
        clause="附件2 二.1(1)",
        requirement="安全需求确认：明确应用场景、可访问资源和禁止性行为，制定安全风险台账",
        maref_implementation="任务前置检查 + 风险授权检查（fail-closed）",
        module_path="maref.governance.task_preflight",
        symbol="TaskPreflight",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_RISK_PREVENTION,
        clause="附件2 二.1(2)",
        requirement="安全风险分级：按客体类别、影响程度、范围和可恢复性划分风险级别",
        maref_implementation="动作风险分类器 + 风险阈值判定",
        module_path="maref.governance.risk_classifier",
        symbol="RiskAssessment",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_RISK_PREVENTION,
        clause="附件2 二.1(2)",
        requirement="风险分级方法论（跨域对照）",
        maref_implementation="EU AI Act 风险管理生命周期（识别/评估/缓解/应用）",
        module_path="maref.compliance.eu_ai_act_v2.risk_management",
        symbol="RiskManagementSystem",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_RISK_PREVENTION,
        clause="附件2 二.1(2)",
        requirement="风险五级显式化（低/一般/较大/重大/特别重大）+ 四维度（客体类别/影响程度/范围/可恢复性）",
        maref_implementation="框架3.0 分级适配层（现有四挡权威分级 → 五级映射 + 四维度补齐 + 处置流程绑定）",
        module_path="maref.compliance.cac.risk_grading",
        symbol="grade_action",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_RISK_PREVENTION,
        clause="附件2 二.1(3)",
        requirement="安全控制策略：制定动态安全控制策略与应急响应流程",
        maref_implementation="辖区监管策略映射（动作 × 辖区 → 处置策略）",
        module_path="maref.compliance.regulatory_policy_mapper",
        symbol="RegulatoryPolicyMapper",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_RISK_PREVENTION,
        clause="附件2 二.1(3)",
        requirement="部署环境安全基线（安全能力摸底）",
        maref_implementation="PERCV 多维安全基线扫描",
        module_path="maref.compliance.security_baseline",
        symbol="run_scan",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_RISK_PREVENTION,
        clause="附件2 二.1(4)",
        requirement="安全机制确认：保留版本发布与回退记录",
        maref_implementation="治理状态机快照/恢复 + 迁移回滚点",
        module_path="maref.governance.state_machine",
        symbol="GovernanceStateMachine",
        status=STATUS_COVERED,
    ),
    # ---- 2. 身份与权限管理（附件2 二.2）----
    FrameworkMapping(
        category=CATEGORY_IDENTITY_PERMISSION,
        clause="附件2 二.2(1)",
        requirement="唯一身份标识：禁止智能体应用实例间共享身份标识",
        maref_implementation="Agent DID 注册表（register/resolve/revoke/deactivate）",
        module_path="maref.identity.did_registry",
        symbol="DIDRegistry",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_IDENTITY_PERMISSION,
        clause="附件2 二.2(1)",
        requirement="身份鉴别：鉴别用户、智能体、工具及外部服务身份",
        maref_implementation="Agent 身份统一门面（签发/验证/撤销）+ 握手挑战",
        module_path="maref.identity.agent_identity_service",
        symbol="AgentIdentityService",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_IDENTITY_PERMISSION,
        clause="附件2 二.2(1)",
        requirement="身份鉴别握手（访问主体身份可信）",
        maref_implementation="ATP 适配器身份验证与挑战生成",
        module_path="maref.security.agent_identity",
        symbol="ATPAdapter",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_IDENTITY_PERMISSION,
        clause="附件2 二.2(1)",
        requirement="国密身份证书与跨系统身份互认（鼓励采用国密算法）",
        maref_implementation="SM2 身份证书（ACPs CAI）签发/验签 + SM3 公钥指纹互认 + DID 绑定；国家 CA 对接为预留接口（未联调）",
        module_path="maref.identity.sm2_certificate",
        symbol="issue_certificate",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_IDENTITY_PERMISSION,
        clause="附件2 二.2(2)",
        requirement="最小权限：仅为智能体授予执行当前任务所必需的最小权限",
        maref_implementation="信任边界管理器（check / check_no_raise，禁止越权提权）",
        module_path="maref.governance.trust_boundary",
        symbol="TrustBoundaryManager",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_IDENTITY_PERMISSION,
        clause="附件2 二.2(2)",
        requirement="零信任：Agent 间消息边界与上下文隔离",
        maref_implementation="零信任校验器 + 上下文隔离 + Agent 边界",
        module_path="maref.recursive.zero_trust",
        symbol="ZeroTrustValidator",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_IDENTITY_PERMISSION,
        clause="附件2 二.2(3)",
        requirement="凭证动态管理：任务终止或停用后立即撤销对应凭证",
        maref_implementation="凭证管理器（轮换/撤销/过期检查）+ 密钥轮换策略",
        module_path="maref.identity.credential_manager",
        symbol="CredentialManager",
        status=STATUS_COVERED,
    ),
    # ---- 3. 加强人工审批（附件2 二.3）----
    FrameworkMapping(
        category=CATEGORY_HUMAN_APPROVAL,
        clause="附件2 二.3(2)",
        requirement="在关键决策节点设置强制人工审批",
        maref_implementation="人工决策 API（请求决策/提交响应）+ 高风险操作审批引擎",
        module_path="maref.human.decision_api",
        symbol="HumanDecisionAPI",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_HUMAN_APPROVAL,
        clause="附件2 二.3(1)(2)",
        requirement="高风险操作转交用户接管、中低风险需授权",
        maref_implementation="审批引擎（预测 + 首次使用强制审批 + 超策略风险拦截）",
        module_path="maref.opc_integration.approval.engine",
        symbol="ApprovalEngine",
        status=STATUS_COVERED,
        openclaw_only=True,
    ),
    FrameworkMapping(
        category=CATEGORY_HUMAN_APPROVAL,
        clause="附件2 二.3(2)",
        requirement="出网/敏感动作的人工确认节点",
        maref_implementation="出网消息门禁（HITLRequiredError）+ 底线预检 HITL 确认",
        module_path="maref.governance.governance_baseline_gate",
        symbol="GovernanceBaselineGate",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_HUMAN_APPROVAL,
        clause="附件2 二.3(4)",
        requirement="审批系统异常/用户无响应时默认拒绝操作执行（fail-closed）",
        maref_implementation="安全门 v2（block/is_blocked，审批异常默认拒绝）",
        module_path="maref.recursive.safety_gate_v2",
        symbol="SafetyGateV2",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_HUMAN_APPROVAL,
        clause="附件2 二.3(3)",
        requirement="采用防篡改、可校验方式保存人工审批日志（审批人身份绑定）",
        maref_implementation="审批台账（链式哈希 + SM2/Ed25519 签名 + Merkle 离线证明 + 审批人身份绑定 + 高风险 fail-closed 阻断）",
        module_path="maref.human.approval_ledger",
        symbol="ApprovalLedger",
        status=STATUS_COVERED,
    ),
    # ---- 4. 供应链与工具管理（附件2 二.4）----
    FrameworkMapping(
        category=CATEGORY_SUPPLY_CHAIN,
        clause="附件2 二.4",
        requirement="工具/依赖元数据与版本清单",
        maref_implementation="SBOM 生成器（项目依赖清单）",
        module_path="maref.supply_chain.sbom_generator",
        symbol="SBOMGenerator",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_SUPPLY_CHAIN,
        clause="附件2 二.4(1)",
        requirement="工具调用前校验来源、版本、元数据",
        maref_implementation="供应链信任校验器",
        module_path="maref.supply_chain.trust_verifier",
        symbol="SupplyChainVerifier",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_SUPPLY_CHAIN,
        clause="附件2 二.4(1)",
        requirement="技能/工具清单登记与校验",
        maref_implementation="技能注册表 + 清单校验",
        module_path="maref.marketplace.registry",
        symbol="SkillRegistry",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_SUPPLY_CHAIN,
        clause="附件2 二.4(1)",
        requirement="不调用公开已知恶意工具、阻断越权调用",
        maref_implementation="MCP 安全门（安全裁决 + 越权拦截）",
        module_path="maref.integration.mcp_security",
        symbol="MCPSecurityGate",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_SUPPLY_CHAIN,
        clause="附件2 二.4(3)",
        requirement="工具异常检测",
        maref_implementation="工具沙箱参数/环境校验 + 行为异常监测",
        module_path="maref.security.tool_sandbox",
        symbol="ToolSandbox",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_SUPPLY_CHAIN,
        clause="附件2 二.4(4)",
        requirement="漏洞追踪与供应链风险持续处置",
        maref_implementation="漏洞扫描器（SBOM 扫描 + 漏洞库）",
        module_path="maref.supply_chain.vulnerability_scanner",
        symbol="VulnerabilityScanner",
        status=STATUS_COVERED,
    ),
    # ---- 5. 运行时动态管理（附件2 二.5）----
    FrameworkMapping(
        category=CATEGORY_RUNTIME_CONTROL,
        clause="附件2 二.5(1)",
        requirement="输入管理控制：校验来源可信度、多层检测拦截点",
        maref_implementation="输入净化器 + 隐蔽字符/隐写检测",
        module_path="maref.security.sanitizer",
        symbol="Sanitizer",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_RUNTIME_CONTROL,
        clause="附件2 二.5(5)",
        requirement="自主执行控制：异常循环/目标偏移时暂停、终止或转人工",
        maref_implementation="中断协议（签发中断/向 Agent 传播）+ 质量门强制终止/隔离/限流",
        module_path="maref.human.interrupt_protocol",
        symbol="InterruptProtocol",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_RUNTIME_CONTROL,
        clause="附件2 二.5(5)",
        requirement="治理级紧急停止",
        maref_implementation="治理状态机 force_halt / force_stabilize",
        module_path="maref.governance.state_machine",
        symbol="GovernanceStateMachine",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_RUNTIME_CONTROL,
        clause="附件2 二.5(5)",
        requirement="运行时熔断（连续失败自动暂停）",
        maref_implementation="熔断器 + 预测性熔断（提前制动）",
        module_path="maref.governance.circuit_breaker",
        symbol="CircuitBreaker",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_RUNTIME_CONTROL,
        clause="附件2 二.5(6)",
        requirement="运行环境隔离",
        maref_implementation="WASM 沙箱执行器（资源限制 + EIVL 验证）+ 进程沙箱",
        module_path="maref.eivl.wasm_sandbox",
        symbol="WasmSandboxExecutor",
        status=STATUS_COVERED,
    ),
    # ---- 6. 持续监测与审计（附件2 二.6）----
    FrameworkMapping(
        category=CATEGORY_MONITORING_AUDIT,
        clause="附件2 二.6",
        requirement="全链路安全监测（行为可感知、可追溯、可审计）",
        maref_implementation="安全大屏 + 异常阻断编排",
        module_path="maref.monitoring.safety_dashboard",
        symbol="SafetyDashboard",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_MONITORING_AUDIT,
        clause="附件2 二.6(1)",
        requirement="异常阻断（实时监控 + 介入阻断）",
        maref_implementation="安全编排器（剧本化自动响应）",
        module_path="maref.monitoring.security_orchestrator",
        symbol="SecurityOrchestrator",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_MONITORING_AUDIT,
        clause="附件2 二.6",
        requirement="行为记录可追溯、可审计（链式防篡改）",
        maref_implementation="审计日志（chain_hash + Ed25519 签名）+ Merkle 完整性证明",
        module_path="maref.eivl.merkle_auditor",
        symbol="MerkleAuditor",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_MONITORING_AUDIT,
        clause="附件2 二.6",
        requirement="跨组织审计可交叉验证",
        maref_implementation="联邦审计日志 + 联邦 Merkle 聚合",
        module_path="maref.eivl.federated_audit_log",
        symbol="FederatedAuditLog",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_MONITORING_AUDIT,
        clause="附件2 二.6(5)",
        requirement="沙箱环境验证（安全属性形式证明）",
        maref_implementation="安全属性证明器 + TLA+ 不变量校验",
        module_path="maref.security.security_proofs",
        symbol="SecurityPropertyProver",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_MONITORING_AUDIT,
        clause="附件2 二.6(6)",
        requirement="常态化红队安全测试",
        maref_implementation="红蓝对抗引擎",
        module_path="maref.redblue.red_blue_engine",
        symbol="RedBlueEngine",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_MONITORING_AUDIT,
        clause="附件2 二.6(7)",
        requirement="应急处置预案（不同等级事件处置流程）",
        maref_implementation="告警管理器（多渠道）+ 检疫/取证快照",
        module_path="maref.recursive.alert_manager",
        symbol="AlertManager",
        status=STATUS_COVERED,
        openclaw_only=True,
    ),
    FrameworkMapping(
        category=CATEGORY_MONITORING_AUDIT,
        clause="附件2 二.6(8)",
        requirement="重大变更安全验证（框架/工具/权限/策略变更回归）",
        maref_implementation="宪法守卫（红线变更拦截）+ 安全门自审",
        module_path="maref.evolution.constitution_guard",
        symbol="ConstitutionGuard",
        status=STATUS_COVERED,
    ),
    # ---- 7. 停用安全管理（附件2 二.7）----
    FrameworkMapping(
        category=CATEGORY_DECOMMISSION,
        clause="附件2 二.7(1)",
        requirement="下线全面关停（终止主程序/后台服务/配套进程）",
        maref_implementation="Decommissioner 编排：Agent24 状态机置 TERMINATING + 治理级 force_halt（OS 进程/端口核验待补）",
        module_path="maref.lifecycle.decommission",
        symbol="Decommissioner",
        status=STATUS_PARTIAL,
    ),
    FrameworkMapping(
        category=CATEGORY_DECOMMISSION,
        clause="附件2 二.7(2)",
        requirement="撤销第三方应用授权、禁用/撤销服务账号与访问权限",
        maref_implementation="DID 生命周期撤销 + 可用凭证撤销 + 身份服务吊销",
        module_path="maref.identity.did_registry",
        symbol="DIDRegistry",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_DECOMMISSION,
        clause="附件2 二.7(3)",
        requirement="数据留存处置：按需备份或清理运行期数据",
        maref_implementation="Decommissioner 备份步（复制必要数据到归档）+ 记忆管理器 purge，逐项核验",
        module_path="maref.lifecycle.decommission",
        symbol="Decommissioner",
        status=STATUS_COVERED,
    ),
    FrameworkMapping(
        category=CATEGORY_DECOMMISSION,
        clause="附件2 二.7",
        requirement="一站式停用编排（关停核验 + 端口/网络核验 + 授权撤销 + 备份 + 残留清理）",
        maref_implementation="Decommissioner 六步幂等编排（状态/停机/凭证/授权/备份/清理+核验，断点恢复）；端口/网络核验待补",
        module_path="maref.lifecycle.decommission",
        symbol="Decommissioner",
        status=STATUS_PARTIAL,
    ),
)


# ---------------------------------------------------------------------------
# 覆盖统计
# ---------------------------------------------------------------------------


def coverage_report() -> dict[str, Any]:
    """覆盖率统计（按状态与类别）。"""
    by_status: dict[str, int] = {STATUS_COVERED: 0, STATUS_PARTIAL: 0, STATUS_MISSING: 0}
    by_category: dict[str, dict[str, int]] = {
        c: {STATUS_COVERED: 0, STATUS_PARTIAL: 0, STATUS_MISSING: 0} for c in CATEGORIES
    }
    degraded: list[str] = []
    for m in MAPS:
        eff = effective_status(m)
        if m.openclaw_only and eff != m.status:
            degraded.append(m.clause)
        by_status[eff] = by_status.get(eff, 0) + 1
        by_category.setdefault(m.category, {STATUS_COVERED: 0, STATUS_PARTIAL: 0, STATUS_MISSING: 0})
        by_category[m.category][eff] = by_category[m.category].get(eff, 0) + 1

    total = len(MAPS)
    covered = by_status[STATUS_COVERED]
    return {
        "framework": "人工智能安全治理框架3.0",
        "source": "TC260, 2026-09, 附件2 智能体风险管理框架",
        "total": total,
        "by_status": by_status,
        "by_category": by_category,
        "coverage": f"{covered}/{total}",
        "coverage_ratio": round(covered / total, 4) if total else 0.0,
        "openclaw_only_degraded": degraded,
    }


def gaps() -> list[FrameworkMapping]:
    """返回未完全覆盖（partial / missing）的映射项（按运行时有效状态）。"""
    return [m for m in MAPS if effective_status(m) != STATUS_COVERED]


# ---------------------------------------------------------------------------
# 模块路径校验（fail-closed，无 import 副作用）
# ---------------------------------------------------------------------------


@cache
def _module_source_path(module_path: str) -> Path | None:
    """定位模块源码文件（纯文件系统查找，绝不触发 import 副作用）。

    结果缓存（functools.cache）：同进程内重复校验/渲染不重复 stat。
    """
    if not module_path:
        return None
    candidate = _SRC_ROOT.joinpath(*module_path.split("."))
    py_file = candidate.with_suffix(".py")
    if py_file.exists():
        return py_file
    init_file = candidate / "__init__.py"
    if init_file.exists():
        return init_file
    return None


def effective_status(mapping: FrameworkMapping) -> str:
    """运行时有效状态。

    单源双仓自洽：标记 ``openclaw_only`` 的映射依赖闭源模块，在开源仓中该模块
    缺失时声明态 ``covered`` 降级为 ``partial``（诚实标注，不粉饰），在开发仓中
    模块存在则维持 ``covered``。
    """
    if (
        mapping.openclaw_only
        and mapping.status == STATUS_COVERED
        and _module_source_path(mapping.module_path) is None
    ):
        return STATUS_PARTIAL
    return mapping.status


def _top_level_names(source: str) -> set[str]:
    """AST 收集模块顶层定义/导入名（含 try 块内定义）。"""
    names: set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return names
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.Try):
            for sub in ast.walk(node):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.add(sub.name)
    return names


def verify_mapping(mapping: FrameworkMapping) -> dict[str, Any]:
    """校验单条映射的 module_path 与 symbol 真实存在。"""
    if mapping.status == STATUS_MISSING and not mapping.module_path:
        return {
            "clause": mapping.clause,
            "module_path": mapping.module_path,
            "symbol": mapping.symbol,
            "ok": False,
            "reason": "declared-missing",
        }
    source_path = _module_source_path(mapping.module_path)
    if source_path is None:
        if mapping.openclaw_only:
            return {
                "clause": mapping.clause,
                "module_path": mapping.module_path,
                "symbol": mapping.symbol,
                "ok": True,
                "reason": "closed-source-dependency-absent",
            }
        return {
            "clause": mapping.clause,
            "module_path": mapping.module_path,
            "symbol": mapping.symbol,
            "ok": False,
            "reason": "module-not-found",
        }
    source = source_path.read_text(encoding="utf-8", errors="replace")
    # 直接定义（AST）或 __getattr__ 延迟导出（文本）两种方式都接受
    symbol_present = bool(mapping.symbol) and (
        mapping.symbol in _top_level_names(source)
        or ("def __getattr__" in source and mapping.symbol in source)
    )
    return {
        "clause": mapping.clause,
        "module_path": mapping.module_path,
        "symbol": mapping.symbol,
        "ok": symbol_present,
        "reason": "ok" if symbol_present else "symbol-not-found",
        "source": str(source_path),
    }


def verify_module_paths() -> list[str]:
    """返回校验失败的描述列表（空列表 = 全部通过）。fail-closed 供 CI 使用。"""
    failures: list[str] = []
    for m in MAPS:
        if m.status == STATUS_MISSING and not m.module_path:
            continue  # 明确声明缺失的条目不计入路径校验失败
        result = verify_mapping(m)
        if not result["ok"]:
            failures.append(
                f"{m.clause} {m.module_path}.{m.symbol} ({result['reason']})"
            )
    return failures


def verify_report() -> dict[str, Any]:
    """结构化校验报告。"""
    checked = [m for m in MAPS if not (m.status == STATUS_MISSING and not m.module_path)]
    results = [verify_mapping(m) for m in checked]
    passed = sum(1 for r in results if r["ok"])
    return {
        "total": len(checked),
        "passed": passed,
        "failed": len(checked) - passed,
        "pass": passed == len(checked),
        "results": results,
    }


# ---------------------------------------------------------------------------
# Markdown 渲染（幂等，可 CI 重生成）
# ---------------------------------------------------------------------------


def render_markdown() -> str:
    report = coverage_report()
    lines: list[str] = []
    lines.append("# MAREF ×《人工智能安全治理框架 3.0》映射矩阵")
    lines.append("")
    lines.append(
        "> 本文件由 `src/maref/compliance/cac/framework_3_0.py::render_markdown()` 自动生成，请勿手工编辑。"
    )
    lines.append(
        f"> 依据：{report['source']}　|　总条目：{report['total']}　|　完全覆盖：{report['coverage']}"
    )
    lines.append("")
    lines.append("## 覆盖统计")
    lines.append("")
    lines.append("| 状态 | 数量 |")
    lines.append("|---|---|")
    for status in (STATUS_COVERED, STATUS_PARTIAL, STATUS_MISSING):
        lines.append(
            f"| {STATUS_LABELS[status]} | {report['by_status'][status]} |"
        )
    lines.append("")
    lines.append("| 防范措施（附件2 二） | 已覆盖 | 部分覆盖 | 缺失 |")
    lines.append("|---|---|---|---|")
    for cat in CATEGORIES:
        row = report["by_category"].get(cat, {})
        lines.append(
            f"| {cat} | {row.get(STATUS_COVERED, 0)} | "
            f"{row.get(STATUS_PARTIAL, 0)} | {row.get(STATUS_MISSING, 0)} |"
        )
    lines.append("")
    if report["openclaw_only_degraded"]:
        lines.append(
            f"> 注：{len(report['openclaw_only_degraded'])} 条映射依赖闭源（开发仓专有）模块，"
            "在开源仓中按「部分覆盖」计，已如实标注。"
        )
        lines.append("")
    lines.append("## 逐条映射")
    for cat in CATEGORIES:
        lines.append("")
        lines.append(f"### {cat}")
        lines.append("")
        lines.append("| 条款 | 框架要求 | MAREF 实现 | 模块 · 符号 | 状态 |")
        lines.append("|---|---|---|---|---|")
        for m in [x for x in MAPS if x.category == cat]:
            eff = effective_status(m)
            module = (
                f"`{m.module_path}.{m.symbol}`"
                if m.module_path
                else "—"
            )
            req = m.requirement.replace("|", "\\|").replace("\n", " ")
            impl = m.maref_implementation.replace("|", "\\|").replace("\n", " ")
            label = STATUS_LABELS[eff]
            if m.openclaw_only:
                label += "（依赖闭源模块）"
            lines.append(
                f"| {m.clause} | {req} | {impl} | {module} | {label} |"
            )
    lines.append("")
    lines.append("## 校验")
    lines.append("")
    lines.append("```")
    lines.append("python3 -m maref.compliance.cac.framework_3_0 verify")
    lines.append("```")
    lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_report(as_json: bool) -> int:
    report = coverage_report()
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"《人工智能安全治理框架3.0》MAREF 映射覆盖：{report['coverage']}")
        for status in (STATUS_COVERED, STATUS_PARTIAL, STATUS_MISSING):
            print(f"  {STATUS_LABELS[status]}: {report['by_status'][status]}")
    return 0


def _cmd_gaps(as_json: bool) -> int:
    items = gaps()
    if as_json:
        print(json.dumps([m.to_dict() for m in items], ensure_ascii=False, indent=2))
    else:
        if not items:
            print("无缺口：全部已覆盖")
        for m in items:
            print(f"  [{STATUS_LABELS[m.status]}] {m.clause} {m.requirement}")
    return 0


def _cmd_verify(as_json: bool) -> int:
    report = verify_report()
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"模块路径校验：{report['passed']}/{report['total']} 通过")
        for r in report["results"]:
            if not r["ok"]:
                print(f"  ❌ {r['clause']} {r['module_path']}.{r['symbol']} ({r['reason']})")
    return 0 if report["pass"] else 1


def _cmd_render(out: str | None) -> int:
    content = render_markdown()
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"已写入 {path}")
    else:
        print(content)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m maref.compliance.cac.framework_3_0",
        description="MAREF ×《人工智能安全治理框架3.0》映射与校验",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_report = sub.add_parser("report", help="覆盖率统计")
    p_report.add_argument("--json", action="store_true")

    p_gaps = sub.add_parser("gaps", help="缺口清单（partial/missing）")
    p_gaps.add_argument("--json", action="store_true")

    p_verify = sub.add_parser("verify", help="module_path/symbol fail-closed 校验（exit 1=失败）")
    p_verify.add_argument("--json", action="store_true")

    p_render = sub.add_parser("render", help="渲染映射矩阵 Markdown")
    p_render.add_argument("--out", default=None, help="输出文件路径；省略则打印到 stdout")

    args = parser.parse_args(argv)
    if args.command == "report":
        return _cmd_report(args.json)
    if args.command == "gaps":
        return _cmd_gaps(args.json)
    if args.command == "verify":
        return _cmd_verify(args.json)
    if args.command == "render":
        return _cmd_render(args.out)
    return 2


__all__ = [
    "CATEGORIES",
    "CATEGORY_DECOMMISSION",
    "CATEGORY_HUMAN_APPROVAL",
    "CATEGORY_IDENTITY_PERMISSION",
    "CATEGORY_MONITORING_AUDIT",
    "CATEGORY_RISK_PREVENTION",
    "CATEGORY_RUNTIME_CONTROL",
    "CATEGORY_SUPPLY_CHAIN",
    "FrameworkMapping",
    "MAPS",
    "STATUS_COVERED",
    "STATUS_MISSING",
    "STATUS_PARTIAL",
    "coverage_report",
    "gaps",
    "main",
    "render_markdown",
    "verify_mapping",
    "verify_module_paths",
    "verify_report",
]


if __name__ == "__main__":
    sys.exit(main())
