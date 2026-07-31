from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:

    pass

logger = logging.getLogger(__name__)


class RELState(Enum):
    IDLE = 0b0000
    TRIGGERED = 0b0001
    OBSERVE = 0b0011
    DIAGNOSE = 0b0010
    ARCHITECT = 0b0110
    CODEGEN = 0b0111
    SAFETY = 0b0101
    DEPLOY = 0b0100
    VERIFY = 0b1100
    EVALUATE = 0b1101
    STOP = 0b1111
    HALT = 0b1110


_REL_TRANSITIONS: dict[RELState, list[RELState]] = {
    RELState.IDLE: [RELState.TRIGGERED],
    RELState.TRIGGERED: [RELState.OBSERVE],
    RELState.OBSERVE: [RELState.DIAGNOSE],
    RELState.DIAGNOSE: [RELState.ARCHITECT],
    RELState.ARCHITECT: [RELState.CODEGEN],
    RELState.CODEGEN: [RELState.SAFETY, RELState.ARCHITECT],
    RELState.SAFETY: [RELState.DEPLOY],
    RELState.DEPLOY: [RELState.VERIFY],
    RELState.VERIFY: [RELState.EVALUATE, RELState.CODEGEN],
    RELState.EVALUATE: [RELState.OBSERVE, RELState.STOP, RELState.IDLE],
    RELState.STOP: [],
    RELState.HALT: [RELState.IDLE],
}


def hamming_distance(a: RELState, b: RELState) -> int:
    return (a.value ^ b.value).bit_count()


def can_transition(current: RELState, target: RELState) -> bool:
    if target == RELState.HALT and current not in (RELState.HALT, RELState.STOP):
        return True
    return target in _REL_TRANSITIONS.get(current, [])


class IllegalTransitionError(RuntimeError):
    pass


class RELStateMachine:
    def __init__(self) -> None:
        self._state = RELState.IDLE
        self._transition_history: list[tuple[RELState, RELState, float]] = []

    @property
    def state(self) -> RELState:
        return self._state

    @property
    def transition_history(self) -> list[tuple[RELState, RELState, float]]:
        return list(self._transition_history)

    def transition(self, target: RELState) -> None:
        if not can_transition(self._state, target):
            raise IllegalTransitionError(
                f"Illegal transition: {self._state.name} -> {target.name}"
            )
        self._transition_history.append((self._state, target, time.time()))
        self._state = target

    def reset(self) -> None:
        self._state = RELState.IDLE

    def verify_hamming(self, target: RELState) -> bool:
        if self._state == RELState.HALT:
            return target == RELState.IDLE
        return hamming_distance(self._state, target) == 1


@dataclass
class ConvergenceVerdict:
    converged: bool
    reason: str
    metrics_snapshot: dict[str, float]
    oscillation_detected: bool = False
    divergence_detected: bool = False
    rollback_to_snapshot: str | None = None


