"""Phase 2.5 — three-process federated saga E2E + audit chain merge.

Runs a cross-organization saga across **three real processes**:

1. **发起方 (org-alpha, initiator)** — runs a federation HTTP server plus an
   in-process :class:`FederatedSagaOrchestrator`. Executing the saga:
   policy gating → delegation of the executor agent over HTTP →
   trust evaluation → cross-process task execution.
2. **执行方 (org-beta, executor)** — runs a federation HTTP server; receives
   the delegated agent registration and executes the task, recording its own
   audit log + Merkle evidence chain.
3. **审计方 (org-gamma, auditor)** — owns a SQLite-backed
   :class:`FederatedAuditStore` (merging both orgs' Merkle roots into one
   federated root) and an :class:`AuditReconciler` (comparing the executor's
   audit log against a replica fetched over HTTP).

Verification points:

- The saga completes with 3 steps, policy decisions, and trust snapshots.
- The executor process received the delegation and executed the task.
- The auditor merges both Merkle roots; inclusion proofs verify **offline**
  with only the federated root hash.
- Cross-process audit reconciliation reports consistency.

Also covers the Phase 2.5 cascade linkage: :class:`FederationHealthMonitor`
wired to :class:`FederationCascadeBreaker` — sustained silence isolates an
agent and degrades its dependents; a recovery probe restores them exactly.
"""

from __future__ import annotations

import multiprocessing
import socket
import time
from pathlib import Path
from typing import Any

import httpx
import uvicorn

from maref.eivl.federated_merkle import FederatedProof
from maref.federation.cascade_breaker import (
    CascadeStatus,
    FederationCascadeBreaker,
)
from maref.federation.federation_http import create_federation_app
from maref.federation.health_monitor import FederationHealthMonitor

HEALTH_PATH = "/api/v1/federation/health"


# ── Process-launch helpers ───────────────────────────────────────────────


