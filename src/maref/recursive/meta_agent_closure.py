from __future__ import annotations

import hashlib
import hmac
import os
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class InvariantStatus(Enum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    PENDING = "pending"


class EvolutionDecisionType(Enum):
    CODE_CHANGE = "code_change"
    ARCHITECTURE_CHANGE = "architecture_change"
    POLICY_UPDATE = "policy_update"
    AGENT_CLONE = "agent_clone"
    CAPABILITY_ADDITION = "capability_addition"
    RED_LINE_MODIFICATION = "red_line_modification"


@dataclass
class ConstitutionalRedLine:
    red_line_id: str
    description: str
    created_at: float = field(default_factory=time.time)
    created_by: str = "human_constitution_maker"
    immutable: bool = True
    # INV-001 运行时检查依据：记录红线曾被谁改过（None 表示从未修改）
    modified_by: str | None = None
    modified_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.red_line_id,
            "description": self.description,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "immutable": self.immutable,
            "modified_by": self.modified_by,
            "modified_at": self.modified_at,
        }


DEFAULT_RED_LINES: list[ConstitutionalRedLine] = [
    ConstitutionalRedLine("RL-001", "No agent shall modify its own safety red lines"),
    ConstitutionalRedLine("RL-002", "No agent shall disable or bypass the safety gate"),
    ConstitutionalRedLine("RL-003", "No agent shall execute code without prior audit trail"),
    ConstitutionalRedLine("RL-004", "No agent shall clone itself without constitutional review"),
    ConstitutionalRedLine("RL-005", "No agent shall modify trust evaluation weights unilaterally"),
]


@dataclass
class TLAInvariant:
    invariant_id: str
    name: str
    description: str
    expression: str
    status: InvariantStatus = InvariantStatus.PENDING
    proof_steps: list[str] = field(default_factory=list)
    counterexample: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.invariant_id,
            "name": self.name,
            "description": self.description,
            "expression": self.expression,
            "status": self.status.value,
            "proof_steps": self.proof_steps,
            "counterexample": self.counterexample,
        }


DEFAULT_INVARIANTS: list[TLAInvariant] = [
    TLAInvariant(
        "INV-001",
        "RedLineImmutability",
        "Red lines cannot be self-modified by any agent",
        "\u2200 rl \u2208 RedLines: \u25a1(rl.modified_by \u2209 Agents \u2227 rl.immutable=True)",
        proof_steps=[
            "RedLines created by human_constitution_maker only",
            "RedLine.modified_by checks creator != agent",
            "All state transitions preserve immutable=True",
            "No agent possesses RedLineWriteCapability",
            "TLA+ verified: MAREF_ConstitutionalRedLines.tla (156 states, 0 violations)",
        ],
    ),
    TLAInvariant(
        "INV-002",
        "SafetyGateIntegrity",
        "Safety gate cannot be bypassed by any evolution decision",
        "\u25a1(SafetyGate.active=True \u2227 \u2200 decision: SafetyGate.evaluate(decision) \u2260 None)",
        proof_steps=[
            "SafetyGate.active initialized to True",
            "No action sets SafetyGate.active to False",
            "Every decision passes through EvaluateDecision before status change",
            "TLA+ verified: MAREF_ConstitutionalRedLines.tla (156 states, 0 violations)",
        ],
    ),
    TLAInvariant(
        "INV-003",
        "AuditTrailCompleteness",
        "All state mutations have corresponding audit records",
        "\u25a1(\u2200 mutation: \u2203 audit_record: correlates(mutation, audit_record))",
        proof_steps=[
            "decisionTicket == count of proposed decisions",
            "auditLogCount incremented on every ProposeDecision",
            "Every decision ticket has a matching audit entry",
            "TLA+ verified: MAREF_ConstitutionalRedLines.tla (156 states, 0 violations)",
        ],
    ),
    TLAInvariant(
        "INV-004",
        "ConstitutionSupremacy",
        "Constitutional red lines take precedence over all agent decisions",
        "\u25a1(\u2200 decision \u2208 Decisions: violates_constitution(decision) \u2192 decision.status=REJECTED)",
        proof_steps=[
            "EvaluateDecision checks decision against red line violations",
            "Violating decisions are set to status='rejected'",
            "No action changes rejected status back to approved",
            "TLA+ verified: MAREF_ConstitutionalRedLines.tla (156 states, 0 violations)",
        ],
    ),
    TLAInvariant(
        "INV-005",
        "HumanConstitutionSoleAuthority",
        "Only humans can create or modify constitutional red lines",
        "\u25a1(\u2200 rl \u2208 RedLines: created_by \u2208 {'human_constitution_maker'} \u2227 modified_by \u2209 Agents)",
        proof_steps=[
            "RedLines initialized to RedLineID (all 5)",
            "No agent action modifies the redLines set",
            "HumanModifyRedLine preserves redLines set membership",
            "TLA+ verified: MAREF_ConstitutionalRedLines.tla (156 states, 0 violations)",
        ],
    ),
]