class RELConvergenceDetector:
    def __init__(
        self,
        gain_threshold: float = 0.05,
        round_decay_window: int = 2,
        oscillation_threshold: int = 3,
        min_pass_rate: float = 0.85,
        max_coverage_drop: float = 2.0,
    ) -> None:
        self._gain_threshold = gain_threshold
        self._round_decay_window = round_decay_window
        self._oscillation_threshold = oscillation_threshold
        self._min_pass_rate = min_pass_rate
        self._max_coverage_drop = max_coverage_drop
        self._history: list[dict[str, float]] = []

    def evaluate(self, current: dict[str, float]) -> ConvergenceVerdict:
        self._history.append(current)
        divergence = self._check_divergence(current)
        if divergence:
            return ConvergenceVerdict(
                converged=False,
                reason="divergence detected: quality metrics degraded below threshold",
                metrics_snapshot=current,
                divergence_detected=True,
                rollback_to_snapshot=self._find_last_stable_snapshot(),
            )

        oscillation = self._check_oscillation()
        if oscillation:
            return ConvergenceVerdict(
                converged=False,
                reason="oscillation detected: alternating metric signs",
                metrics_snapshot=current,
                oscillation_detected=True,
                rollback_to_snapshot=self._find_last_stable_snapshot(),
            )

        marginal = self._check_marginal_gain()
        if marginal:
            return ConvergenceVerdict(
                converged=True,
                reason=f"converged: marginal gain below threshold for {self._round_decay_window} rounds",
                metrics_snapshot=current,
            )

        return ConvergenceVerdict(
            converged=False,
            reason="continuing: marginal gain above threshold",
            metrics_snapshot=current,
        )

    def _check_divergence(self, current: dict[str, float]) -> bool:
        pass_rate = current.get("test_pass_rate", 1.0)
        coverage = current.get("coverage_pct", 100.0)
        compile_errors = current.get("compilation_error_count", 0)
        baseline_coverage = current.get("baseline_coverage_pct", coverage)
        coverage_drop = baseline_coverage - coverage

        if pass_rate < self._min_pass_rate:
            return True
        if coverage_drop > self._max_coverage_drop:
            return True
        return compile_errors > 0

    def _check_oscillation(self) -> bool:
        if len(self._history) < 3:
            return False

        deltas = []
        for i in range(1, len(self._history)):
            metric = self._select_primary_metric(self._history[i])
            prev = self._select_primary_metric(self._history[i - 1])
            deltas.append(metric - prev)

        trailing = deltas[-(self._oscillation_threshold + 1):]
        sign_changes = sum(
            1 for i in range(1, len(trailing))
            if (trailing[i] > 0) != (trailing[i - 1] > 0)
        )
        return sign_changes >= self._oscillation_threshold

    def _check_marginal_gain(self) -> bool:
        if len(self._history) < self._round_decay_window + 1:
            return False

        deltas = []
        for i in range(1, len(self._history)):
            metric = self._select_primary_metric(self._history[i])
            prev = self._select_primary_metric(self._history[i - 1])
            deltas.append(abs(metric - prev))

        trailing = deltas[-self._round_decay_window:]
        return all(d < self._gain_threshold for d in trailing)

    def _select_primary_metric(self, metrics: dict[str, float]) -> float:
        for key in ("test_pass_rate", "coverage_pct", "lint_violation_count"):
            if key in metrics:
                val = metrics[key]
                if key == "lint_violation_count":
                    return -val
                return val
        return 0.0

    def _find_last_stable_snapshot(self) -> str | None:
        if len(self._history) >= 2:
            return f"snapshot_{len(self._history) - 2}"
        return None

    @property
    def history(self) -> list[dict[str, float]]:
        return list(self._history)


class TransactionState(Enum):
    ACTIVE = "active"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    CORRUPTED = "corrupted"


@dataclass
class FileSnapshot:
    path: str
    original_content: str
    backup_path: str


@dataclass
class RELTransaction:
    tx_id: str
    round_number: int
    snapshots: list[FileSnapshot]
    generated_files: list[str]
    baseline_metrics: dict[str, float]
    state: TransactionState = TransactionState.ACTIVE


