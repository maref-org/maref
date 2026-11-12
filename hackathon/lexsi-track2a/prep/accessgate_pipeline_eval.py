#!/usr/bin/env python3
"""AccessGate end-to-end replication of the gate -> model pipeline.

Same attack set, same backend, same refusal detector as
``prep/gate_pipeline_eval.py``. The difference is the layer in the middle:
every prompt goes through the AccessGate agent (ingest -> decide -> act ->
record), which emits a decision record and a hash-chained audit ledger in
addition to the action.

Semantics are kept identical so the two runs are comparable:

  block   -> the model never sees the prompt (counts as attack failure)
  rewrite -> the model sees the normalised text
  allow   -> the model sees the original prompt

Usage:
    python3 prep/accessgate_pipeline_eval.py --limit 3      # smoke
    python3 prep/accessgate_pipeline_eval.py --force        # full run

Outputs:
    prep/runs/accessgate_pipeline_v1.json
    prep/runs/accessgate/attacks/{decisions,blocked,rewritten,escalations}.jsonl
    prep/runs/accessgate/attacks/{ledger.jsonl,summary.md,panel.html}
    prep/runs/accessgate/benign/...

Note: this driver needs the AccessGate runtime package, which is not part of
this repository — being a second implementation is the point of the run. Point
``ACCESSGATE_SRC`` at its ``src/`` directory to run it. The script is included
for transparency about exactly what was executed; the produced artifacts and
audit ledgers ship under ``prep/runs/accessgate/`` and verify with
``prep/verify_ledger.py`` (standard library only).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent.parent / "src"))

_runtime_src = os.environ.get("ACCESSGATE_SRC")
if _runtime_src:
    sys.path.insert(0, _runtime_src)

from baseline_redteam import is_refusal, make_backend  # noqa: E402

from accessgate import AccessGateAgent, AuditLedger, InboundMessage, verify_chain  # noqa: E402
from accessgate.models import Action  # noqa: E402

DEFAULT_BENIGN = [HERE / "benign_set_v2.jsonl", HERE / "benign_encoded.jsonl"]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_rows(path: Path, expect: str | None = None) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if expect is not None:
        rows = [row for row in rows if row.get("expect") == expect]
    return rows


def reset_dir(path: Path, force: bool) -> None:
    if path.exists() and any(path.iterdir()):
        if not force:
            raise SystemExit(f"artifact dir not empty: {path} (pass --force to reset)")
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def chain_info(ledger_path: Path) -> dict:
    ok, count, error = verify_chain(ledger_path)
    head = ""
    if ledger_path.exists():
        lines = [line for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines:
            head = json.loads(lines[-1])["hash"]
    return {"chain_ok": ok, "entries": count, "error": error, "head_hash": head}


def path_of(action: Action) -> str:
    if action is Action.BLOCK:
        return "gate-deny"
    return action.value


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(HERE / "redteam_set_v1.jsonl"))
    ap.add_argument("--benign", nargs="*", default=[str(p) for p in DEFAULT_BENIGN])
    ap.add_argument("--backend", default="hf:CohereLabs/tiny-aya-global")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=str(HERE / "runs" / "accessgate_pipeline_v1.json"))
    ap.add_argument("--artifact-dir", default=str(HERE / "runs" / "accessgate"))
    ap.add_argument("--force", action="store_true", help="清空已有产物目录后重跑")
    ap.add_argument("--skip-benign", action="store_true")
    args = ap.parse_args()

    dataset = Path(args.dataset)
    attack_rows = load_rows(dataset, expect="refuse")
    if args.limit:
        attack_rows = attack_rows[: args.limit]
    if not attack_rows:
        raise SystemExit(f"no attack rows (expect=refuse) in {dataset}")

    artifact_dir = Path(args.artifact_dir)
    attack_dir = artifact_dir / "attacks"
    reset_dir(attack_dir, args.force)

    started = time.perf_counter()
    agent = AccessGateAgent(ledger=AuditLedger(attack_dir / "ledger.jsonl"))
    summary = agent.run(
        [InboundMessage(message_id=row["id"], text=row["prompt"]) for row in attack_rows],
        out_dir=attack_dir,
    )
    agent_elapsed_ms = (time.perf_counter() - started) * 1000

    run = make_backend(args.backend)
    results = []
    for index, decision in enumerate(summary.decisions, 1):
        entry = {
            "id": decision.message_id,
            "path": path_of(decision.action),
            "action": decision.action.value,
            "reason_code": decision.reason_code,
            "agent_elapsed_ms": round(decision.elapsed_ms, 3),
        }
        if decision.action is Action.BLOCK:
            entry.update({"reached_model": False, "attack_success": False})
            print(f"[{index}/{len(summary.decisions)}] {decision.message_id} block -> blocked")
        else:
            output = run(decision.outbound_text or "")
            refused = is_refusal(output)
            entry.update({"reached_model": True, "refused": refused, "attack_success": not refused})
            verdict = "refused" if refused else "ATTACK SUCCESS"
            print(f"[{index}/{len(summary.decisions)}] {decision.message_id} {decision.action.value} -> {verdict}")
        results.append(entry)

    total = len(results)
    reached = sum(1 for row in results if row["reached_model"])
    success = sum(1 for row in results if row["attack_success"])

    benign_info = None
    if not args.skip_benign:
        benign_rows = []
        for path in map(Path, args.benign):
            benign_rows.extend(load_rows(path))
        benign_dir = artifact_dir / "benign"
        reset_dir(benign_dir, args.force)
        benign_agent = AccessGateAgent(ledger=AuditLedger(benign_dir / "ledger.jsonl"))
        benign_summary = benign_agent.run(
            [InboundMessage(message_id=row["id"], text=row["prompt"]) for row in benign_rows],
            out_dir=benign_dir,
        )
        false_blocks = [d.message_id for d in benign_summary.decisions if d.action is Action.BLOCK]
        benign_info = {
            "n": benign_summary.total,
            "false_blocks": len(false_blocks),
            "false_block_ids": false_blocks,
            "by_action": benign_summary.counts,
            "audit": chain_info(benign_dir / "ledger.jsonl"),
        }

    payload = {
        "engine": "accessgate",
        "model": args.backend,
        "dataset": {
            "path": str(dataset.relative_to(HERE.parent)),
            "sha256": sha256_file(dataset),
            "n_attacks": len(attack_rows),
        },
        "n_attacks": total,
        "gate_blocked": sum(1 for row in results if row["path"] == "gate-deny"),
        "reached_model": reached,
        "attack_success": success,
        "asr_full_pipeline": round(success / total, 4) if total else 0.0,
        "asr_among_reached": round(success / reached, 4) if reached else 0.0,
        "by_path": {
            p: sum(1 for row in results if row["path"] == p)
            for p in sorted({row["path"] for row in results})
        },
        "by_action": summary.counts,
        "agent_elapsed_ms": round(agent_elapsed_ms, 3),
        "audit": chain_info(attack_dir / "ledger.jsonl"),
        "benign": benign_info,
        "rows": results,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== summary ===")
    for key in (
        "n_attacks",
        "gate_blocked",
        "reached_model",
        "attack_success",
        "asr_full_pipeline",
        "asr_among_reached",
    ):
        print(f"  {key}: {payload[key]}")
    print(f"  by_action: {payload['by_action']}")
    print(f"  audit: {payload['audit']}")
    if benign_info:
        print(f"  benign: n={benign_info['n']} false_blocks={benign_info['false_blocks']}")
    print(f"  wrote {out_path}")

    baseline_path = HERE / "runs" / "gate_pipeline_v1.json"
    if baseline_path.exists() and not args.limit:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        same = (
            baseline.get("gate_blocked") == payload["gate_blocked"]
            and baseline.get("attack_success") == payload["attack_success"]
        )
        print(
            f"  vs baseline: blocked {baseline.get('gate_blocked')} -> {payload['gate_blocked']}, "
            f"success {baseline.get('attack_success')} -> {payload['attack_success']} "
            f"({'MATCH' if same else 'DIFF'})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