def _free_port() -> int:
    """Return a currently-free TCP port on loopback."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_until_healthy(base_url: str, timeout: float = 20.0) -> None:
    """Poll the health endpoint until the server responds 200."""
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = httpx.get(f"{base_url}{HEALTH_PATH}", timeout=1.0)
            if response.status_code == 200:
                return
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(0.05)
    raise RuntimeError(f"server {base_url} did not become healthy: {last_error}")


def _start_server_process(
    kind: str, workdir: Path, executor_url: str = ""
) -> tuple[multiprocessing.Process, str]:
    """Start one of the three federation processes; return (proc, base_url)."""
    port = _free_port()
    if kind == "initiator":
        target = _run_initiator_process
        args = (port, workdir, executor_url)
    elif kind == "executor":
        target = _run_executor_process
        args = (port, workdir)
    else:  # auditor
        target = _run_auditor_process
        args = (port, workdir)
    proc = multiprocessing.Process(target=target, args=args, daemon=True)
    proc.start()
    base_url = f"http://127.0.0.1:{port}"
    _wait_until_healthy(base_url)
    return proc, base_url


# ── Child-process entry points ───────────────────────────────────────────


def _run_initiator_process(port: int, workdir: Path, executor_url: str) -> None:
    """发起方: federation server + FederatedSagaOrchestrator + Merkle chain."""
    from fastapi import APIRouter

    from maref.eivl.merkle_auditor import AuditChainIntegrator
    from maref.federation import create_default_federation
    from maref.federation.policy_subscriber import FederatedPolicySubscriber
    from maref.governance.audit import AuditLogger
    from maref.identity.aic_adapter import AIC
    from maref.integration.acs_parser import ACSParser
    from maref.recursive.federated_saga_orchestrator import (
        FederatedSagaOrchestrator,
    )
    from maref.recursive.saga_orchestrator import Saga, SagaStep, StepResult

    audit_logger = AuditLogger(workdir / "org-alpha" / "audit.jsonl", hmac_key=b"e2e-key")
    platform = create_default_federation(server_id="org-alpha", audit_logger=audit_logger)
    chain = AuditChainIntegrator()
    orchestrator = FederatedSagaOrchestrator(platform)
    # Explicitly allow the saga steps (v0.47 S3 fail-closed: no rule → deny).
    from maref.federation.policy import PolicyDecision

    for _action in ("delegate_to_executor", "assess_trust", "execute_task"):
        orchestrator.policy_engine.add_federation_rule(
            rule_id=f"e2e-allow-{_action}",
            action=_action,
            decision=PolicyDecision.ALLOW,
        )
    subscriber = FederatedPolicySubscriber(
        local_engine=platform.policy_engine, local_org="org-alpha"
    )
    app = create_federation_app(
        platform.gateway, platform.trust_engine, subscriber, server_id="org-alpha"
    )
    router = APIRouter()

    @router.post("/api/v1/federation/saga/execute")
    def saga_execute(body: dict[str, Any]) -> dict[str, Any]:
        """Run the cross-org saga: delegate → trust → execute over HTTP."""
        task_id = body.get("task_id", "task-001")
        acs_doc = (
            ACSParser()
            .from_maref_capabilities(
                aic=AIC.generate().aic_string,
                agent_name="e2e-executor-agent",
                agent_description="phase 2.5 federated executor",
                capabilities=["execute_task"],
                endpoint_url=executor_url,
                provider_organization="org-beta",
            )
            .to_dict()
        )

        agent_did: dict[str, str] = {}

        def step_delegate(ctx: dict[str, Any]) -> StepResult:
            with httpx.Client(base_url=executor_url, timeout=10.0) as client:
                resp = client.post(
                    "/api/v1/federation/gateway/register",
                    json={
                        "aic_string": acs_doc["aic"],
                        "acs_document": acs_doc,
                        "endpoint_url": executor_url,
                        "protocol": "a2a",
                    },
                )
                resp.raise_for_status()
                body = resp.json()
            did = body["did_string"]
            agent_did["did"] = did
            chain.record_delegation("org-alpha", did, ["execute_task"])
            ctx["delegate_agent_did"] = did
            return StepResult(
                step_id="delegate",
                success=True,
                data={
                    "did_string": did,
                    "aic_string": body["aic_string"],
                    # Convention: surface the delegated agent DID so the
                    # orchestrator records a trust snapshot for it.
                    "delegate_agent_did": did,
                },
            )

        def step_trust(ctx: dict[str, Any]) -> StepResult:
            did = ctx["delegate_agent_did"]
            score = platform.trust_engine.assess(did)
            chain.record_trust_evaluation(did, score.effective_score, [], evaluator="org-alpha")
            return StepResult(
                step_id="trust_evaluate",
                success=True,
                data={"trust_score": round(score.effective_score, 2)},
            )

        def step_execute(ctx: dict[str, Any]) -> StepResult:
            did = ctx["delegate_agent_did"]
            with httpx.Client(base_url=executor_url, timeout=10.0) as client:
                resp = client.post(
                    "/api/v1/federation/exec/execute",
                    json={
                        "task_id": task_id,
                        "agent_did": did,
                        "delegator_org": "org-alpha",
                    },
                )
                resp.raise_for_status()
                exec_body = resp.json()
            entry = audit_logger.log(
                event_type="federation_saga_executed",
                actor="org-alpha",
                action="execute_saga_step",
                details=f"task {task_id} delegated to {did}",
                metadata={
                    "task_id": task_id,
                    "agent_did": did,
                    "executor_result": exec_body,
                },
            )
            chain.record_audit_entry(entry)
            return StepResult(
                step_id="execute_task",
                success=True,
                data={"executor_result": exec_body},
            )

        saga = Saga(saga_id=f"saga-{task_id}", description="cross-org task")
        saga.add_step(
            SagaStep(
                step_id="delegate",
                description="delegate_to_executor",
                execute_fn=step_delegate,
            )
        )
        saga.add_step(
            SagaStep(
                step_id="trust_evaluate",
                description="assess_trust",
                execute_fn=step_trust,
            )
        )
        saga.add_step(
            SagaStep(
                step_id="execute_task",
                description="execute_task",
                execute_fn=step_execute,
            )
        )
        result = orchestrator.execute(
            saga,
            initial_context={
                "requesting_org": "org-alpha",
                "reviewing_org": "org-alpha",
            },
        )
        out = result.to_dict()
        out["is_success"] = result.is_success
        out["merkle_root"] = chain.merkle.get_root_hash()
        out["tree_info"] = chain.merkle.get_tree_info()
        out["agent_did"] = agent_did.get("did", "")
        return out

    @router.get("/api/v1/federation/saga/merkle-root")
    def saga_merkle_root() -> dict[str, Any]:
        return {
            "merkle_root": chain.merkle.get_root_hash(),
            "tree_info": chain.merkle.get_tree_info(),
        }

    app.include_router(router)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def _run_executor_process(port: int, workdir: Path) -> None:
    """执行方: federation server + task execution + own Merkle chain."""
    from fastapi import APIRouter

    from maref.eivl.merkle_auditor import AuditChainIntegrator
    from maref.federation import create_default_federation
    from maref.federation.policy_subscriber import FederatedPolicySubscriber
    from maref.governance.audit import AuditLogger

    audit_logger = AuditLogger(workdir / "org-beta" / "audit.jsonl", hmac_key=b"e2e-key")
    platform = create_default_federation(server_id="org-beta", audit_logger=audit_logger)
    chain = AuditChainIntegrator()
    subscriber = FederatedPolicySubscriber(
        local_engine=platform.policy_engine, local_org="org-beta"
    )
    app = create_federation_app(
        platform.gateway, platform.trust_engine, subscriber, server_id="org-beta"
    )
    executions: list[dict[str, Any]] = []
    router = APIRouter()

    @router.post("/api/v1/federation/exec/execute")
    def exec_execute(body: dict[str, Any]) -> dict[str, Any]:
        task_id = body["task_id"]
        agent_did = body.get("agent_did", "")
        delegator_org = body.get("delegator_org", "")
        entry = audit_logger.log(
            event_type="federation_task_executed",
            actor="org-beta",
            action="execute_task",
            details=f"executed {task_id} for {delegator_org}",
            metadata={"task_id": task_id, "agent_did": agent_did, "status": "ok"},
        )
        leaf_hash = chain.record_audit_entry(entry)
        executions.append(
            {
                "task_id": task_id,
                "agent_did": agent_did,
                "delegator_org": delegator_org,
                "merkle_leaf": leaf_hash,
            }
        )
        return {
            "task_id": task_id,
            "status": "ok",
            "executor_org": "org-beta",
            "merkle_leaf": leaf_hash,
        }

    @router.get("/api/v1/federation/exec/merkle-root")
    def exec_merkle_root() -> dict[str, Any]:
        return {
            "merkle_root": chain.merkle.get_root_hash(),
            "tree_info": chain.merkle.get_tree_info(),
        }

    @router.get("/api/v1/federation/exec/audit-log-raw")
    def exec_audit_log_raw() -> dict[str, Any]:
        path = workdir / "org-beta" / "audit.jsonl"
        return {"content": path.read_text() if path.exists() else ""}

    @router.get("/api/v1/federation/exec/executions")
    def exec_executions() -> dict[str, Any]:
        return {"executions": list(executions)}

    app.include_router(router)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def _run_auditor_process(port: int, workdir: Path) -> None:
    """审计方: FederatedAuditStore (SQLite) + AuditReconciler over HTTP."""
    from fastapi import APIRouter, FastAPI, HTTPException

    from maref.eivl.audit_reconciler import AuditReconciler
    from maref.eivl.federated_store import FederatedAuditStore

    store = FederatedAuditStore(workdir / "federation.db")
    reconciler = AuditReconciler()
    app = FastAPI(title="MAREF Federation Auditor")
    router = APIRouter()

    @router.get("/api/v1/federation/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "server_id": "org-gamma"}

    @router.post("/api/v1/federation/audit/submit-root")
    def audit_submit_root(body: dict[str, Any]) -> dict[str, Any]:
        store.submit_root(
            org_id=body["org_id"],
            root_hash=body["root_hash"],
            tree_size=body.get("tree_size", 0),
            metadata=body.get("metadata"),
        )
        return {"accepted": True, "org_count": len(store.list_orgs())}

    @router.get("/api/v1/federation/audit/federated-root")
    def audit_federated_root() -> dict[str, Any]:
        return store.summary()

    @router.get("/api/v1/federation/audit/proof/{org_id}")
    def audit_proof(org_id: str) -> dict[str, Any]:
        proof = store.generate_proof(org_id)
        if proof is None:
            raise HTTPException(status_code=404, detail=f"no proof for {org_id}")
        return proof.to_dict()

    @router.get("/api/v1/federation/audit/reconcile")
    def audit_reconcile(executor_url: str) -> dict[str, Any]:
        """Fetch the executor's audit log over HTTP and reconcile a replica."""
        replica_path = workdir / "replicas" / "org-beta.jsonl"
        raw = httpx.get(
            f"{executor_url}/api/v1/federation/exec/audit-log-raw", timeout=10.0
        ).json()["content"]
        replica_path.parent.mkdir(parents=True, exist_ok=True)
        replica_path.write_text(raw)
        source_path = workdir / "org-beta" / "audit.jsonl"
        reconciler.add_replica("executor-source", source_path)
        reconciler.add_replica("executor-replica", replica_path)
        return reconciler.reconcile().to_dict()

    app.include_router(router)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


