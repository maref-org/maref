#!/usr/bin/env python3
"""用 MAREF 入站门禁跑红队集 v1，输出纯规则层的拦截率（不调用模型）。

用法:
    PYTHONPATH=../../src python3 prep/maref_gate_eval.py
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from maref.security.inbound import InboundDecision, InboundNormalizationGate

HERE = Path(__file__).resolve().parent


def main() -> int:
    rows = [json.loads(l) for l in (HERE / "redteam_set_v1.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    gate = InboundNormalizationGate()

    by_cat: dict[str, Counter] = defaultdict(Counter)
    details = []
    for r in rows:
        v = gate.check(r["prompt"])
        by_cat[r["category"]][v.decision.value] += 1
        details.append({
            "id": r["id"], "category": r["category"], "decision": v.decision.value,
            "methods": list(v.methods), "matched": v.matched, "reason": v.reason,
        })

    print(f"{'category':<16} {'n':>3} {'ALLOW':>6} {'REWRITE':>8} {'HITL':>5} {'DENY':>5}")
    for cat, c in sorted(by_cat.items()):
        n = sum(c.values())
        print(f"{cat:<16} {n:>3} {c['allow']:>6} {c['rewrite']:>8} {c['hitl']:>5} {c['deny']:>5}")

    enc = by_cat.get("encoding", Counter())
    ben = by_cat.get("benign", Counter())
    summary = {
        "encoding_deny": enc.get("deny", 0),
        "encoding_rewrite": enc.get("rewrite", 0),
        "encoding_allow": enc.get("allow", 0),
        "encoding_handled_rate": round((enc.get("deny", 0) + enc.get("rewrite", 0)) / max(1, sum(enc.values())), 4),
        "benign_false_deny": ben.get("deny", 0),
        "benign_false_deny_rate": round(ben.get("deny", 0) / max(1, sum(ben.values())), 4),
        "benign_rewrite": ben.get("rewrite", 0),
    }
    out = HERE / "runs" / "maref_gate_eval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "rows": details}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== summary ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\nencoding 未处理条目:")
    for d in details:
        if d["category"] == "encoding" and d["decision"] == "allow":
            print(f"  {d['id']}")
    print("benign 误拦条目:")
    for d in details:
        if d["category"] == "benign" and d["decision"] == "deny":
            print(f"  {d['id']}: {d['matched']}")
    print("saved:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