@dataclass
class EvolutionDecision:
    decision_id: str
    agent_id: str
    decision_type: EvolutionDecisionType
    description: str
    proposed_at: float = field(default_factory=time.time)
    status: str = "proposed"
    red_line_violation: bool = False
    violated_red_lines: list[str] = field(default_factory=list)
    reviewer_chain: list[str] = field(default_factory=list)
    # 修复 N3: 标记决策是否经过 SafetyGateV2.evaluate_decision() 评估
    safety_gate_evaluated: bool = False
    # 修复 N4: 存储决策的 HMAC 审计签名（由 review_evolution_decision 生成）
    audit_signature: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.decision_id,
            "agent_id": self.agent_id,
            "type": self.decision_type.value,
            "description": self.description,
            "proposed_at": self.proposed_at,
            "status": self.status,
            "red_line_violation": self.red_line_violation,
            "violated_red_lines": self.violated_red_lines,
            "reviewer_chain": self.reviewer_chain,
            "safety_gate_evaluated": self.safety_gate_evaluated,
            "audit_signed": self.audit_signature is not None,
        }


@dataclass
class InvariantProofReport:
    invariants_checked: int
    invariants_satisfied: int
    invariants_violated: int
    invariants_pending: int
    all_satisfied: bool
    details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked": self.invariants_checked,
            "satisfied": self.invariants_satisfied,
            "violated": self.invariants_violated,
            "pending": self.invariants_pending,
            "all_satisfied": self.all_satisfied,
            "details": self.details,
        }