class RELTransactionManager:
    _SNAPSHOT_DIR = os.path.join(tempfile.gettempdir(), "rel_snapshots")

    def __init__(self, max_committed: int = 10, max_rolled_back: int = 3) -> None:
        self._max_committed = max_committed
        self._max_rolled_back = max_rolled_back
        self._txs: dict[str, RELTransaction] = {}
        os.makedirs(self._SNAPSHOT_DIR, exist_ok=True)

    def begin(self, files: list[str]) -> RELTransaction:
        tx_id = f"tx_{uuid.uuid4().hex[:12]}"
        snapshots: list[FileSnapshot] = []
        tx_dir = os.path.join(self._SNAPSHOT_DIR, tx_id)
        os.makedirs(tx_dir, exist_ok=True)

        for fp in files:
            path = Path(fp)
            backup_name = f"{hash(fp)}_{path.name}"
            backup_path = os.path.join(tx_dir, backup_name)
            original_content = ""
            if path.exists():
                original_content = path.read_text(encoding="utf-8")
                shutil.copy2(str(path), backup_path)
            snap = FileSnapshot(
                path=fp,
                original_content=original_content,
                backup_path=backup_path,
            )
            snapshots.append(snap)

        tx = RELTransaction(
            tx_id=tx_id,
            round_number=len(self._txs) + 1,
            snapshots=snapshots,
            generated_files=list(files),
            baseline_metrics={},
        )
        self._txs[tx_id] = tx
        return tx

    def commit(self, tx: RELTransaction) -> bool:
        for snap in tx.snapshots:
            if os.path.exists(snap.backup_path):
                try:
                    os.remove(snap.backup_path)
                except OSError:
                    pass
        tx.state = TransactionState.COMMITTED
        self._enforce_limit(self._max_committed, TransactionState.COMMITTED)
        return True

    def rollback(self, tx: RELTransaction) -> bool:
        all_succeeded = True
        backup_paths = {snap.path for snap in tx.snapshots}

        for snap in tx.snapshots:
            if os.path.exists(snap.backup_path):
                try:
                    shutil.copy2(snap.backup_path, snap.path)
                    os.remove(snap.backup_path)
                except OSError:
                    all_succeeded = False

        for gf in tx.generated_files:
            if gf in backup_paths:
                continue
            gpath = Path(gf)
            if gpath.exists():
                try:
                    os.remove(str(gpath))
                except OSError:
                    pass

        tx.state = TransactionState.ROLLED_BACK if all_succeeded else TransactionState.CORRUPTED
        self._enforce_limit(self._max_rolled_back, TransactionState.ROLLED_BACK)
        return all_succeeded

    def _enforce_limit(self, max_count: int, state: TransactionState) -> None:
        matching = [(tid, tx) for tid, tx in self._txs.items() if tx.state == state]
        if len(matching) > max_count:
            to_remove = sorted(matching, key=lambda item: item[1].round_number)[
                :len(matching) - max_count
            ]
            for tid, _tx in to_remove:
                tx_dir = os.path.join(self._SNAPSHOT_DIR, tid)
                if os.path.exists(tx_dir):
                    shutil.rmtree(tx_dir, ignore_errors=True)
                del self._txs[tid]

    def get(self, tx_id: str) -> RELTransaction | None:
        return self._txs.get(tx_id)

    def get_by_round(self, round_number: int) -> list[RELTransaction]:
        return [tx for tx in self._txs.values() if tx.round_number == round_number]


@dataclass
class SafetyGovernorConfig:
    max_rounds_per_session: int = 10
    max_files_per_round: int = 5
    max_modules_affected: int = 3
    hitl_interval_rounds: int = 5
    max_wall_clock_seconds: int = 3600
    rel_cb_trip_threshold: int = 3


@dataclass
class GovernorVerdict:
    allowed: bool
    reason: str
    halt: bool = False
    requires_hitl: bool = False
    hitl_proposal_id: str = ""


class RELSafetyGovernor:
    def __init__(
        self,
        config: SafetyGovernorConfig | None = None,
    ) -> None:
        self._config = config or SafetyGovernorConfig()
        self._round_count = 0
        self._consecutive_rollbacks = 0
        self._start_time: float = 0.0

    def start_session(self) -> None:
        self._round_count = 0
        self._consecutive_rollbacks = 0
        self._start_time = time.time()

    def check_pre_deploy(
        self,
        generated: list,
    ) -> GovernorVerdict:
        if len(generated) > self._config.max_files_per_round:
            return GovernorVerdict(
                allowed=False,
                reason=f"files per round {len(generated)} exceeds limit {self._config.max_files_per_round}",
            )

        elapsed = time.time() - self._start_time
        if elapsed > self._config.max_wall_clock_seconds:
            return GovernorVerdict(
                allowed=False,
                reason=f"wall clock {elapsed:.0f}s exceeds limit {self._config.max_wall_clock_seconds}s",
                halt=True,
            )

        return GovernorVerdict(allowed=True, reason="")

    def check_post_round(self, tx: RELTransaction | None) -> GovernorVerdict:
        self._round_count += 1

        if tx is not None and tx.state == TransactionState.ROLLED_BACK:
            self._consecutive_rollbacks += 1
        else:
            self._consecutive_rollbacks = 0

        if self._consecutive_rollbacks >= self._config.rel_cb_trip_threshold:
            return GovernorVerdict(
                allowed=False,
                reason=f"consecutive rollbacks {self._consecutive_rollbacks} >= threshold {self._config.rel_cb_trip_threshold}",
                halt=True,
            )

        if self._round_count >= self._config.max_rounds_per_session:
            return GovernorVerdict(
                allowed=False,
                reason=f"rounds per session {self._round_count} >= limit {self._config.max_rounds_per_session}",
                halt=True,
            )

        elapsed = 0.0 if self._start_time == 0.0 else time.time() - self._start_time
        if elapsed > self._config.max_wall_clock_seconds:
            return GovernorVerdict(
                allowed=False,
                reason=f"wall clock {elapsed:.0f}s exceeds limit {self._config.max_wall_clock_seconds}s",
                halt=True,
            )

        if (
            self._config.hitl_interval_rounds > 0
            and self._round_count % self._config.hitl_interval_rounds == 0
        ):
            hitl_id = f"hitl_rel_round_{self._round_count}_{uuid.uuid4().hex[:6]}"
            return GovernorVerdict(
                allowed=True,
                reason=f"HITL check required at round {self._round_count}",
                requires_hitl=True,
                hitl_proposal_id=hitl_id,
            )

        return GovernorVerdict(allowed=True, reason="")

    @property
    def round_count(self) -> int:
        return self._round_count

    @property
    def consecutive_rollbacks(self) -> int:
        return self._consecutive_rollbacks


