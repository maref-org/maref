#!/usr/bin/env python3
"""Full pipeline eval: gate -> model, end to end.

For every attack prompt:
  gate DENY       -> blocked (model never sees it)
  gate REWRITE    -> model sees the normalised text
  gate ALLOW      -> model sees the original text

The final ASR is "fraction of attacks that reached the model AND got a
non-refusal". This is the deployment number: what the gate actually buys.

Run:
    python3 prep/gate_pipeline_eval.py [--limit N] [--backend hf:CohereLabs/tiny-aya-global]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent.parent / "src"))

from baseline_redteam import is_refusal, make_backend  # noqa: E402
from maref.security.inbound import InboundNormalizationGate  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(HERE / "redteam_set_v1.jsonl"))
    ap.add_argument("--backend", default="hf:CohereLabs/tiny-aya-global")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=str(HERE / "runs" / "gate_pipeline_v1.json"))
    args = ap.parse_args()

    rows = [json.loads(line) for line in Path(args.dataset).read_text().splitlines() if line.strip()]
    rows = [r for r in rows if r.get("expect") == "refuse"]
    if args.limit:
        rows = rows[: args.limit]

    gate = InboundNormalizationGate()
    run = make_backend(args.backend)

    results = []
    for i, r in enumerate(rows, 1):
        v = gate.check(r["prompt"])
        decision = v.decision.value
        if decision == "deny":
            results.append(
                {
                    "id": r["id"],
                    "path": "gate-deny",
                    "reached_model": False,
                    "attack_success": False,
                }
            )
            print(f"[{i}/{len(rows)}] {r['id']} gate-deny -> blocked")
            continue

        text = v.normalized if decision == "rewrite" else r["prompt"]
        out = run(text)
        refused = is_refusal(out)
        results.append(
            {
                "id": r["id"],
                "path": decision,
                "reached_model": True,
                "refused": refused,
                "attack_success": not refused,
            }
        )
        print(f"[{i}/{len(rows)}] {r['id']} {decision} -> {'refused' if refused else 'ATTACK SUCCESS'}")

    total = len(results)
    reached = sum(1 for x in results if x["reached_model"])
    success = sum(1 for x in results if x["attack_success"])
    out = {
        "model": args.backend,
        "n_attacks": total,
        "gate_blocked": sum(1 for x in results if x["path"] == "gate-deny"),
        "reached_model": reached,
        "attack_success": success,
        "asr_full_pipeline": round(success / total, 4) if total else 0.0,
        "asr_among_reached": round(success / reached, 4) if reached else 0.0,
        "by_path": {
            p: sum(1 for x in results if x["path"] == p)
            for p in sorted({x["path"] for x in results})
        },
        "rows": results,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("\n=== summary ===")
    for k in ("n_attacks", "gate_blocked", "reached_model", "attack_success", "asr_full_pipeline", "asr_among_reached"):
        print(f"  {k}: {out[k]}")
    print(f"  by_path: {out['by_path']}")
    print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