# ── Three-process end-to-end test ────────────────────────────────────────


def test_three_process_federation_saga(tmp_path: Path) -> None:
    """发起方 → 执行方 → 审计方: saga + Merkle merge + reconciliation."""
    workdir = tmp_path / "fed"
    executor_proc, executor_url = _start_server_process("executor", workdir)
    auditor_proc, auditor_url = _start_server_process("auditor", workdir)
    initiator_proc, initiator_url = _start_server_process(
        "initiator", workdir, executor_url=executor_url
    )
    try:
        # 1) Run the federated saga on the initiator process.
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{initiator_url}/api/v1/federation/saga/execute",
                json={"task_id": "task-cross-org-001"},
            )
            resp.raise_for_status()
            saga = resp.json()
        assert saga["state"] == "completed", saga
        assert saga["is_success"] is True
        assert saga["steps_executed"] == 3
        assert len(saga["policy_decisions"]) == 3
        assert saga["trust_assessments"], "expected trust snapshots per agent"
        agent_did = saga["agent_did"]
        assert agent_did.startswith("did:")
        assert agent_did in saga["trust_assessments"]
        initiator_root = saga["merkle_root"]
        assert initiator_root
        assert saga["tree_info"]["leaf_count"] == 3  # delegation+trust+audit

        # 2) The executor process received the delegation and executed.
        with httpx.Client(timeout=10.0) as client:
            executions = client.get(f"{executor_url}/api/v1/federation/exec/executions").json()[
                "executions"
            ]
            assert len(executions) == 1
            assert executions[0]["task_id"] == "task-cross-org-001"
            assert executions[0]["agent_did"] == agent_did
            executor_root_body = client.get(
                f"{executor_url}/api/v1/federation/exec/merkle-root"
            ).json()
        assert executor_root_body["merkle_root"]
        assert executor_root_body["tree_info"]["leaf_count"] == 1

        # 3) Auditor merges both orgs' Merkle roots into a federated root.
        with httpx.Client(timeout=10.0) as client:
            for org_id, root_hash, tree_size in (
                ("org-alpha", initiator_root, saga["tree_info"]["leaf_count"]),
                ("org-beta", executor_root_body["merkle_root"], 1),
            ):
                resp = client.post(
                    f"{auditor_url}/api/v1/federation/audit/submit-root",
                    json={
                        "org_id": org_id,
                        "root_hash": root_hash,
                        "tree_size": tree_size,
                    },
                )
                resp.raise_for_status()
            summary = client.get(f"{auditor_url}/api/v1/federation/audit/federated-root").json()
        assert summary["org_count"] == 2
        federated_root = summary["federated_root"]
        assert federated_root

        # 4) Offline audit verification: inclusion proofs need only the
        #    federated root hash — no live server.
        with httpx.Client(timeout=10.0) as client:
            proof_alpha = FederatedProof.from_dict(
                client.get(f"{auditor_url}/api/v1/federation/audit/proof/org-alpha").json()
            )
            proof_beta = FederatedProof.from_dict(
                client.get(f"{auditor_url}/api/v1/federation/audit/proof/org-beta").json()
            )
        assert proof_alpha.verify()
        assert proof_beta.verify()
        assert proof_alpha.federated_root_hash == federated_root
        assert proof_beta.federated_root_hash == federated_root
        assert proof_alpha.org_count == 2

        # 5) Cross-process audit reconciliation: the auditor fetched the
        #    executor's log over HTTP; the replica must match the source.
        with httpx.Client(timeout=10.0) as client:
            report = client.get(
                f"{auditor_url}/api/v1/federation/audit/reconcile",
                params={"executor_url": executor_url},
            ).json()
        assert report["is_consistent"] is True, report
        assert report["total_replicas"] == 2
        assert report["total_entries"]["executor-source"] >= 1
    finally:
        for proc in (initiator_proc, executor_proc, auditor_proc):
            proc.terminate()
            proc.join(timeout=10.0)