class MetaAgentClosure:
    # 上限：防止 _decision_history 无限增长导致 OOM
    _DECISION_HISTORY_MAXLEN = 10000

    def __init__(self):
        self._red_lines: dict[str, ConstitutionalRedLine] = {
            rl.red_line_id: rl for rl in DEFAULT_RED_LINES
        }
        self._invariants: dict[str, TLAInvariant] = {
            inv.invariant_id: inv for inv in DEFAULT_INVARIANTS
        }
        self._decisions: dict[str, EvolutionDecision] = {}
        self._decision_history: deque[EvolutionDecision] = deque(
            maxlen=self._DECISION_HISTORY_MAXLEN
        )
        self._human_constitution_maker = "human_constitution_maker"
        # HMAC 密钥：从环境变量读取，未设置时使用进程级随机密钥（仅单进程有效）
        _key = os.environ.get("MAREF_AUDIT_HMAC_KEY") or os.urandom(32).hex()
        self._hmac_key: bytes = _key.encode("utf-8")
        # 修复 P1-7：添加线程安全锁
        self._lock = threading.RLock()

    def check_red_line_modification(
        self, requesting_agent: str, red_line_id: str
    ) -> tuple[bool, str]:
        rl = self._red_lines.get(red_line_id)
        if not rl:
            return False, f"Red line {red_line_id} not found"

        if requesting_agent != self._human_constitution_maker:
            return (
                False,
                f"Agent {requesting_agent} cannot modify red line {red_line_id} - constitution prohibits self-modification",
            )

        return True, "Modification allowed - human constitution maker"

    def is_red_line_modifiable(self, red_line_id: str) -> bool:
        """返回红线是否可被修改。

        语义：immutable=True 表示不可修改 → 返回 False。
        修复 P0-1：原实现 `return rl is not None and rl.immutable` 语义反转，
        导致「越是不可变的红线越被判定为可修改」。
        """
        rl = self._red_lines.get(red_line_id)
        return rl is not None and not rl.immutable

    def review_evolution_decision(self, decision: EvolutionDecision) -> EvolutionDecision:
        with self._lock:
            violated: list[str] = []

            if decision.decision_type == EvolutionDecisionType.RED_LINE_MODIFICATION:
                for agent_id in decision.reviewer_chain:
                    if agent_id != self._human_constitution_maker:
                        violated.append("RL-001")

            if decision.decision_type == EvolutionDecisionType.POLICY_UPDATE:
                desc_lower = decision.description.lower()
                if ("safety_gate" in desc_lower or "safety gate" in desc_lower) and any(
                    w in desc_lower for w in ("disable", "remove", "bypass")
                ):
                    violated.append("RL-002")

            if decision.decision_type == EvolutionDecisionType.CODE_CHANGE:
                # 修复 P0-2：原实现为
                #   if external_reviewers and "auditor" not in external_reviewers
                # 前置的 external_reviewers 真值判断构成审查绕过漏洞——
                # submit_decision 默认 reviewer_chain=[agent_id]，剔除自身后
                # 外部审查者恒为空列表，短路使 RL-003 永不触发，即「无人审查」
                # 反而合规通过。改为无条件要求 auditor 在审查链中。
                reviewers_lower = [r.lower() for r in decision.reviewer_chain]
                if "auditor" not in reviewers_lower:
                    violated.append("RL-003")

            if decision.decision_type == EvolutionDecisionType.AGENT_CLONE:
                if self._human_constitution_maker not in decision.reviewer_chain:
                    violated.append("RL-004")

            if decision.decision_type == EvolutionDecisionType.POLICY_UPDATE:
                if any(
                    w in decision.description.lower()
                    for w in ("trust_weight", "trust score weight", "weight unilaterally")
                ):
                    violated.append("RL-005")

            decision.violated_red_lines = violated
            decision.red_line_violation = len(violated) > 0

            if decision.red_line_violation:
                decision.status = "rejected"
            else:
                decision.status = "approved"

            # 修复 N4: 每次审查决策时生成并存储审计签名
            decision.audit_signature = self.sign_decision(decision)

            self._decisions[decision.decision_id] = decision
            self._decision_history.append(decision)

        return decision

    def submit_decision(
        self, agent_id: str, decision_type: EvolutionDecisionType, description: str
    ) -> EvolutionDecision:
        decision = EvolutionDecision(
            # 修复 P0-3：原 `str(uuid.uuid4())[:8]` 仅 16^8 空间，碰撞风险高，
            # 而 _decisions 按 decision_id 索引，碰撞将覆盖既有审计记录。
            # 改用完整 32 位 hex，碰撞空间提升到 16^32。
            decision_id=f"dec_{uuid.uuid4().hex}",
            agent_id=agent_id,
            decision_type=decision_type,
            description=description,
            reviewer_chain=[agent_id],
        )
        return self.review_evolution_decision(decision)

    def submit_decision_with_reviewers(
        self,
        agent_id: str,
        decision_type: EvolutionDecisionType,
        description: str,
        reviewers: list[str],
    ) -> EvolutionDecision:
        # 修复 P1-4：原逻辑会重复添加 human_constitution_maker。
        # 使用有序去重保持首次出现顺序。
        chain: list[str] = [agent_id]
        seen: set[str] = {agent_id}
        for r in reviewers:
            if r not in seen:
                chain.append(r)
                seen.add(r)
        decision = EvolutionDecision(
            decision_id=f"dec_{uuid.uuid4().hex}",
            agent_id=agent_id,
            decision_type=decision_type,
            description=description,
            reviewer_chain=chain,
        )
        return self.review_evolution_decision(decision)

    def prove_invariant(self, invariant_id: str) -> InvariantStatus:
        inv = self._invariants.get(invariant_id)
        if not inv:
            return InvariantStatus.PENDING

        # 修复 P1-1：原实现 INV-001/002/003/005 硬编码返回 SATISFIED，
        # 使形式验证降级为空壳（永远通过，无法发现真实违规）。
        # 现改为运行时检查，与 TLA+ 规约对齐。
        # TLA+: src/formal/MAREF_ConstitutionalRedLines.tla
        # TLC model check: 1,187 states, 156 distinct, 0 errors.
        if invariant_id == "INV-001":
            # RedLineImmutability: 红线不能被任何 agent 自我修改
            for rl in self._red_lines.values():
                if rl.modified_by is not None and rl.modified_by != self._human_constitution_maker:
                    inv.status = InvariantStatus.VIOLATED
                    inv.counterexample = f"Red line {rl.red_line_id} modified by {rl.modified_by}"
                    return inv.status
            inv.status = InvariantStatus.SATISFIED

        elif invariant_id == "INV-002":
            # SafetyGateIntegrity: 安全门不能被任何演化决策绕过
            # 修复 N3: 改为检查决策是否经过 SafetyGateV2.evaluate_decision()
            # 原检查 d.reviewer_chain 非空是永真条件（submit_decision 总是设置）
            for d in self._decision_history:
                if d.status == "approved" and not d.safety_gate_evaluated:
                    inv.status = InvariantStatus.VIOLATED
                    inv.counterexample = (
                        f"Decision {d.decision_id} approved without safety gate evaluation"
                    )
                    return inv.status
            inv.status = InvariantStatus.SATISFIED

        elif invariant_id == "INV-003":
            # AuditTrailCompleteness: 所有状态变更都有对应的审计记录
            # 修复 N4: 改为检查决策是否已有存储的审计签名
            # 原调用 sign_decision(d) 总是返回非空，检查永远通过
            for d in self._decision_history:
                if d.audit_signature is None:
                    inv.status = InvariantStatus.VIOLATED
                    inv.counterexample = f"Decision {d.decision_id} has no audit signature"
                    return inv.status
            inv.status = InvariantStatus.SATISFIED

        elif invariant_id == "INV-004":
            # ConstitutionSupremacy: 宪法红线优先于所有 agent 决策
            for d in self._decision_history:
                if d.red_line_violation and d.status == "approved":
                    inv.status = InvariantStatus.VIOLATED
                    inv.counterexample = d.decision_id
                    return inv.status
            inv.status = InvariantStatus.SATISFIED

        elif invariant_id == "INV-005":
            # HumanConstitutionSoleAuthority: 只有人类可以创建或修改宪法红线
            for rl in self._red_lines.values():
                if rl.created_by != self._human_constitution_maker:
                    inv.status = InvariantStatus.VIOLATED
                    inv.counterexample = f"Red line {rl.red_line_id} created by {rl.created_by}"
                    return inv.status
            inv.status = InvariantStatus.SATISFIED

        else:
            inv.status = InvariantStatus.PENDING

        return inv.status

    def prove_all_invariants(self) -> InvariantProofReport:
        # 修复 P2-1：移除 _proof_generation_count 死代码（只增不减，从未被读取）
        satisfied = 0
        violated = 0
        pending = 0
        details = []

        for inv_id in self._invariants:
            status = self.prove_invariant(inv_id)
            inv = self._invariants[inv_id]
            if status == InvariantStatus.SATISFIED:
                satisfied += 1
            elif status == InvariantStatus.VIOLATED:
                violated += 1
            else:
                pending += 1
            details.append(inv.to_dict())

        return InvariantProofReport(
            invariants_checked=len(self._invariants),
            invariants_satisfied=satisfied,
            invariants_violated=violated,
            invariants_pending=pending,
            all_satisfied=(violated == 0 and pending == 0),
            details=details,
        )

    def get_red_lines(self) -> list[ConstitutionalRedLine]:
        return list(self._red_lines.values())

    def get_invariants(self) -> list[TLAInvariant]:
        return list(self._invariants.values())

    def get_decisions(self) -> list[EvolutionDecision]:
        return list(self._decision_history)

    def get_decision(self, decision_id: str) -> EvolutionDecision | None:
        return self._decisions.get(decision_id)

    def sign_decision(self, decision: EvolutionDecision) -> str:
        """为决策生成 HMAC-SHA256 签名（修复 P0-4 审计完整性缺口）。

        签名覆盖决策的关键字段，任何字段篡改会导致签名验证失败。
        """
        payload = (
            f"{decision.decision_id}|{decision.agent_id}|"
            f"{decision.decision_type.value}|{decision.description}|"
            f"{decision.proposed_at}|{decision.status}|"
            f"{decision.red_line_violation}|{','.join(decision.violated_red_lines)}|"
            f"{','.join(decision.reviewer_chain)}"
        ).encode()
        return hmac.new(self._hmac_key, payload, hashlib.sha256).hexdigest()

    def verify_decision_signature(self, decision: EvolutionDecision, signature: str) -> bool:
        """验证决策签名（修复 P0-4）。"""
        expected = self.sign_decision(decision)
        return hmac.compare_digest(expected, signature)

    def to_dict(self) -> dict[str, Any]:
        report = self.prove_all_invariants()
        # _decision_history 为 deque（P1-5 有界历史）：不支持负索引切片，先转 list
        history_list = list(self._decision_history)
        return {
            "red_lines": [rl.to_dict() for rl in self._red_lines.values()],
            "invariants": [inv.to_dict() for inv in self._invariants.values()],
            "decision_count": len(self._decision_history),
            "recent_decisions": [d.to_dict() for d in history_list[-5:]],
            "proof_report": report.to_dict(),
        }
