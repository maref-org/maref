"""停用安全管理编排（框架 3.0 附件2 二.7）。

《人工智能安全治理框架3.0》附件2 二.7 要求智能体下线/停用时做好安全管理：
全面关停、凭证与授权撤销、必要数据备份、残留清理并核验。

本模块把既有碎片（``recursive.Agent24StateMachine``、
``governance.GovernanceStateMachine.force_halt``、``identity`` 的凭证撤销、
``memory`` 清理）组合为一个幂等、可恢复、留痕的编排器 ``Decommissioner``。

设计: docs/plans/2026-10-02-maref-framework-3-0-compliance-mapping-plan.md P3
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_SKIP = "skip"

DEFAULT_STATE_DIR = ".openclaw/decommission"


class DecommissionStep(StrEnum):
    """停用六步（顺序即执行顺序）。"""

    MARK_TERMINATING = "标记终止中"
    HALT = "治理级停机"
    REVOKE_CREDENTIALS = "撤销凭证"
    REVOKE_AUTHORIZATIONS = "撤销第三方授权"
    BACKUP = "备份必要数据"
    CLEANUP = "清理残留并核验"


@dataclass(frozen=True)
class StepResult:
    step: DecommissionStep
    status: str
    detail: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step.name,
            "label": self.step.value,
            "status": self.status,
            "detail": self.detail,
            "evidence": self.evidence,
        }


@dataclass
class DecommissionReport:
    agent_id: str
    steps: list[StepResult] = field(default_factory=list)
    generated_at: float = field(default_factory=time.time)

    @property
    def ok(self) -> bool:
        return not any(s.status == STATUS_FAIL for s in self.steps)

    @property
    def failures(self) -> list[StepResult]:
        return [s for s in self.steps if s.status == STATUS_FAIL]

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "ok": self.ok,
            "generated_at": self.generated_at,
            "steps": [s.to_dict() for s in self.steps],
        }

    def summary(self) -> str:
        lines = [f"停用报告 agent={self.agent_id} ok={self.ok}"]
        for s in self.steps:
            lines.append(f"  [{s.status}] {s.step.value}: {s.detail}")
        return "\n".join(lines)

    def write(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return out


class Decommissioner:
    """幂等编排器：组合既有碎片完成六步停用。

    所有协作者均为可选注入；缺失时该步骤如实报告 ``skip``（绝不假 ``pass``）。
    默认 ``dry_run=True``：只做只读探测、输出执行计划，不产生任何副作用。
    """

    def __init__(
        self,
        *,
        state_machine: Any | None = None,
        governance_state_machine: Any | None = None,
        identity_service: Any | None = None,
        credential_manager: Any | None = None,
        authorization_registry: Any | None = None,
        memory_manager: Any | None = None,
        backup_fn: Callable[[str, Path], Any] | None = None,
        backup_sources: list[str] | None = None,
        did: str | None = None,
        credential_ids: list[str] | None = None,
        memory_ids: list[str] | None = None,
        residual_paths: list[str] | None = None,
        state_dir: str | Path = DEFAULT_STATE_DIR,
        dry_run: bool = True,
    ) -> None:
        self.state_machine = state_machine
        self.governance_state_machine = governance_state_machine
        self.identity_service = identity_service
        self.credential_manager = credential_manager
        self.authorization_registry = authorization_registry
        self.memory_manager = memory_manager
        self.backup_fn = backup_fn
        self.backup_sources = backup_sources or []
        self.did = did
        self.credential_ids = credential_ids or []
        self.memory_ids = memory_ids or []
        self.residual_paths = residual_paths or []
        self.state_dir = Path(state_dir)
        self.dry_run = dry_run

    # ------------------------------------------------------------------ #
    # 状态持久化（幂等 / 断点恢复）
    # ------------------------------------------------------------------ #
    def _state_file(self, agent_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in agent_id)
        return self.state_dir / f"{safe}.json"

    def _load_completed(self, agent_id: str) -> set[str]:
        path = self._state_file(agent_id)
        if not path.exists():
            return set()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return set()
        return set(data.get("completed_steps", []))

    def _save_completed(self, agent_id: str, completed: set[str]) -> None:
        path = self._state_file(agent_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "agent_id": agent_id,
            "completed_steps": sorted(completed),
            "updated_at": time.time(),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _audit(self, agent_id: str, result: StepResult) -> None:
        path = self.state_dir / "audit.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        line = {"ts": time.time(), "agent_id": agent_id, **result.to_dict()}
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------ #
    # 六步
    # ------------------------------------------------------------------ #
    def _step_mark_terminating(self, agent_id: str) -> StepResult:
        step = DecommissionStep.MARK_TERMINATING
        if self.state_machine is None:
            return StepResult(step, STATUS_SKIP, "未注入 state_machine")
        from maref.recursive.agent_24_state_machine import AgentStateV3

        current = self.state_machine.state_of(agent_id)
        if current in (AgentStateV3.TERMINATING, AgentStateV3.TERMINATED):
            return StepResult(step, STATUS_PASS, f"已是 {current.value}", {"state": current.value})
        if self.dry_run:
            return StepResult(step, STATUS_SKIP, "dry-run：计划迁移到 TERMINATING")
        transition = self.state_machine.transition(agent_id, AgentStateV3.TERMINATING)
        if transition is None:
            transition = self.state_machine.force_transition(agent_id, AgentStateV3.TERMINATING)
        if transition is None:
            return StepResult(step, STATUS_FAIL, "无法迁移到 TERMINATING")
        return StepResult(step, STATUS_PASS, "已置 TERMINATING", {"to": AgentStateV3.TERMINATING.value})

    def _step_halt(self, agent_id: str) -> StepResult:
        step = DecommissionStep.HALT
        if self.governance_state_machine is None:
            return StepResult(step, STATUS_SKIP, "未注入 governance_state_machine")
        if self.dry_run:
            return StepResult(step, STATUS_SKIP, "dry-run：计划 force_halt")
        ok = self.governance_state_machine.force_halt(
            f"decommission:{agent_id}", actor="decommissioner"
        )
        if ok:
            return StepResult(step, STATUS_PASS, "治理级已停机（HALT）")
        return StepResult(step, STATUS_FAIL, "force_halt 返回 False")

    def _step_revoke_credentials(self, agent_id: str) -> StepResult:
        step = DecommissionStep.REVOKE_CREDENTIALS
        if self.identity_service is None and self.credential_manager is None:
            return StepResult(step, STATUS_SKIP, "未注入 identity_service / credential_manager")
        if self.dry_run:
            return StepResult(step, STATUS_SKIP, "dry-run：计划撤销 DID 与凭据")

        did = self.did or agent_id
        evidence: dict[str, Any] = {}
        try:
            if self.identity_service is not None:
                evidence["identity"] = self.identity_service.revoke(did, reason="agent decommission")
            for cid in self.credential_ids:
                evidence[f"credential:{cid}"] = self.credential_manager.revoke(cid, "decommission")
        except Exception as exc:  # noqa: BLE001 - 编排器需捕获任意协作者异常并留证
            return StepResult(step, STATUS_FAIL, f"撤销异常：{exc}", evidence)
        return StepResult(step, STATUS_PASS, f"已处理 {len(evidence)} 项", evidence)

    def _step_revoke_authorizations(self, agent_id: str) -> StepResult:
        step = DecommissionStep.REVOKE_AUTHORIZATIONS
        if self.authorization_registry is None:
            return StepResult(step, STATUS_SKIP, "未注入 authorization_registry")
        if self.dry_run:
            return StepResult(step, STATUS_SKIP, "dry-run：计划撤销第三方授权")
        try:
            auths = list(self.authorization_registry.list_authorizations(agent_id))
            if not auths:
                return StepResult(step, STATUS_PASS, "无第三方授权", {"count": 0})
            revoked = [a for a in auths if self.authorization_registry.revoke(a)]
        except Exception as exc:  # noqa: BLE001
            return StepResult(step, STATUS_FAIL, f"撤销授权异常：{exc}")
        evidence = {"total": len(auths), "revoked": len(revoked)}
        if len(revoked) < len(auths):
            return StepResult(step, STATUS_FAIL, "部分授权未撤销", evidence)
        return StepResult(step, STATUS_PASS, f"已撤销 {len(revoked)} 项授权", evidence)

    def _default_backup(self, agent_id: str, dest: Path) -> list[str]:
        produced: list[str] = []
        target = dest / agent_id
        target.mkdir(parents=True, exist_ok=True)
        for src in self.backup_sources:
            sp = Path(src)
            if not sp.exists():
                continue
            dst = target / sp.name
            if sp.is_dir():
                shutil.copytree(sp, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(sp, dst)
            produced.append(str(dst))
        return produced

    def _step_backup(self, agent_id: str) -> StepResult:
        step = DecommissionStep.BACKUP
        backup = self.backup_fn or (self._default_backup if self.backup_sources else None)
        if backup is None:
            return StepResult(step, STATUS_SKIP, "未配置备份源 / backup_fn")
        if self.dry_run:
            return StepResult(step, STATUS_SKIP, "dry-run：计划备份必要数据")
        try:
            produced = backup(agent_id, self.state_dir / "backups")
        except Exception as exc:  # noqa: BLE001
            return StepResult(step, STATUS_FAIL, f"备份异常：{exc}")
        if not produced:
            return StepResult(step, STATUS_FAIL, "备份未产出任何文件")
        return StepResult(step, STATUS_PASS, f"备份 {len(produced)} 项", {"artifacts": produced})

    def _step_cleanup(self, agent_id: str) -> StepResult:
        step = DecommissionStep.CLEANUP
        if self.memory_manager is None and not self.residual_paths:
            return StepResult(step, STATUS_SKIP, "无清理目标（memory / residual_paths）")
        if self.dry_run:
            return StepResult(step, STATUS_SKIP, "dry-run：计划清理残留并核验")
        purged: list[str] = []
        removed: list[str] = []
        try:
            for mid in self.memory_ids:
                if self.memory_manager is not None and self.memory_manager.purge(mid):
                    purged.append(mid)
            for raw in self.residual_paths:
                p = Path(raw)
                if p.exists():
                    p.unlink()
                    removed.append(raw)
        except Exception as exc:  # noqa: BLE001
            return StepResult(step, STATUS_FAIL, f"清理异常：{exc}")
        leftovers = [raw for raw in self.residual_paths if Path(raw).exists()]
        evidence = {"memory_purged": purged, "files_removed": removed, "leftovers": leftovers}
        if leftovers:
            return StepResult(step, STATUS_FAIL, f"仍有残留 {len(leftovers)} 项", evidence)
        return StepResult(step, STATUS_PASS, "残留已清理并核验", evidence)

    # ------------------------------------------------------------------ #
    # 编排
    # ------------------------------------------------------------------ #
    def _steps(self) -> list[tuple[DecommissionStep, Callable[[str], StepResult]]]:
        return [
            (DecommissionStep.MARK_TERMINATING, self._step_mark_terminating),
            (DecommissionStep.HALT, self._step_halt),
            (DecommissionStep.REVOKE_CREDENTIALS, self._step_revoke_credentials),
            (DecommissionStep.REVOKE_AUTHORIZATIONS, self._step_revoke_authorizations),
            (DecommissionStep.BACKUP, self._step_backup),
            (DecommissionStep.CLEANUP, self._step_cleanup),
        ]

    def run(self, agent_id: str) -> DecommissionReport:
        completed = self._load_completed(agent_id)
        report = DecommissionReport(agent_id=agent_id)
        for step, fn in self._steps():
            if step.name in completed:
                report.steps.append(
                    StepResult(step, STATUS_PASS, "resume：此前已完成", {"resumed": True})
                )
                continue
            result = fn(agent_id)
            report.steps.append(result)
            self._audit(agent_id, result)
            if result.status == STATUS_PASS and not self.dry_run:
                completed.add(step.name)
                self._save_completed(agent_id, completed)
        report.write(self.state_dir / f"{agent_id}.report.json")
        return report


def _cmd_run(agent_id: str, state_dir: str, execute: bool, as_json: bool) -> int:
    decom = Decommissioner(state_dir=state_dir, dry_run=not execute)
    report = decom.run(agent_id)
    if as_json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(report.summary())
    return 0 if report.ok else 1


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python3 -m maref.lifecycle.decommission",
        description="框架 3.0 停用安全管理编排（默认 dry-run）",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run")
    p.add_argument("agent_id")
    p.add_argument("--state-dir", default=DEFAULT_STATE_DIR)
    p.add_argument("--execute", action="store_true", help="真正执行（默认只做计划）")
    p.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "run":
        return _cmd_run(args.agent_id, args.state_dir, args.execute, args.json)
    return 2


__all__ = [
    "DEFAULT_STATE_DIR",
    "STATUS_FAIL",
    "STATUS_PASS",
    "STATUS_SKIP",
    "DecommissionReport",
    "DecommissionStep",
    "Decommissioner",
    "StepResult",
    "main",
]


if __name__ == "__main__":
    sys.exit(main())