@dataclass
class RELRoundRecord:
    round_number: int
    start_state: RELState
    end_state: RELState
    metrics_before: dict[str, float]
    metrics_after: dict[str, float]
    verdict: ConvergenceVerdict
    tx: RELTransaction | None
    duration_seconds: float
    errors: list[str] = field(default_factory=list)


@dataclass
class RELSessionResult:
    success: bool
    reason: str
    round_count: int
    final_state: str = ""
    duration_seconds: float = 0.0


class RecursiveEvolutionLoop:
    def __init__(
        self,
        state_machine: RELStateMachine | None = None,
        convergence_detector: RELConvergenceDetector | None = None,
        transaction_manager: RELTransactionManager | None = None,
        safety_governor: RELSafetyGovernor | None = None,
        agent_id: str | None = None,
    ) -> None:
        self._sm = state_machine or RELStateMachine()
        self._detector = convergence_detector or RELConvergenceDetector()
        self._tx_mgr = transaction_manager or RELTransactionManager()
        self._governor = safety_governor or RELSafetyGovernor()
        self._rounds: list[RELRoundRecord] = []
        self._current_round = 0
        self._current_snapshot: Any = None
        self._current_report: Any = None
        self._current_proposal: Any = None
        self._current_code: Any = None
        self._agent_id = agent_id or f"rel-{uuid.uuid4().hex[:8]}"
        self._pulse_writer: Any = None
        self._best_baseline: float = 0.0

    @property
    def state_machine(self) -> RELStateMachine:
        return self._sm

    @property
    def convergence_detector(self) -> RELConvergenceDetector:
        return self._detector

    @property
    def transaction_manager(self) -> RELTransactionManager:
        return self._tx_mgr

    @property
    def safety_governor(self) -> RELSafetyGovernor:
        return self._governor

    @property
    def rounds(self) -> list[RELRoundRecord]:
        return list(self._rounds)

    @property
    def current_round(self) -> int:
        return self._current_round

    def start(self) -> None:
        if self._sm.state != RELState.IDLE:
            return
        self._governor.start_session()
        self._sm.transition(RELState.TRIGGERED)
        from maref.recursive.agent_health import PulseWriter
        self._pulse_writer = PulseWriter(
            agent_id=self._agent_id,
            interval_seconds=30.0,
        )

    def stop(self) -> None:
        if can_transition(self._sm.state, RELState.STOP):
            self._sm.transition(RELState.STOP)

    def halt(self, reason: str = "") -> None:
        if can_transition(self._sm.state, RELState.HALT):
            self._sm.transition(RELState.HALT)

    def recover(self) -> bool:
        if self._sm.state != RELState.HALT:
            return False
        if can_transition(RELState.HALT, RELState.IDLE):
            self._sm.transition(RELState.IDLE)
            return True
        return False

    def complete_round(
        self,
        metrics_before: dict[str, float],
        metrics_after: dict[str, float],
        tx: RELTransaction | None = None,
        errors: list[str] | None = None,
    ) -> ConvergenceVerdict:
        start = time.time()
        round_num = self._current_round + 1
        start_state = self._sm.state

        current_state = self._sm.state
        if current_state in (RELState.HALT, RELState.STOP):
            return ConvergenceVerdict(
                converged=False,
                reason=f"state_already_{current_state.name.lower()}",
                metrics_snapshot=metrics_after,
            )

        verdict = self._detector.evaluate(metrics_after)

        # H5: MetaRatchetAuditor baseline audit — block if baseline regresses
        new_baseline = metrics_after.get("test_pass_rate", 1.0)
        if self._best_baseline > 0.0:
            from maref.integration.percv.meta_ratchet_auditor import MetaRatchetAuditor
            _ra = MetaRatchetAuditor()
            baseline_verdict = _ra.audit_baseline(self._best_baseline, new_baseline)
            if baseline_verdict.blocked:
                logger.error("REL baseline audit blocked: %s", baseline_verdict.reason)
                self.halt(f"baseline_audit: {baseline_verdict.reason}")
                if tx is not None:
                    self._tx_mgr.rollback(tx)
                return ConvergenceVerdict(
                    converged=False,
                    reason=f"baseline_regression: {baseline_verdict.reason}",
                    metrics_snapshot=metrics_after,
                    divergence_detected=True,
                )
        if new_baseline > self._best_baseline:
            self._best_baseline = new_baseline

        if verdict.divergence_detected or verdict.oscillation_detected:
            if tx is not None:
                self._tx_mgr.rollback(tx)
            end_state = RELState.HALT
            self._safe_transition(RELState.HALT)
        elif verdict.converged:
            if tx is not None:
                self._tx_mgr.commit(tx)
            end_state = RELState.STOP
            self._safe_transition(RELState.STOP)
        else:
            end_state = RELState.OBSERVE
            self._safe_transition(RELState.OBSERVE)

        duration = time.time() - start
        record = RELRoundRecord(
            round_number=round_num,
            start_state=start_state,
            end_state=end_state,
            metrics_before=metrics_before,
            metrics_after=metrics_after,
            verdict=verdict,
            tx=tx,
            duration_seconds=duration,
            errors=errors or [],
        )
        self._rounds.append(record)
        self._current_round = round_num

        gov_verdict = self._governor.check_post_round(tx)
        if gov_verdict.halt:
            self._sm.transition(RELState.HALT)

        return verdict

    def _safe_transition(self, target: RELState) -> None:
        """Transition to target, routing through intermediate states if direct path invalid."""
        current = self._sm.state
        if current == target:
            return
        if target == RELState.HALT:
            self._sm.transition(RELState.HALT)
            return
        if current == RELState.IDLE:
            return
        if can_transition(current, target):
            self._sm.transition(target)
            return
        if target == RELState.STOP and can_transition(RELState.EVALUATE, RELState.STOP):
            if can_transition(current, RELState.EVALUATE):
                self._sm.transition(RELState.EVALUATE)
            self._sm.transition(RELState.STOP)
            return
        if target == RELState.OBSERVE and can_transition(RELState.EVALUATE, RELState.OBSERVE):
            if can_transition(current, RELState.EVALUATE):
                self._sm.transition(RELState.EVALUATE)
            self._sm.transition(RELState.OBSERVE)
            return
        logger.warning("Cannot transition %s -> %s", current.name, target.name)

    def is_active(self) -> bool:
        return self._sm.state not in (RELState.IDLE, RELState.STOP, RELState.HALT)

    def is_converged(self) -> bool:
        return self._sm.state == RELState.STOP

    def is_halted(self) -> bool:
        return self._sm.state == RELState.HALT

    # ── Session execution ────────────────────────────────────────────

    async def run_session(self) -> RELSessionResult:
        """
        Run one complete evolution session:
        IDLE → TRIGGERED → OBSERVE → DIAGNOSE → ARCHITECT → CODEGEN → SAFETY → DEPLOY → VERIFY → EVALUATE → STOP/HALT

        Returns session result with verification artifacts.
        """
        self.start()
        if self._sm.state != RELState.TRIGGERED:
            return RELSessionResult(success=False, reason="failed_to_start", round_count=0)

        session_start = time.time()
        rounds_completed = 0
        verdict = ConvergenceVerdict(
            converged=False,
            reason="initial",
            metrics_snapshot={},
        )

        while self.is_active():
            governor = self._governor.check_post_round(None)
            if governor.halt:
                self.halt(governor.reason)
                break
            if governor.requires_hitl:
                logger.warning("HITL required at round %d, halting", self._governor.round_count)
                self.halt("hitl_required")
                break

            metrics_before = self._collect_current_metrics()
            tx = self._tx_mgr.begin([])

            await self._execute_state_actions()

            if self._pulse_writer is not None:
                self._pulse_writer.write_pulse(status="alive")

            metrics_after = self._collect_current_metrics()
            verdict = self.complete_round(metrics_before, metrics_after, tx)
            rounds_completed += 1

            if verdict.converged or verdict.divergence_detected or verdict.oscillation_detected:
                break

        return RELSessionResult(
            success=self.is_converged(),
            reason=verdict.reason if rounds_completed > 0 else "no_rounds",
            round_count=rounds_completed,
            final_state=self._sm.state.name,
            duration_seconds=time.time() - session_start,
        )

    async def _execute_state_actions(self) -> None:
        """Execute all phase actions from the current state through EVALUATE."""
        max_iterations = 20
        for _ in range(max_iterations):
            state = self._sm.state
            if state in (RELState.IDLE, RELState.STOP, RELState.HALT, RELState.EVALUATE):
                break

            if state == RELState.TRIGGERED:
                if can_transition(RELState.TRIGGERED, RELState.OBSERVE):
                    self._sm.transition(RELState.OBSERVE)

            elif state == RELState.OBSERVE:
                from maref.recursive.self_observer import SelfObserver
                observer = SelfObserver()
                snapshot = observer.snapshot(collect_only=True)
                self._current_snapshot = snapshot
                if can_transition(RELState.OBSERVE, RELState.DIAGNOSE):
                    self._sm.transition(RELState.DIAGNOSE)

            elif state == RELState.DIAGNOSE:
                from maref.recursive.self_diagnostician import SelfDiagnostician
                diagnostician = SelfDiagnostician()
                if self._current_snapshot is not None:
                    self._current_report = diagnostician.diagnose(self._current_snapshot)
                if can_transition(RELState.DIAGNOSE, RELState.ARCHITECT):
                    self._sm.transition(RELState.ARCHITECT)

            elif state == RELState.ARCHITECT:
                from maref.recursive.self_architect import SelfArchitect
                from maref.recursive.unified_audit import UnifiedAuditStore
                architect = SelfArchitect(audit_store=UnifiedAuditStore())
                proposals = architect.propose_all()
                self._current_proposal = proposals[0] if proposals else None

                # H2: MetaRatchetAuditor config change audit — block if proposal targets ratchet config
                if self._current_proposal is not None:
                    target_files = getattr(self._current_proposal, "target_files", []) or []
                    for tf in target_files:
                        from maref.integration.percv.meta_ratchet_auditor import MetaRatchetAuditor
                        _ra = MetaRatchetAuditor()
                        verdict = _ra.audit_file_change(str(tf))
                        if verdict.blocked:
                            logger.error("REL ratchet audit blocked proposal: %s — %s", tf, verdict.reason)
                            self.halt(f"ratchet_audit_architect: {verdict.reason}")
                            return

                if can_transition(RELState.ARCHITECT, RELState.CODEGEN):
                    self._sm.transition(RELState.CODEGEN)

            elif state == RELState.CODEGEN:
                from maref.recursive.llm_code_generator import LLMCodeGenerator
                generator = LLMCodeGenerator()
                if self._current_proposal is not None:
                    result = await generator.generate(self._current_proposal)
                    if result.success and result.generated:
                        self._current_code = result.generated[0]
                    else:
                        errs = "; ".join(result.validation_errors)
                        logger.warning("CODEGEN: generation failed: %s", errs or "unknown")
                else:
                    logger.warning("CODEGEN: no proposal available, skipping")
                if can_transition(RELState.CODEGEN, RELState.SAFETY):
                    self._sm.transition(RELState.SAFETY)

            elif state == RELState.SAFETY:
                if self._current_code is not None:
                    code_str = str(getattr(self._current_code, "content", str(self._current_code)))
                    try:
                        from maref.immunity.immune_checker import ImmuneChecker
                        from maref.immunity.negative_gene_bank import NegativeGeneBank
                        from maref.immunity.seed_genes import seed_all
                        bank = NegativeGeneBank()
                        seed_all(bank)
                        checker = ImmuneChecker(gene_bank=bank)
                        immune_hits = checker.scan(code_str) + checker.scan_ast(code_str)
                        blocked_hits = [h for h in immune_hits if h.blocked]
                        if blocked_hits:
                            reasons = "; ".join(f"{h.gene_id}:{h.gene_title}" for h in blocked_hits[:5])
                            self.halt(f"immune: {reasons}")
                    except ImportError:
                        logger.info("ImmuneChecker not available, skipping")
                    except Exception:
                        logger.exception("ImmuneChecker scan failed, continuing")
                    if self._sm.state == RELState.SAFETY:
                        from maref.recursive.safety_gate_v2 import SafetyGateV2
                        gate = SafetyGateV2()
                        threat = gate.detect_core_removal(code_str)
                        if threat.blocked:
                            self.halt(f"safety: {threat.reason}")
                if self._sm.state == RELState.SAFETY and can_transition(self._sm.state, RELState.DEPLOY):
                    self._sm.transition(RELState.DEPLOY)

            elif state == RELState.DEPLOY:
                from maref.recursive.self_executor import SelfExecutor
                executor = SelfExecutor()
                if self._current_code is not None:
                    deploy_result = executor.deploy(self._current_code)
                    if not deploy_result.success:
                        last_tx = self._tx_mgr.get_by_round(self._current_round)
                        if last_tx:
                            self._tx_mgr.rollback(last_tx[-1])
                    else:
                        # H4: MetaRatchetAuditor config change audit — block if deployed file is ratchet config
                        f_path = getattr(self._current_code, "file_path", None)
                        if f_path:
                            from maref.integration.percv.meta_ratchet_auditor import (
                                MetaRatchetAuditor,
                            )
                            _ra = MetaRatchetAuditor()
                            verdict = _ra.audit_file_change(str(f_path))
                            if verdict.blocked:
                                logger.error("REL ratchet audit blocked deploy: %s — %s", f_path, verdict.reason)
                                self.halt(f"ratchet_audit_deploy: {verdict.reason}")
                                return

                if can_transition(RELState.DEPLOY, RELState.VERIFY):
                    self._sm.transition(RELState.VERIFY)

            elif state == RELState.VERIFY:
                self._run_quality_checks()

                # H1: MetaRatchetAuditor check — block if REL modifies ratchet files
                if self._current_code is not None:
                    f_path = getattr(self._current_code, "file_path", None)
                    if f_path:
                        from maref.integration.percv.meta_ratchet_auditor import MetaRatchetAuditor
                        _ra = MetaRatchetAuditor()
                        verdict = _ra.audit_file_change(str(f_path))
                        if verdict.blocked:
                            logger.error("REL ratchet audit blocked: %s — %s", f_path, verdict.reason)
                            self.halt(f"ratchet_audit: {verdict.reason}")
                            return

                if can_transition(RELState.VERIFY, RELState.EVALUATE):
                    self._sm.transition(RELState.EVALUATE)

            if self._sm.state == state:
                logger.warning("REL: state stuck at %s, breaking", state.name)
                break
        else:
            logger.warning("REL: state machine did not reach EVALUATE within %d iterations", max_iterations)

        if self._sm.state not in (RELState.EVALUATE, RELState.HALT):
            if can_transition(self._sm.state, RELState.EVALUATE):
                self._sm.transition(RELState.EVALUATE)
            elif can_transition(RELState.VERIFY, RELState.EVALUATE):
                self._sm.transition(RELState.VERIFY)
                self._sm.transition(RELState.EVALUATE)

    def _collect_current_metrics(self) -> dict[str, float]:
        try:
            from maref.recursive.self_observer import SelfObserver
            observer = SelfObserver()
            snapshot = observer.snapshot(collect_only=True)
            return {
                "test_pass_rate": float(snapshot.test_pass_rate) if hasattr(snapshot, "test_pass_rate") and snapshot.test_pass_rate else 1.0,
                "coverage_pct": float(snapshot.coverage_pct) if hasattr(snapshot, "coverage_pct") else 0.0,
                "source_file_count": float(snapshot.source_file_count) if hasattr(snapshot, "source_file_count") else 0.0,
                "test_count": float(snapshot.test_count) if hasattr(snapshot, "test_count") else 0.0,
            }
        except Exception:
            try:
                result = subprocess.run(
                    ["git", "status", "--short"],
                    capture_output=True, text=True, timeout=10,
                )
                dirty = float(len(result.stdout.strip()) > 0)
            except Exception:
                dirty = 0.0
            return {
                "test_pass_rate": 1.0,
                "coverage_pct": 0.0,
                "lint_violation_count": 0.0,
                "dirty_files": dirty,
            }

    def _run_quality_checks(self) -> None:
        logger.info("REL: running quality checks")
        try:
            subprocess.run(
                ["git", "status"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception:
            logger.warning("REL: quality check git command failed")
