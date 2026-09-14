"""P1.1 回归: production_feedback_pipeline 幂等（重复运行不产生重复 decision）。"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE = REPO_ROOT / "scripts" / "production_feedback_pipeline.py"


def _load_module() -> object:
    spec = importlib.util.spec_from_file_location("pfl_test", PIPELINE)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pfl_test"] = mod  # dataclass 解析需要模块已在 sys.modules
    spec.loader.exec_module(mod)
    return mod


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_pipeline_is_idempotent(tmp_path: Path) -> None:
    mod = _load_module()

    audit = tmp_path / "audit.jsonl"
    cb = tmp_path / "cb.jsonl"
    _write_jsonl(audit, [
        {"timestamp": 1000, "event_type": "governance_decision", "action": "x"},
        {"timestamp": 1001, "event_type": "anomaly_detected", "actor": "a",
         "details": "d", "metadata": {"severity": "critical"}},
    ])
    _write_jsonl(cb, [{"timestamp": 1000, "details": "depth=3"}, {"timestamp": 1001}])

    meta_db = tmp_path / "experience.db"
    out = tmp_path / "convergence.jsonl"

    def run() -> int:
        p = mod.AuditFeedbackPipeline(
            audit_path=str(audit), cb_path=str(cb),
            output_path=str(out), meta_db_path=str(meta_db),
        )
        p.run()
        conn = sqlite3.connect(str(meta_db))
        n = conn.execute("SELECT COUNT(*) FROM experience").fetchone()[0]
        conn.close()
        return n

    first = run()
    assert first > 0, "首次运行应写入 decision 记录"
    second = run()
    assert second == first, "重复运行不得新增 decision（幂等）"