# ── Cascade breaker × health monitor linkage (Phase 2.5) ─────────────────


def test_health_monitor_drives_cascade_isolation_and_recovery() -> None:
    """Sustained silence isolates an agent and degrades its dependent;
    a recovery probe restores both exactly."""
    breaker = FederationCascadeBreaker(cooldown_seconds=0.02, max_failures=3)
    breaker.declare_dependency(dependent="agent-b", upstream="agent-a")
    monitor = FederationHealthMonitor(
        silence_timeout=0.05,
        trust_decay_per_cycle=5.0,
        cascade_breaker=breaker,
    )
    monitor.probe("agent-a")
    monitor.probe("agent-b")
    assert breaker.status("agent-a") == CascadeStatus.NOMINAL

    # agent-a stays silent across 3 check cycles → isolated + b degraded.
    # agent-b keeps heartbeating so it is never itself suspected.
    time.sleep(0.06)
    for _ in range(3):
        monitor.probe("agent-b")
        monitor.check()
    assert breaker.status("agent-a") == CascadeStatus.ISOLATED
    assert breaker.status("agent-b") == CascadeStatus.DEGRADED
    assert breaker.can_proceed("agent-a") is False  # still inside cooldown

    # Recovery probe after the cooldown → exact un-degradation.
    time.sleep(0.08)
    monitor.probe("agent-a")
    assert breaker.status("agent-a") == CascadeStatus.NOMINAL
    assert breaker.status("agent-b") == CascadeStatus.NOMINAL


def test_health_monitor_active_member_does_not_trip_cascade() -> None:
    """An active member produces no cascade failure signal."""
    breaker = FederationCascadeBreaker(max_failures=3)
    breaker.declare_dependency(dependent="agent-b", upstream="agent-a")
    monitor = FederationHealthMonitor(
        silence_timeout=0.05,
        trust_decay_per_cycle=5.0,
        cascade_breaker=breaker,
    )
    monitor.probe("agent-a")
    time.sleep(0.06)
    monitor.probe("agent-a")  # heartbeat keeps it fresh
    monitor.check()
    assert breaker.status("agent-a") == CascadeStatus.NOMINAL
    assert breaker.status("agent-b") == CascadeStatus.NOMINAL


def test_health_monitor_without_breaker_is_noop() -> None:
    """Backward compatibility: no cascade_breaker wired → unchanged behaviour."""
    monitor = FederationHealthMonitor(silence_timeout=0.05, trust_decay_per_cycle=5.0)
    monitor.probe("agent-silent")
    time.sleep(0.06)
    result = monitor.check()
    assert result.suspected >= 1
